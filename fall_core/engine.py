"""STANDING 판정 + 세부 자세 + 무움직임 + 낙상 후 경보를 묶는 엔진 (track_id별 상태 관리).

입력 : update(t, detections)   t = 프레임 타임스탬프(초)
        detections = [{"track_id": int, "kpts": (17,3) 배열, "box_conf": float}, ...]
출력 : track별 TrackResult 목록

처리 순서 (프레임마다)
  0) 관절 좌표 떨림 보정 (지수평균, smoothing.keypoint_alpha)
  1) STANDING(S1~S6) 판정과 확정 (낙상 규칙 F1과 바닥 기준선에 씀)
  2) 기준값 갱신: 몸통 길이 L_trunk_ref, 바닥 기준선 (서 있을 때만). 서 있던 적이 없으면 바닥을 추정
  3) 세부 자세 분류 (posture_framework, 프레임워크 13단계 순서) + 깜빡임 방지 (posture.min_hold_s)
  4) 무움직임 (자세와 무관 / 기립 중 / 현재 자세 유지 중)
  5) 낙상 사건 (임시 규칙: 직전 기립 + 빠른 골반 하강 + 바닥 도달)
  6) 경보: 낙상 후(긴급, 스스로 일어나는 중, 움직임, 회복) / 평상시(자세별 주의, 무움직임 확인)

[지시서에 없는 부분을 정한 가정] (README와 docs/POSTURE_FRAMEWORK.md에 기록, 사용자 확인 필요)
  1. POST_FALL에서 긴급이 한 번 발령되면(latched) 움직임이 생겨도 해제하지 않는다. RECOVERED 로만 해제.
  2. 낙상 직후 post_fall_settle_s 동안의 움직임은 '몸이 자리잡는 중'으로 보고 POST_FALL_MOVING으로 표시하지 않는다.
  3. POST_FALL_MOVING은 한 번 표시되면 RECOVERED/긴급 전까지 유지한다 ("사람이 확인할 때까지 유지").
  4. 소실된 POST_FALL track은 같은 위치에 새 track_id로 나타나면 이어 붙인다 (POST_FALL 상태만 대상).
  5. 낙상 후 회복 경로 자세(회복 2단계 이상)에 있으면 SELF_RECOVERABLE(주의)로 표시한다.
"""
import math
from dataclasses import dataclass, field

import numpy as np

from fall_core.alerts import FallEventDetector, select_alert
from fall_core.fall_metrics import describe_descent
from fall_core.history import Sample, TrackHistory
from fall_core.immobility import ImmobilityTimer, WindowStatus, evaluate_window
from fall_core.keypoints import L_ANKLE, L_HIP, R_ANKLE, R_HIP, as_kpts, midpoint
from fall_core.posture import FEATURE_KEYS, classify_posture
from fall_core.posture_framework import KO, classify_framework, make_class, transition_name
from fall_core.states import Alert, Mode, Posture

NAN = float("nan")
_SLIP_FROM = {"SIT_CHAIR_UPRIGHT", "SIT_CHAIR_SLUMPED", "RECLINED_SUPPORTED"}   # 슬립다운이 시작되는 자세


@dataclass
class TrackContext:
    track_id: int
    history: TrackHistory
    created_t: float
    last_seen_t: float
    timer: ImmobilityTimer = field(default_factory=ImmobilityTimer)            # 자세와 무관한 연속 무움직임
    standing_timer: ImmobilityTimer = field(default_factory=ImmobilityTimer)   # STANDING 중의 무움직임
    posture_timer: ImmobilityTimer = field(default_factory=ImmobilityTimer)    # 지금 세부 자세를 유지하는 동안의 무움직임
    k_smooth: object = None           # 떨림 보정된 관절 좌표
    last_center: object = None
    last_l_trunk: float = None
    l_ref: float = None               # 최근 STANDING 구간의 trunk length (지수평균)
    floor_y: float = None             # 최근 STANDING 구간의 ankle 평균 y
    last_standing_t: float = None
    streak_start: float = None        # STANDING 조건이 연속으로 만족된 시작 시각
    confirmed_standing: bool = False
    held_posture: Posture = Posture.UNKNOWN
    cls: object = None                # 안정된 세부 자세 (PostureClass)
    cls_since: float = None
    cand: str = None                  # 바뀌려는 중인 자세 이름
    last_named: str = None            # 마지막으로 이름 붙은 자세 (기타·판단 불가는 건너뜀, 전이 이름용)
    cand_since: float = None
    mode: Mode = Mode.NORMAL
    fall_event_t: float = None
    landing_stage: int = None         # 낙상 후 처음 자리 잡은 자세의 회복 단계 (이보다 올라가야 '스스로 일어나는 중')
    fall_type: str = None             # FALL (기립에서 빠른 하강) / SLIP_DOWN (의자·침대에서 미끄러져 내려앉음)
    fall_metrics: dict = None         # 낙상 모양 (fall_metrics.describe_descent)
    pre_fall_posture: str = None      # 낙상 직전 자세
    landing_posture: str = None       # 낙상 후 처음 자리 잡은 자세
    latched: bool = False
    moving_seen: bool = False
    check_active: bool = False
    posture_caution: bool = False
    caution_chain_start: float = None  # 주의 자세(caution_after_s 있음)가 끊기지 않고 시작된 시각
    posture_check: bool = False


