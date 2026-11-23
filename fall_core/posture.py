"""자세 분류. 현재는 STANDING / NOT_STANDING / UNKNOWN 만 판정한다.

STANDING (모두 만족):
  S1 knee extension : 좌·우 hip-knee-ankle 내각 >= knee_extension_min_deg
  S2 hip neutral    : 좌·우 shoulder-hip-knee 내각 >= hip_extension_min_deg
  S3 patella 직하방 : 좌·우 |knee_x - hip_x| / L_trunk <= knee_hip_horizontal_max
  S4 수직 순서      : y 좌표 shoulder < hip < knee < ankle (y는 아래로 증가)
  S5 체간 직립      : 체간 수직 대비 경사각 <= trunk_tilt_max_deg
  S6 양측성         : S1~S3을 좌·우 모두 만족

2D 한계
  - 정면(frontal view)에서는 sagittal plane의 hip/knee flexion이 투영으로 작게 보이거나
    보이지 않는다. 정면에서 knee를 20도 굽혀도 일직선처럼 보일 수 있다.
  - 측면(sagittal view)에서는 반대편 하지가 가려질(occlusion) 수 있다.
  - 따라서 STANDING 판정은 시점에 따라 오차가 있다. (IMU로 정량화 예정)
"""
from dataclasses import dataclass, field

from fall_core.geometry import joint_angle_deg, normalize, trunk_length, trunk_tilt_deg
from fall_core.keypoints import (L_ANKLE, L_HIP, L_KNEE, L_SHOULDER, R_ANKLE, R_HIP, R_KNEE,
                                 R_SHOULDER, STANDING_REQUIRED, all_valid, as_kpts, midpoint)
from fall_core.states import Posture

NAN = float("nan")

FEATURE_KEYS = ("L_trunk", "knee_angle_L", "knee_angle_R", "hip_angle_L", "hip_angle_R",
                "knee_hip_dx_L", "knee_hip_dx_R", "trunk_tilt_deg")


@dataclass
class PostureResult:
    posture: Posture
    features: dict = field(default_factory=lambda: {k: NAN for k in FEATURE_KEYS})
    conditions: dict = field(default_factory=dict)   # S1~S6 통과 여부 (디버깅용)


def classify_posture(kpts, cfg):
    """한 프레임의 17점으로 자세를 판정한다. cfg는 load_thresholds()의 dict."""
    k = as_kpts(kpts)
    conf_min = cfg["keypoint_conf_min"]
    s = cfg["standing"]
    feats = {key: NAN for key in FEATURE_KEYS}

    # 체간 정보는 어깨와 골반만 보이면 계산해 둔다 (UNKNOWN이어도 기록용)
    sh_mid = midpoint(k, L_SHOULDER, R_SHOULDER, conf_min)
    pel_mid = midpoint(k, L_HIP, R_HIP, conf_min)
    if sh_mid is not None and pel_mid is not None:
        feats["L_trunk"] = trunk_length(sh_mid, pel_mid)
        feats["trunk_tilt_deg"] = trunk_tilt_deg(sh_mid, pel_mid)

    if not all_valid(k, STANDING_REQUIRED, conf_min):
        return PostureResult(Posture.UNKNOWN, feats, {})       # 판정 보류
    L = feats["L_trunk"]
    if not (L > 1e-6):
        return PostureResult(Posture.UNKNOWN, feats, {})

    sides = {"L": (L_SHOULDER, L_HIP, L_KNEE, L_ANKLE), "R": (R_SHOULDER, R_HIP, R_KNEE, R_ANKLE)}
    side_ok = {}
    s1 = s2 = s3 = True
    for name, (sho, hip, kne, ank) in sides.items():
        knee_ang = joint_angle_deg(k[hip, :2], k[kne, :2], k[ank, :2])
        hip_ang = joint_angle_deg(k[sho, :2], k[hip, :2], k[kne, :2])
        dx = normalize(abs(k[kne, 0] - k[hip, 0]), L)
        feats[f"knee_angle_{name}"] = knee_ang
        feats[f"hip_angle_{name}"] = hip_ang
        feats[f"knee_hip_dx_{name}"] = dx
        c1 = knee_ang >= s["knee_extension_min_deg"]
        c2 = hip_ang >= s["hip_extension_min_deg"]
        c3 = dx <= s["knee_hip_horizontal_max"]
        side_ok[name] = bool(c1 and c2 and c3)
        s1, s2, s3 = s1 and c1, s2 and c2, s3 and c3

    y_sho = (k[L_SHOULDER, 1] + k[R_SHOULDER, 1]) / 2
    y_hip = (k[L_HIP, 1] + k[R_HIP, 1]) / 2
    y_kne = (k[L_KNEE, 1] + k[R_KNEE, 1]) / 2
    y_ank = (k[L_ANKLE, 1] + k[R_ANKLE, 1]) / 2
    s4 = bool(y_sho < y_hip < y_kne < y_ank)
    s5 = bool(feats["trunk_tilt_deg"] <= s["trunk_tilt_max_deg"])
    s6 = bool(side_ok["L"] and side_ok["R"])

    cond = {"S1": bool(s1), "S2": bool(s2), "S3": bool(s3), "S4": s4, "S5": s5, "S6": s6}
    posture = Posture.STANDING if all(cond.values()) else Posture.NOT_STANDING
    return PostureResult(posture, feats, cond)
