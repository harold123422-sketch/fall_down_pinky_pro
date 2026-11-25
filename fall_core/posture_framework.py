"""세부 자세 분류 (BOS 기반 3축 프레임워크). 사양: docs/POSTURE_FRAMEWORK.md

세 개의 축 (모두 관절 좌표로 계산)
  1. 체간 방향  : 어깨 중점 -> 골반 중점 선이 수직선과 이루는 각도 (0 = 수직, 90 = 수평)
  2. 골반 높이  : (바닥 기준선 y - 골반 중점 y) / L_trunk_ref  (몸통 길이 단위. 서 있으면 약 2~3, 바닥에 앉거나 누우면 약 0)
  3. 지지 분절  : 바닥 기준선 근처(높이 <= posture.near_floor)에 있는 점 (ankle, knee, wrist, elbow, pelvis, shoulder)

'손바닥이 바닥에 닿았다'는 직접 볼 수 없으므로 'wrist가 바닥 기준선 근처'로 근사한다 (COCO에 palm 없음).
판단 순서는 프레임워크 4절 그대로 (먼저 맞는 것으로 결정). 모든 숫자는 config/thresholds.yaml 의 posture 블록이며
전부 임시값(실제 데이터로 확정 예정)이다.

2D 한계 때문에 구분이 어려운 자세는 certainty="LOW"로 표시한다 (예: 앙와위/복와위, 의자 앉기/90도 쪼그림).
"""
from dataclasses import dataclass, field

import numpy as np

from fall_core.geometry import joint_angle_deg, trunk_tilt_deg
from fall_core.keypoints import (L_ANKLE, L_ELBOW, L_HIP, L_KNEE, L_SHOULDER, L_WRIST, NOSE, R_ANKLE,
                                 R_ELBOW, R_HIP, R_KNEE, R_SHOULDER, R_WRIST, as_kpts)
from fall_core.posture import classify_posture
from fall_core.states import Posture

# ---------------------------------------------------------------- 자세 이름표
FAMILY = {
    "STAND_UPRIGHT": "STAND", "STAND_ONE_LEG": "STAND", "STAND_LEAN_SUPPORT": "STAND", "WALKING": "STAND",
    "FORWARD_FLEXION": "STAND", "SQUAT_PARTIAL": "STAND", "SQUAT_DEEP": "STAND",
    "SIT_CHAIR_UPRIGHT": "SIT", "SIT_CHAIR_SLUMPED": "SIT", "SIT_FLOOR_LONG": "SIT", "SIT_FLOOR_CROSS": "SIT",
    "SIT_FLOOR_SIDE": "SIT", "SIT_FLOOR_KNEES_UP": "SIT", "SIT_FLOOR": "SIT", "SIT_HEEL": "SIT",
    "KNEEL_BILATERAL": "KNEEL", "KNEEL_HALF_L": "KNEEL", "KNEEL_HALF_R": "KNEEL",
    "QUADRUPED": "QUADRUPED", "BEAR_POSE": "QUADRUPED", "CRAWLING": "QUADRUPED",
    "LYING_FLAT": "LYING", "LYING_SIDE_L": "LYING", "LYING_SIDE_R": "LYING", "LYING_FETAL": "LYING",
    "PRONE_ON_ELBOWS": "LYING", "SIDE_LYING_ON_ELBOW": "LYING", "RECLINED_SUPPORTED": "LYING",
    "OTHER": "OTHER", "UNKNOWN": "UNKNOWN",
}
FAMILY_KO = {"STAND": "기립 계열", "SIT": "앉기 계열", "KNEEL": "무릎 계열", "QUADRUPED": "네발 계열",
             "LYING": "누운 계열", "OTHER": "기타", "UNKNOWN": "판단 불가"}