@dataclass
class TrackResult:
    track_id: int
    t: float
    posture: Posture
    mode: Mode
    alert: Alert
    events: list
    features: dict
    l_trunk_ref: float
    # (floor_y - pelvis_y) / L_trunk_ref : 바닥 위 높이(몸통길이 단위).
    # 서 있으면 다리 길이만큼(몸통의 약 2~3배), 누우면 약 0
    pelvis_y_norm: float
    descent_speed: float              # 몸통길이/초
    immobile_elapsed_s: float
    window_status: WindowStatus
    max_displacement: float
    fall_event_t_s: float
    instant_posture: Posture = Posture.UNKNOWN
    # ---- 세부 자세 (posture_framework)
    posture_class: str = "UNKNOWN"
    posture_family: str = "UNKNOWN"
    posture_ko: str = "판단 불가"
    posture_certainty: str = "HIGH"
    posture_reason: str = ""
    posture_note: str = ""            # posture_risk 의 note (위험 판단 이유)
    posture_held_s: float = 0.0
    instant_class: str = "UNKNOWN"
    recovery_stage: int = None        # 낙상 후 회복 경로 단계 (1 눕기 ~ 6 서기)
    floor_source: str = "none"        # standing(서 있을 때 측정) / estimated(가장 낮은 관절점으로 추정) / none
    pelvis_speed: float = NAN         # 골반 수평 이동 속도 (몸통길이/초)
    # ---- 낙상 보고서용 (낙상 후에만 채워짐)
    fall_type: str = None
    fall_metrics: dict = None
    pre_fall_posture: str = None
    landing_posture: str = None


def _center(k, conf_min):
    valid = k[:, 2] >= conf_min
    return k[valid, :2].mean(axis=0) if valid.any() else None


class FallCoreEngine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.detector = FallEventDetector(cfg)
        self.tracks = {}
        f, i = cfg["fall_event"], cfg["immobility"]
        self.keep_s = max(i["window_s"], f["fall_max_duration_s"], f["fall_prior_standing_s"],
                          cfg["smoothing"]["floor_estimate_window_s"], cfg["posture"]["motion_window_s"],
                          cfg["fall_type"]["slip_down_max_s"] + cfg["posture"]["min_hold_s"],
                          cfg["posture"]["gait_window_s"]) + 1.0

    # ------------------------------------------------------------------ 공개 API
    def update(self, t, detections):
        current_ids = {d["track_id"] for d in detections}
        results = []
        for det in detections:
            tid = det["track_id"]
            ctx = self.tracks.get(tid)
            extra = []
            if ctx is None:
                ctx = self._readopt(tid, det, t, current_ids)
                if ctx is not None:
                    extra.append("TRACK_READOPTED")
                else:
                    ctx = TrackContext(tid, TrackHistory(self.keep_s), t, t)
                    self.tracks[tid] = ctx
            res = self._step(ctx, t, det)
            res.events = extra + res.events
            results.append(res)
        self._expire(t, current_ids)
        return results

    # ------------------------------------------------------------------ 내부
    def _readopt(self, tid, det, t, current_ids):
        """소실된 POST_FALL track을 같은 위치에서 재검출된 새 track_id로 이어 붙인다."""
        a = self.cfg["alerts"]
        center = _center(as_kpts(det["kpts"]), self.cfg["keypoint_conf_min"])
        if center is None:
            return None
        best, best_d = None, math.inf
        for oid, c in self.tracks.items():
            if oid in current_ids or c.mode != Mode.POST_FALL or c.last_center is None:
                continue
            if t - c.last_seen_t > a["track_lost_hold_s"]:
                continue
            scale = c.l_ref or c.last_l_trunk or 100.0
            d = float(np.linalg.norm(center - c.last_center)) / scale
            if d <= a["track_readopt_max_dist"] and d < best_d:
                best, best_d = oid, d
        if best is None:
            return None
        ctx = self.tracks.pop(best)
        ctx.track_id = tid
        self.tracks[tid] = ctx
        return ctx

    def _expire(self, t, current_ids):
        hold = self.cfg["alerts"]["track_lost_hold_s"]
        for tid in [i for i, c in self.tracks.items() if i not in current_ids and t - c.last_seen_t > hold]:
            del self.tracks[tid]

    def _l_used(self, ctx, feats, t):
        """정규화 기준 길이: 최근 STANDING의 trunk length, 없으면 최근 창의 최대 trunk length."""
        if ctx.l_ref:
            return ctx.l_ref
        win = self.cfg["immobility"]["window_s"]
        vals = [s.features.get("L_trunk") for s in ctx.history.window(t, win)] + [feats["L_trunk"]]
        vals = [v for v in vals if v is not None and v == v and v > 0]
        return max(vals) if vals else None

    def _smooth(self, ctx, k):
        """관절 좌표 떨림 보정. 두 프레임 모두 보이는 점만 지수평균, 새로 나타난 점은 그대로 쓴다."""
        a = self.cfg["smoothing"]["keypoint_alpha"]
        c = self.cfg["keypoint_conf_min"]
        if ctx.k_smooth is None or a >= 1.0:
            ctx.k_smooth = k.copy()
            return k.copy()
        out = k.copy()
        both = (k[:, 2] >= c) & (ctx.k_smooth[:, 2] >= c)
        out[both, :2] = a * k[both, :2] + (1 - a) * ctx.k_smooth[both, :2]
        ctx.k_smooth = out
        return out

    def _floor_ref(self, ctx, t):
        """바닥 기준선. 서 있을 때 잰 값이 있으면 그것, 없으면 최근 구간에서 가장 낮게 보인 관절점의 y."""
        if ctx.floor_y is not None:
            return ctx.floor_y, "standing"
        span = self.cfg["smoothing"]["floor_estimate_window_s"]
        lows = [s.features.get("lowest_y") for s in ctx.history.window(t, span)]
        lows = [v for v in lows if v is not None and v == v]
        return (max(lows), "estimated") if lows else (None, "none")

    def _pelvis_speed(self, ctx, t, l_used):
        win = ctx.history.window(t, self.cfg["posture"]["motion_window_s"])
        pts = [(s.t, s.features.get("pelvis_x")) for s in win]
        pts = [(tt, x) for tt, x in pts if x is not None and x == x]          # NaN(골반 안 보임) 제외
        if len(pts) < 2 or not l_used or pts[-1][0] - pts[0][0] < 0.3:
            return 0.0
        return abs(pts[-1][1] - pts[0][1]) / l_used / (pts[-1][0] - pts[0][0])

    def _step(self, ctx, t, det):
        cfg = self.cfg
        a = cfg["alerts"]
        ft = cfg["fall_type"]
        conf_min = cfg["keypoint_conf_min"]
        risk_table = cfg.get("posture_risk", {})
        events = []

        # 관측이 끊겼다가 돌아오면 끊긴 시간은 무움직임으로 세지 않고, 떨림 보정도 새로 시작
        if t - ctx.last_seen_t > a["gap_resume_s"]:
            for tm in (ctx.timer, ctx.standing_timer, ctx.posture_timer):
                tm.resume(t)
            ctx.k_smooth = None
        ctx.last_seen_t = t

        # 0) 떨림 보정
        k = self._smooth(ctx, as_kpts(det["kpts"]))

        # 1) STANDING (S1~S6, min_duration_s 이상 연속 만족해야 확정)
        pr = classify_posture(k, cfg)
        feats = pr.features
        if pr.posture == Posture.STANDING:
            if ctx.streak_start is None:
                ctx.streak_start = t
            if not ctx.confirmed_standing and t - ctx.streak_start >= cfg["standing"]["min_duration_s"]:
                ctx.confirmed_standing = True
        elif pr.posture == Posture.NOT_STANDING:
            ctx.streak_start, ctx.confirmed_standing = None, False
        if pr.posture != Posture.UNKNOWN:
            ctx.held_posture = Posture.STANDING if ctx.confirmed_standing else Posture.NOT_STANDING
        posture_out = Posture.UNKNOWN if pr.posture == Posture.UNKNOWN else ctx.held_posture

        # 2) 기준값 갱신 (STANDING 구간에서만): L_trunk_ref, 바닥 기준선, 마지막 STANDING 시각
        if ctx.confirmed_standing and pr.posture == Posture.STANDING:
            alpha = cfg["standing"]["reference_ema_alpha"]
            ctx.last_standing_t = t
            ctx.l_ref = feats["L_trunk"] if ctx.l_ref is None else (
                (1 - alpha) * ctx.l_ref + alpha * feats["L_trunk"])
            ankle_y = (k[L_ANKLE, 1] + k[R_ANKLE, 1]) / 2
            ctx.floor_y = ankle_y if ctx.floor_y is None else (1 - alpha) * ctx.floor_y + alpha * ankle_y
        if feats["L_trunk"] == feats["L_trunk"]:
            ctx.last_l_trunk = feats["L_trunk"]
        center = _center(k, conf_min)
        if center is not None:
            ctx.last_center = center

        # 샘플 기록
        hip_mid = midpoint(k, L_HIP, R_HIP, conf_min)
        pelvis_y = float(hip_mid[1]) if hip_mid is not None else NAN
        valid_y = k[k[:, 2] >= conf_min, 1]
        sample_feats = dict(feats)
        sample_feats["pelvis_y"] = pelvis_y
        sample_feats["pelvis_x"] = float(hip_mid[0]) if hip_mid is not None else NAN
        sample_feats["lowest_y"] = float(valid_y.max()) if valid_y.size else NAN
        ctx.history.add(Sample(t, k.copy(), sample_feats, posture_out))
        l_used = self._l_used(ctx, feats, t)
        floor_ref, floor_src = self._floor_ref(ctx, t)
        speed = self._pelvis_speed(ctx, t, l_used)

        # 3) 세부 자세 + 깜빡임 방지 (새 자세는 min_hold_s 이상 이어져야 바뀜, UNKNOWN은 이전 자세 유지)
        inst = classify_framework(k, floor_ref, l_used, cfg, speed, self._gait(ctx, t, l_used))
        slip_from = None
        if ctx.cls is None:
            ctx.cls, ctx.cls_since = inst, t
            ctx.posture_timer.reset(t)
            if inst.name not in ("OTHER", "UNKNOWN"):
                ctx.last_named = inst.name
        elif inst.name == ctx.cls.name:
            ctx.cls, ctx.cand = inst, None                   # 같은 자세: 근거·특징값만 새로
        elif inst.name != "UNKNOWN":
            if ctx.cand != inst.name:
                ctx.cand, ctx.cand_since = inst.name, t
            if t - ctx.cand_since >= cfg["posture"]["min_hold_s"] or ctx.cls.name == "UNKNOWN":
                prev_named = ctx.last_named or ctx.cls.name
                to_floor = inst.family in ("LYING", "SIT") and inst.name not in _SLIP_FROM
                if (ctx.mode != Mode.POST_FALL and prev_named in _SLIP_FROM and to_floor
                        and self._pelvis_drop(ctx, t, l_used) >= ft["slip_down_min_drop"]):
                    slip_from = prev_named
                trans = transition_name(prev_named, inst.name)
                if ctx.mode == Mode.POST_FALL and trans == "CONTROLLED_DESCENT":
                    trans = None          # 낙상 직후의 자세 변화는 이미 FALL_DESCENT로 기록됨
                events.append(f"POSTURE:{ctx.cls.name}->{inst.name}")
                if trans:
                    events.append(f"TRANSITION:{trans}")
                ctx.cls, ctx.cls_since, ctx.cand = inst, t, None
                ctx.posture_timer.reset(t)
                if inst.name not in ("OTHER", "UNKNOWN"):
                    ctx.last_named = inst.name
        cls = ctx.cls
        rule = risk_table.get(cls.name, {}) or {}
        # 주의 자세끼리 바뀌면(예: 바닥에 누움 -> 태아 자세) 주의 시간을 이어서 센다. 주의 자세가 아니면 끊김
        if rule.get("caution_after_s") is None:
            ctx.caution_chain_start = None
        elif ctx.caution_chain_start is None:
            ctx.caution_chain_start = ctx.cls_since
        stage = rule.get("recovery_stage")

        # 4) 무움직임
        window = ctx.history.window(t, cfg["immobility"]["window_s"])
        status, max_disp, span = evaluate_window(window, l_used, cfg)
        ctx.timer.update(t, status, span)
        ctx.posture_timer.update(t, status, span)
        if ctx.held_posture == Posture.STANDING:
            ctx.standing_timer.update(t, status, span)
        else:
            ctx.standing_timer.reset(t)

        # 5) 낙상 사건 (하강 속도 기준은 임시값, IMU로 확정 예정)
        descent = self.detector.descent_speed(ctx.history, t, l_used)
        fell = False
        if ctx.mode != Mode.POST_FALL:
            fell = self.detector.check(t, ctx.last_standing_t, descent, pelvis_y, ctx.floor_y, l_used)
            ftype = "FALL"
            if not fell and slip_from is not None:
                fell, ftype = True, "SLIP_DOWN"
            if fell:
                events += ["FALL_EVENT", "TRANSITION:FALL_DESCENT" if ftype == "FALL" else "TRANSITION:SLIP_DOWN"]
                if ftype == "SLIP_DOWN":
                    events.append("SLIP_DOWN")
                lookback = (cfg["fall_event"]["fall_max_duration_s"] + 1.0 if ftype == "FALL"
                            else ft["slip_down_max_s"] + cfg["posture"]["min_hold_s"])
                ctx.fall_type = ftype
                ctx.fall_metrics = describe_descent(ctx.history, t, l_used, cfg, lookback,
                                                    descent if ftype == "FALL" else None, ftype)
                ctx.pre_fall_posture = slip_from if ftype == "SLIP_DOWN" else cls.name
                ctx.landing_posture = cls.name if ftype == "SLIP_DOWN" else None
                ctx.mode = Mode.POST_FALL
                ctx.fall_event_t = t
                ctx.timer.reset(t)
                ctx.standing_timer.reset(t)
                ctx.latched, ctx.moving_seen, ctx.check_active = False, False, False
                ctx.posture_caution, ctx.posture_check = False, False
                ctx.landing_stage = None

        # 6) 경보
        if ctx.mode == Mode.POST_FALL and not fell:
            if (ctx.confirmed_standing and ctx.streak_start is not None
                    and t - ctx.streak_start >= a["recovery_standing_min_s"]):
                ctx.mode = Mode.RECOVERED
                ctx.latched, ctx.moving_seen, ctx.landing_stage = False, False, None
                events += ["RECOVERED", "TRANSITION:RECOVERY_PATH"]
            else:
                if status == WindowStatus.MOVING and t - ctx.fall_event_t >= a["post_fall_settle_s"]:
                    ctx.moving_seen = True
                if not ctx.latched and ctx.timer.elapsed >= a["post_fall_immobile_emergency_s"]:
                    ctx.latched = True
                    events.append("EMERGENCY_POST_FALL_IMMOBILE")
        held_s = t - ctx.cls_since if ctx.cls_since is not None else 0.0
        if ctx.mode != Mode.POST_FALL:
            check_now = (ctx.held_posture == Posture.STANDING
                         and ctx.standing_timer.elapsed >= a["standing_immobile_check_s"])
            if check_now and not ctx.check_active:
                events.append("CHECK_STANDING_IMMOBILE")
            if ctx.check_active and not check_now:
                events.append("CHECK_CLEARED")
            ctx.check_active = check_now

            ca, ci = rule.get("caution_after_s"), rule.get("immobile_check_s")
            caution_now = (ca is not None and ctx.caution_chain_start is not None
                           and t - ctx.caution_chain_start >= ca)
            pcheck_now = ci is not None and ctx.posture_timer.elapsed >= ci
            if caution_now and not ctx.posture_caution:
                events.append(f"POSTURE_CAUTION:{cls.name}")
            if pcheck_now and not ctx.posture_check:
                events.append(f"CHECK_POSTURE_IMMOBILE:{cls.name}")
            ctx.posture_caution, ctx.posture_check = caution_now, pcheck_now

        # 회복 단계: 낙상 '이후에' 자리 잡은 자세만 센다 (낙상 순간에 남아 있던 기립 자세는 제외)
        recovery_stage, self_recovering = None, False
        if ctx.mode == Mode.POST_FALL and ctx.cls_since is not None and ctx.cls_since >= ctx.fall_event_t:
            recovery_stage = stage
            if ctx.landing_posture is None:
                ctx.landing_posture = cls.name
            if ctx.landing_stage is None:
                ctx.landing_stage = stage
            self_recovering = (stage is not None and ctx.landing_stage is not None
                               and stage >= 2 and stage > ctx.landing_stage)
        alert = select_alert(ctx.mode, ctx.latched, ctx.moving_seen, ctx.check_active,
                             self_recovering, ctx.posture_check, ctx.posture_caution)
        if ctx.mode == Mode.POST_FALL:
            elapsed = ctx.timer.elapsed
        elif ctx.held_posture == Posture.STANDING and cls.name == "STAND_UPRIGHT":
            elapsed = ctx.standing_timer.elapsed
        else:
            elapsed = ctx.posture_timer.elapsed
        if ctx.floor_y is not None and l_used and pelvis_y == pelvis_y:
            pelvis_norm = (ctx.floor_y - pelvis_y) / l_used
        elif floor_ref is not None and l_used and pelvis_y == pelvis_y:
            pelvis_norm = (floor_ref - pelvis_y) / l_used
        else:
            pelvis_norm = NAN
        return TrackResult(
            track_id=ctx.track_id, t=t, posture=posture_out, mode=ctx.mode, alert=alert, events=events,
            features={key: feats[key] for key in FEATURE_KEYS},
            l_trunk_ref=l_used if l_used else NAN, pelvis_y_norm=pelvis_norm, descent_speed=descent,
            immobile_elapsed_s=elapsed, window_status=status, max_displacement=max_disp,
            fall_event_t_s=ctx.fall_event_t if ctx.fall_event_t is not None else NAN,
            instant_posture=pr.posture,
            posture_class=cls.name, posture_family=cls.family, posture_ko=cls.ko,
            posture_certainty=cls.certainty, posture_reason=cls.reason, posture_note=rule.get("note", "") or "",
            posture_held_s=held_s, instant_class=inst.name, recovery_stage=recovery_stage,
            floor_source=floor_src, pelvis_speed=speed,
            fall_type=ctx.fall_type, fall_metrics=ctx.fall_metrics,
            pre_fall_posture=ctx.pre_fall_posture, landing_posture=ctx.landing_posture,
        )

    def _gait(self, ctx, t, l_used):
        """보행 주기: 최근 gait_window_s 동안 양 발목의 상대 위치(왼 - 오른)가 번갈아 부호를 바꾸는지.

        측면에서 걸으면 가로(x) 차이가, 카메라 쪽으로 걸어오면 세로(y) 차이가 번갈아 바뀐다.
        두 방향 중 더 크게 변하는 쪽을 보고, 골반이 화면에서 움직이지 않아도(카메라가 따라감) 잡는다.
        """
        p = self.cfg["posture"]
        c = self.cfg["keypoint_conf_min"]
        if not l_used:
            return False
        d = [(s.kpts[L_ANKLE, :2] - s.kpts[R_ANKLE, :2]) / l_used
             for s in ctx.history.window(t, p["gait_window_s"])
             if s.kpts[L_ANKLE, 2] >= c and s.kpts[R_ANKLE, 2] >= c]
        if len(d) < 6:
            return False
        d = np.array(d)
        v = d[:, 0] if d[:, 0].var() >= d[:, 1].var() else d[:, 1]
        if v.max() - v.min() < p["gait_amp_min"]:
            return False
        a, side, changes = p["gait_alt_min"], 0, 0
        for x in v:
            now = 1 if x > a else (-1 if x < -a else 0)
            if now and side and now != side:
                changes += 1
            if now:
                side = now
        return changes >= p["gait_min_alternations"]

    def _pelvis_drop(self, ctx, t, l_used):
        """최근 slip_down_max_s(+깜빡임 방지 시간) 동안 골반이 가장 높던 곳에서 지금까지 내려온 거리 (몸통 길이 단위)."""
        span = self.cfg["fall_type"]["slip_down_max_s"] + self.cfg["posture"]["min_hold_s"]
        ys = [s.features.get("pelvis_y") for s in ctx.history.window(t, span)]
        ys = [y for y in ys if y is not None and y == y]
        if len(ys) < 2 or not l_used:
            return 0.0
        return (ys[-1] - min(ys)) / l_used


__all__ = ["FallCoreEngine", "TrackResult", "KO", "make_class"]