KO = {
    "STAND_UPRIGHT": "양하지 기립", "STAND_ONE_LEG": "단하지 기립", "STAND_LEAN_SUPPORT": "지지 기립(기댄 자세)",
    "WALKING": "보행", "FORWARD_FLEXION": "체간 전방 굴곡", "SQUAT_PARTIAL": "부분 쪼그림", "SQUAT_DEEP": "깊은 쪼그림",
    "SIT_CHAIR_UPRIGHT": "의자 앉기(바른 자세)", "SIT_CHAIR_SLUMPED": "의자 앉기(체간 처짐)",
    "SIT_FLOOR_LONG": "장좌위(long sitting)", "SIT_FLOOR_CROSS": "책상다리 앉기", "SIT_FLOOR_SIDE": "측좌위(side sitting)",
    "SIT_FLOOR_KNEES_UP": "무릎 세워 앉기(hook sitting)", "SIT_FLOOR": "바닥 앉기(세부 미구분)",
    "SIT_HEEL": "뒤꿈치 위 앉기(seiza)",
    "KNEEL_BILATERAL": "양측 무릎 서기", "KNEEL_HALF_L": "반무릎 서기(왼무릎 바닥)", "KNEEL_HALF_R": "반무릎 서기(오른무릎 바닥)",
    "QUADRUPED": "사지 착지(hands-and-knees)", "BEAR_POSE": "손·발 지지(bear)", "CRAWLING": "기기",
    "LYING_FLAT": "앙와위 또는 복와위", "LYING_SIDE_L": "좌측와위(왼쪽이 바닥)", "LYING_SIDE_R": "우측와위(오른쪽이 바닥)",
    "LYING_FETAL": "태아 자세", "PRONE_ON_ELBOWS": "팔꿈치 지지 복와위", "SIDE_LYING_ON_ELBOW": "팔꿈치 지지 측와위",
    "RECLINED_SUPPORTED": "기댄 반와위(침대·소파)", "OTHER": "기타 자세", "UNKNOWN": "판단 불가",
}
# 2D에서 신뢰도가 낮은 자세와 그 이유
LOW_CERTAINTY = {
    "LYING_FLAT": "앙와위와 복와위는 2D 점만으로 구분이 어려움",
    "LYING_SIDE_L": "카메라 방향에 따라 앙와위와 헷갈릴 수 있음", "LYING_SIDE_R": "카메라 방향에 따라 앙와위와 헷갈릴 수 있음",
    "PRONE_ON_ELBOWS": "복와위 여부는 2D에서 확실하지 않음",
    "SIT_CHAIR_UPRIGHT": "90도 부분 쪼그림과 2D에서 구분이 어려움 (좌석은 보이지 않음)",
    "SIT_CHAIR_SLUMPED": "90도 부분 쪼그림과 2D에서 구분이 어려움",
    "SIT_FLOOR_CROSS": "정면 영상에서만 판단 가능", "SIT_FLOOR": "세부 바닥 앉기 자세를 구분하지 못함",
    "STAND_LEAN_SUPPORT": "벽·보행기 같은 지지물은 카메라로 확인하지 못함 (체간 기울기로만 판단)",
    "RECLINED_SUPPORTED": "등받이·침대는 보이지 않으므로 골반 높이와 기울기로만 추정",
    "SQUAT_DEEP": "바닥에 앉은 자세와 골반 높이로만 구분 (경계가 가까움)",
}


@dataclass
class PostureClass:
    name: str
    family: str
    ko: str
    reason: str
    certainty: str = "HIGH"
    note: str = ""            # LOW일 때 그 이유
    feats: dict = field(default_factory=dict)


def make_class(name, reason, feats=None):
    return PostureClass(name, FAMILY[name], KO[name], reason,
                        "LOW" if name in LOW_CERTAINTY else "HIGH", LOW_CERTAINTY.get(name, ""), feats or {})


# ---------------------------------------------------------------- 특징량
def _pt(k, i, c):
    return k[i, :2].astype(float) if k[i, 2] >= c else None


def _has(*xs):
    """모든 점이 보이는지 (numpy 배열은 'in'으로 비교하면 안 되므로 is not None 으로 확인)."""
    return all(x is not None for x in xs)


def _mid(a, b):
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return (a + b) / 2.0


def body_features(k, floor_y, l_ref, conf_min):
    """자세 판단에 쓰는 값. 어깨·골반이 모두 안 보이거나 기준(바닥선, 몸통 길이)이 없으면 None."""
    if floor_y is None or l_ref is None or not (l_ref > 1e-6):
        return None
    P = {n: _pt(k, i, conf_min) for n, i in (
        ("nose", NOSE), ("shL", L_SHOULDER), ("shR", R_SHOULDER), ("elL", L_ELBOW), ("elR", R_ELBOW),
        ("wrL", L_WRIST), ("wrR", R_WRIST), ("hipL", L_HIP), ("hipR", R_HIP), ("knL", L_KNEE), ("knR", R_KNEE),
        ("anL", L_ANKLE), ("anR", R_ANKLE))}
    sh, pel = _mid(P["shL"], P["shR"]), _mid(P["hipL"], P["hipR"])
    if sh is None or pel is None:
        return None

    def h(p):
        return None if p is None else (floor_y - p[1]) / l_ref

    f = {"P": P, "sh": sh, "pel": pel, "l": l_ref}
    f["tilt"] = trunk_tilt_deg(sh, pel)
    if f["tilt"] != f["tilt"]:                 # 어깨와 골반이 한 점으로 겹침 (몸이 카메라 쪽을 향해 누움 등)
        f["tilt"] = 0.0
    f["h_sh"], f["h_pel"] = h(sh), h(pel)
    for side in "LR":
        for part in ("kn", "an", "wr", "el"):
            f[f"h_{part}{side}"] = h(P[f"{part}{side}"])
        hip, kn, an, shs = P[f"hip{side}"], P[f"kn{side}"], P[f"an{side}"], P[f"sh{side}"]
        f[f"knee_ang{side}"] = joint_angle_deg(hip, kn, an) if _has(hip, kn, an) else None
        f[f"hip_ang{side}"] = joint_angle_deg(shs, hip, kn) if _has(shs, hip, kn) else None
    kn_mid = _mid(P["knL"], P["knR"])
    f["knee_chest"] = None if kn_mid is None else float(np.linalg.norm(kn_mid - sh)) / l_ref
    knees = [f[f"knee_ang{s}"] for s in "LR"]
    knees = [v for v in knees if v is not None and v == v]                    # NaN 제외
    f["knee_min"] = min(knees) if knees else None
    kh = [f[f"h_kn{s}"] for s in "LR" if f[f"h_kn{s}"] is not None]
    f["h_kn_mean"] = sum(kh) / len(kh) if kh else None
    return f


def _near(v, lim):
    return v is not None and v <= lim


def _any_near(f, part, lim):
    return _near(f[f"h_{part}L"], lim) or _near(f[f"h_{part}R"], lim)


# ---------------------------------------------------------------- 분류
def classify_framework(k, floor_y, l_ref, cfg, pelvis_speed=0.0, gait=False):
    """한 프레임의 자세. pelvis_speed = 골반 중점의 수평 이동 속도 (몸통 길이/초, 보행·기기 판단용).
    gait = 최근 양 발목이 번갈아 엇갈렸는지 (엔진이 시간에 따라 계산)."""
    k = as_kpts(k)
    c = cfg["keypoint_conf_min"]
    p = cfg["posture"]
    f = body_features(k, floor_y, l_ref, c)
    if f is None:
        return make_class("UNKNOWN", "어깨·골반이 보이지 않거나 바닥 기준선이 없음")
    nf = p["near_floor"]
    tilt, h_pel, h_sh, l = f["tilt"], f["h_pel"], f["h_sh"], f["l"]
    P = f["P"]
    feats = {k_: v for k_, v in f.items() if k_ not in ("P", "sh", "pel")}

    def C(name, reason):
        return make_class(name, reason, feats)

    # 2. 누운 계열: 어깨와 골반이 모두 바닥 근처 (체간 기울기와 무관: 카메라 쪽으로 누워 몸통이 짧게 보여도 잡힘)
    if h_pel <= p["lying_pelvis_max"] and h_sh <= p["lying_shoulder_max"]:
        if (f["knee_chest"] is not None and f["knee_chest"] <= p["fetal_knee_chest_max"]
                and f["knee_min"] is not None and f["knee_min"] <= p["fetal_knee_angle_max"]):
            return C("LYING_FETAL", f"어깨·골반이 바닥, 무릎이 가슴 가까이(거리 {f['knee_chest']:.2f})")
        shL, shR = P["shL"], P["shR"]
        if shL is not None and shR is not None:
            dy, dx = abs(shL[1] - shR[1]) / l, abs(shL[0] - shR[0]) / l
            if dy >= p["side_stack_min"] and dx <= p["side_width_max"]:
                name = "LYING_SIDE_L" if shL[1] > shR[1] else "LYING_SIDE_R"   # 아래(바닥 쪽) 어깨가 누운 쪽
                return C(name, f"양 어깨가 위아래로 겹침(세로 {dy:.2f}, 가로 {dx:.2f})")
            return C("LYING_FLAT", f"어깨·골반이 바닥, 양 어깨가 나란함(가로 {dx:.2f})")
        side = "R" if shL is not None else "L"       # 한쪽 어깨만 보이면 안 보이는 쪽이 바닥에 깔린 것으로 추정
        return C(f"LYING_SIDE_{side}", "어깨·골반이 바닥, 한쪽 어깨가 가려짐")

    # 3. 팔꿈치로 상체를 들어 올림
    if (h_pel <= p["sit_floor_pelvis_max"] and h_sh >= p["elbow_shoulder_min"]
            and p["elbow_tilt_min_deg"] <= tilt <= p["elbow_tilt_max_deg"]):
        down = [s for s in "LR" if _near(f[f"h_el{s}"], nf) and P[f"sh{s}"] is not None
                and abs(P[f"el{s}"][0] - P[f"sh{s}"][0]) / l <= p["elbow_under_shoulder_max"]]
        if len(down) == 2:
            return C("PRONE_ON_ELBOWS", "골반이 바닥, 양 팔꿈치가 어깨 아래 바닥에 있음")
        if len(down) == 1:
            return C("SIDE_LYING_ON_ELBOW", f"골반이 바닥, {'왼' if down[0] == 'L' else '오른'}팔꿈치가 어깨 아래 바닥에 있음")

    hands = _any_near(f, "wr", nf)
    knees_down = _any_near(f, "kn", nf)
    ankles_down = _any_near(f, "an", nf)
    # 4. 손·발 지지 (무릎은 바닥에서 뜸)
    knees_seen = [f[f"h_kn{s}"] for s in "LR" if f[f"h_kn{s}"] is not None]
    if (hands and ankles_down and knees_seen and all(v > nf for v in knees_seen)
            and tilt >= p["quad_tilt_min_deg"] and h_pel > p["sit_floor_pelvis_max"]):
        return C("BEAR_POSE", "손목·발목이 바닥, 무릎은 뜸, 체간이 수평에 가까움")
    # 5. 손 + 무릎 지지
    if hands and knees_down and tilt >= p["quad_tilt_min_deg"] and h_pel > p["sit_floor_pelvis_max"]:
        if pelvis_speed >= p["crawl_speed_min"]:
            return C("CRAWLING", f"사지 착지 + 이동 중(골반 {pelvis_speed:.2f} 몸통/초)")
        return C("QUADRUPED", "손목·무릎이 바닥, 체간이 수평에 가까움")

    # 6. 바닥 앉기: 골반이 바닥 + 체간 수직
    if h_pel <= p["sit_floor_pelvis_max"] and tilt <= p["sit_trunk_max_deg"]:
        kL, kR = P["knL"], P["knR"]
        pel = f["pel"]
        if kL is not None and kR is not None and f["knee_min"] is not None and f["knee_min"] <= p["knees_up_angle_max"]:
            oL, oR = (kL[0] - pel[0]) / l, (kR[0] - pel[0]) / l
            if oL * oR > 0 and abs(oL + oR) / 2 >= p["side_sit_knee_shift_min"] and hands:
                return C("SIT_FLOOR_SIDE", "골반이 바닥, 두 무릎이 한쪽으로 쏠림, 한 손이 바닥")
        knee_h = [v for v in (f["h_knL"], f["h_knR"]) if v is not None]
        if knee_h and max(knee_h) >= p["knees_up_min"] and f["knee_min"] is not None \
                and f["knee_min"] <= p["knees_up_angle_max"]:
            return C("SIT_FLOOR_KNEES_UP", "골반이 바닥, 무릎이 높이 올라옴")
        hL, hR, aL, aR = P["hipL"], P["hipR"], P["anL"], P["anR"]
        # 책상다리는 정면에서만 판단: 고관절 폭이 보여야 하고(측면이면 양 고관절이 겹쳐 비율이 잡음에 흔들림), 무릎이 굽어야 함
        if (_has(kL, kR, hL, hR, aL, aR) and abs(hL[0] - hR[0]) / l >= p["cross_hip_width_min"]
                and f["knee_min"] is not None and f["knee_min"] <= p["knees_up_angle_max"]):
            spread = abs(kL[0] - kR[0]) / abs(hL[0] - hR[0])
            gap = float(np.linalg.norm(aL - aR)) / l
            if spread >= p["cross_knee_spread_min"] and gap <= p["cross_ankle_gap_max"]:
                return C("SIT_FLOOR_CROSS", f"골반이 바닥, 무릎이 바깥으로 벌어지고(×{spread:.1f}) 발목이 모임")
        if f["knee_min"] is not None and f["knee_min"] >= p["long_sit_knee_min_deg"] and knees_down:
            return C("SIT_FLOOR_LONG", "골반이 바닥, 무릎이 펴진 채 다리를 앞으로 뻗음")
        return C("SIT_FLOOR", "골반이 바닥, 체간이 세워짐")

    # 7~8. 무릎이 바닥
    if knees_down:
        down = [s for s in "LR" if _near(f[f"h_kn{s}"], nf)]
        h_kn_down = min(f[f"h_kn{s}"] for s in down)
        above = h_pel - h_kn_down
        if above >= p["kneel_pelvis_above_knee_min"] and tilt <= p["kneel_trunk_max_deg"]:
            if len(down) == 2:
                return C("KNEEL_BILATERAL", f"양 무릎이 바닥, 골반이 무릎 위({above:.2f})")
            other = "R" if down[0] == "L" else "L"
            if f[f"h_kn{other}"] is not None and f[f"h_kn{other}"] >= p["half_kneel_other_knee_min"]:
                return C(f"KNEEL_HALF_{down[0]}", f"{'왼' if down[0] == 'L' else '오른'}무릎이 바닥, 반대 무릎은 세움")
            return C("KNEEL_BILATERAL", "무릎이 바닥, 골반이 무릎 위 (반대 무릎이 가려짐)")
        if h_pel > p["sit_floor_pelvis_max"] and tilt <= p["sit_trunk_max_deg"]:
            return C("SIT_HEEL", f"무릎이 바닥, 골반이 발뒤꿈치 위(무릎보다 {above:.2f} 높음)")

    # (추가) 기댄 반와위: 체간이 많이 기울었지만 골반이 바닥보다 높고 발은 바닥에 없음 (침대·소파)
    both_ankles_down = _near(f["h_anL"], nf) and _near(f["h_anR"], nf)
    if (tilt >= p["reclined_tilt_min_deg"] and p["sit_floor_pelvis_max"] < h_pel <= p["reclined_pelvis_max"]
            and not both_ankles_down):
        return C("RECLINED_SUPPORTED", f"체간 기울기 {tilt:.0f}°, 골반이 바닥보다 높고 발이 바닥에 없음")

    # 9. 의자 앉기: 골반 높이 ≈ 무릎 높이 + 발이 바닥
    if (f["h_kn_mean"] is not None and abs(h_pel - f["h_kn_mean"]) <= p["chair_pelvis_knee_max"]
            and ankles_down and h_pel > p["sit_floor_pelvis_max"]):
        shL, shR = P["shL"], P["shR"]
        dy = abs(shL[1] - shR[1]) / l if shL is not None and shR is not None else 0.0
        if tilt >= p["slumped_tilt_min_deg"] or dy >= p["slumped_shoulder_dy_min"]:
            return C("SIT_CHAIR_SLUMPED", f"골반≈무릎 높이, 체간이 기울거나 한쪽 어깨가 처짐({tilt:.0f}°)")
        return C("SIT_CHAIR_UPRIGHT", "골반≈무릎 높이, 발이 바닥, 체간 직립")

    # 10. 쪼그림: 발이 바닥 + 무릎 굽힘 + 골반이 중간~낮음
    if (ankles_down and f["knee_min"] is not None and f["knee_min"] <= p["squat_knee_angle_max"]
            and p["sit_floor_pelvis_max"] < h_pel <= p["squat_partial_pelvis_max"]):
        if h_pel <= p["squat_deep_pelvis_max"]:
            return C("SQUAT_DEEP", f"발이 바닥, 골반이 낮음({h_pel:.2f}), 무릎 {f['knee_min']:.0f}°")
        return C("SQUAT_PARTIAL", f"발이 바닥, 골반이 중간 높이({h_pel:.2f}), 무릎 {f['knee_min']:.0f}°")

    # 11. 체간 전방 굴곡 + 무릎 신전
    if (tilt >= p["flexion_tilt_min_deg"] and f["knee_min"] is not None
            and f["knee_min"] >= p["flexion_knee_min_deg"] and ankles_down):
        return C("FORWARD_FLEXION", f"무릎을 편 채 체간이 {tilt:.0f}° 숙여짐")

    # 12. 기립 계열
    s = cfg["standing"]
    high = h_pel > p["squat_partial_pelvis_max"]
    if high and tilt <= p["lean_tilt_max_deg"] and (gait or pelvis_speed >= p["walk_speed_min"]):
        why = "양 발목이 번갈아 엇갈림(보행 주기)" if gait else f"서서 이동 중(골반 {pelvis_speed:.2f} 몸통/초)"
        return C("WALKING", why)
    for sup, lift in (("L", "R"), ("R", "L")):
        if (tilt <= s["trunk_tilt_max_deg"] and _near(f[f"h_an{sup}"], nf)
                and f[f"h_an{lift}"] is not None and f[f"h_an{lift}"] >= p["one_leg_lift_min"]
                and f[f"knee_ang{sup}"] is not None and f[f"knee_ang{sup}"] >= s["knee_extension_min_deg"]):
            return C("STAND_ONE_LEG", f"{'왼' if sup == 'L' else '오른'}발로만 섬 (반대 발목 높이 {f[f'h_an{lift}']:.2f})")
    if classify_posture(k, cfg).posture == Posture.STANDING:
        return C("STAND_UPRIGHT", "무릎·고관절 신전, 골반 아래 무릎·발목, 체간 직립 (S1~S6)")
    if (high and s["trunk_tilt_max_deg"] < tilt <= p["lean_tilt_max_deg"] and ankles_down
            and f["knee_min"] is not None and f["knee_min"] >= p["flexion_knee_min_deg"]):
        return C("STAND_LEAN_SUPPORT", f"무릎을 편 채 체간이 {tilt:.0f}° 기울어 섬")

    # 13. 그 외
    return C("OTHER", f"규칙에 맞지 않음 (체간 {tilt:.0f}°, 골반 높이 {h_pel:.2f})")


# ---------------------------------------------------------------- 자세 전이 (프레임워크 6절)
_STANDISH = {"STAND_UPRIGHT", "STAND_ONE_LEG", "STAND_LEAN_SUPPORT", "WALKING"}
_FLOOR_SIT = {"SIT_FLOOR_LONG", "SIT_FLOOR_CROSS", "SIT_FLOOR_SIDE", "SIT_FLOOR_KNEES_UP", "SIT_FLOOR"}
_LIE = {"LYING_FLAT", "LYING_SIDE_L", "LYING_SIDE_R", "LYING_FETAL"}
_ROLL = {"LYING_FLAT", "LYING_SIDE_L", "LYING_SIDE_R"}          # 돌아눕기는 이 셋 사이 전환만


def transition_name(prev, new):
    """안정된 자세가 prev -> new 로 바뀌었을 때의 전이 이름 (해당 없으면 None). FALL_DESCENT는 엔진이 낙상 시 붙인다."""
    if prev is None or prev == new or "UNKNOWN" in (prev, new):
        return None
    fp, fn = FAMILY[prev], FAMILY[new]
    if prev in _STANDISH and new in ("SIT_CHAIR_UPRIGHT", "SIT_CHAIR_SLUMPED"):
        return "STAND_TO_SIT"
    if prev in ("SIT_CHAIR_UPRIGHT", "SIT_CHAIR_SLUMPED") and new in _STANDISH:
        return "SIT_TO_STAND"
    if prev in _STANDISH and new.startswith("SQUAT"):
        return "CONTROLLED_DESCENT"
    # 기립 계열(체간 굴곡·쪼그림 포함)에서 무릎·바닥 앉기·누운 계열로: 낙상 사건이 없었다면 조절된 하강
    if fp == "STAND" and (fn in ("KNEEL", "LYING") or new in _FLOOR_SIT or new == "SIT_HEEL"):
        return "CONTROLLED_DESCENT"
    if prev in _FLOOR_SIT and new in _LIE:
        return "SIT_TO_LIE"
    if prev in ("LYING_SIDE_L", "LYING_SIDE_R") and new == "SIDE_LYING_ON_ELBOW":
        return "SIDE_TO_SIT"
    if prev == "SIDE_LYING_ON_ELBOW" and new in _FLOOR_SIT:
        return "SIDE_TO_SIT"
    if prev in _LIE and new in _FLOOR_SIT:
        return "LIE_TO_SIT"
    if prev in _ROLL and new in _ROLL:
        return "ROLL"
    if (prev in _LIE or prev in ("PRONE_ON_ELBOWS", "SIDE_LYING_ON_ELBOW")) and fn == "QUADRUPED":
        return "LIE_TO_QUADRUPED"
    if fp == "QUADRUPED" and fn == "KNEEL":
        return "QUADRUPED_TO_KNEEL"
    if prev.startswith("KNEEL_HALF") and new in _STANDISH:
        return "KNEEL_TO_STAND"
    return None


TRANSITION_KO = {
    "FALL_DESCENT": "낙상성 하강", "CONTROLLED_DESCENT": "조절된 하강", "STAND_TO_SIT": "서기→의자 앉기",
    "SIT_TO_STAND": "의자 앉기→서기", "SIT_TO_LIE": "앉기→눕기", "LIE_TO_SIT": "눕기→앉기",
    "SIDE_TO_SIT": "측와위→팔꿈치 지지→측좌위", "ROLL": "돌아눕기", "LIE_TO_QUADRUPED": "눕기→네발",
    "QUADRUPED_TO_KNEEL": "네발→무릎 서기", "KNEEL_TO_STAND": "반무릎→서기", "RECOVERY_PATH": "자력 회복 완료",
    "SLIP_DOWN": "미끄러져 내려앉음(슬립다운)",
}

