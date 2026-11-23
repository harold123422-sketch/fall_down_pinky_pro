"""STANDING 판정 + 무움직임 + 낙상 후 경보를 묶는 엔진 (track_id별 상태 관리).

입력 : update(t, detections)   t = 프레임 타임스탬프(초)
        detections = [{"track_id": int, "kpts": (17,3) 배열, "box_conf": float}, ...]
출력 : track별 TrackResult 목록

[지시서에 없는 부분을 정한 가정] (모두 docs/SPEC_standing.md 와 README에 기록)
  1. POST_FALL에서 긴급이 한 번 발령되면(latched) 움직임이 생겨도 해제하지 않는다. RECOVERED 로만 해제.
  2. 낙상 직후 post_fall_settle_s 동안의 움직임은 '몸이 자리잡는 중'으로 보고 POST_FALL_MOVING으로 표시하지 않는다.
  3. POST_FALL_MOVING은 한 번 표시되면 RECOVERED/긴급 전까지 유지한다 ("사람이 확인할 때까지 유지").
  4. 소실된 POST_FALL track은 같은 위치에 새 track_id로 나타나면 이어 붙인다 (POST_FALL 상태만 대상).
"""
import math
from dataclasses import dataclass, field

import numpy as np

from fall_core.alerts import FallEventDetector, select_alert
from fall_core.history import Sample, TrackHistory
from fall_core.immobility import ImmobilityTimer, WindowStatus, evaluate_window
from fall_core.keypoints import L_ANKLE, L_HIP, R_ANKLE, R_HIP, as_kpts, midpoint
from fall_core.posture import FEATURE_KEYS, classify_posture
from fall_core.states import Alert, Mode, Posture

NAN = float("nan")


@dataclass
class TrackContext:
    track_id: int
    history: TrackHistory
    created_t: float
    last_seen_t: float
    timer: ImmobilityTimer = field(default_factory=ImmobilityTimer)            # 자세와 무관한 연속 무움직임
    standing_timer: ImmobilityTimer = field(default_factory=ImmobilityTimer)   # STANDING 중의 무움직임
    last_center: object = None
    last_l_trunk: float = None
    l_ref: float = None               # 최근 STANDING 구간의 trunk length (지수평균)
    floor_y: float = None             # 최근 STANDING 구간의 ankle 평균 y
    last_standing_t: float = None
    streak_start: float = None        # STANDING 조건이 연속으로 만족된 시작 시각
    confirmed_standing: bool = False
    held_posture: Posture = Posture.UNKNOWN
    mode: Mode = Mode.NORMAL
    fall_event_t: float = None
    latched: bool = False
    moving_seen: bool = False
    check_active: bool = False


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


def _center(k, conf_min):
    valid = k[:, 2] >= conf_min
    return k[valid, :2].mean(axis=0) if valid.any() else None


class FallCoreEngine:
    def __init__(self, cfg):
        self.cfg = cfg
        self.detector = FallEventDetector(cfg)
        self.tracks = {}
        f, i = cfg["fall_event"], cfg["immobility"]
        self.keep_s = max(i["window_s"], f["fall_max_duration_s"], f["fall_prior_standing_s"]) + 1.0

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

    def _step(self, ctx, t, det):
        cfg = self.cfg
        a = cfg["alerts"]
        conf_min = cfg["keypoint_conf_min"]
        events = []
        k = as_kpts(det["kpts"])

        # 관측이 끊겼다가 돌아오면 끊긴 시간은 무움직임으로 세지 않는다
        if t - ctx.last_seen_t > a["gap_resume_s"]:
            ctx.timer.resume(t)
            ctx.standing_timer.resume(t)
        ctx.last_seen_t = t

        # 1) 자세 (STANDING은 min_duration_s 이상 연속 만족해야 확정: 깜빡임 방지)
        pr = classify_posture(k, cfg)
        feats = pr.features
        if pr.posture == Posture.STANDING:
            if ctx.streak_start is None:
                ctx.streak_start = t
            if not ctx.confirmed_standing and t - ctx.streak_start >= cfg["standing"]["min_duration_s"]:
                ctx.confirmed_standing = True
        elif pr.posture == Posture.NOT_STANDING:
            ctx.streak_start, ctx.confirmed_standing = None, False
        # UNKNOWN: 이전 상태 유지
        if pr.posture != Posture.UNKNOWN:
            ctx.held_posture = Posture.STANDING if ctx.confirmed_standing else Posture.NOT_STANDING
        posture_out = Posture.UNKNOWN if pr.posture == Posture.UNKNOWN else ctx.held_posture

        # 2) 기준값 갱신 (STANDING 구간에서만): L_trunk_ref, floor, 마지막 STANDING 시각
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

        # 3) 샘플 기록
        hip_mid = midpoint(k, L_HIP, R_HIP, conf_min)
        pelvis_y = float(hip_mid[1]) if hip_mid is not None else NAN
        sample_feats = dict(feats)
        sample_feats["pelvis_y"] = pelvis_y
        ctx.history.add(Sample(t, k.copy(), sample_feats, posture_out))
        l_used = self._l_used(ctx, feats, t)

        # 4) 무움직임
        window = ctx.history.window(t, cfg["immobility"]["window_s"])
        status, max_disp, span = evaluate_window(window, l_used, cfg)
        ctx.timer.update(t, status, span)
        if ctx.held_posture == Posture.STANDING:
            ctx.standing_timer.update(t, status, span)
        else:
            ctx.standing_timer.reset(t)

        # 5) 낙상 사건
        descent = self.detector.descent_speed(ctx.history, t, l_used)
        fell = False
        if ctx.mode != Mode.POST_FALL:
            fell = self.detector.check(t, ctx.last_standing_t, descent, pelvis_y, ctx.floor_y, l_used)
            if fell:
                events.append("FALL_EVENT")
                ctx.mode = Mode.POST_FALL
                ctx.fall_event_t = t
                ctx.timer.reset(t)
                ctx.standing_timer.reset(t)
                ctx.latched, ctx.moving_seen, ctx.check_active = False, False, False

        # 6) POST_FALL 처리 / 기립 무움직임 확인
        if ctx.mode == Mode.POST_FALL and not fell:
            if (ctx.confirmed_standing and ctx.streak_start is not None
                    and t - ctx.streak_start >= a["recovery_standing_min_s"]):
                ctx.mode = Mode.RECOVERED
                ctx.latched, ctx.moving_seen = False, False
                events.append("RECOVERED")
            else:
                if status == WindowStatus.MOVING and t - ctx.fall_event_t >= a["post_fall_settle_s"]:
                    ctx.moving_seen = True
                if not ctx.latched and ctx.timer.elapsed >= a["post_fall_immobile_emergency_s"]:
                    ctx.latched = True
                    events.append("EMERGENCY_POST_FALL_IMMOBILE")
        if ctx.mode != Mode.POST_FALL:
            check_now = (ctx.held_posture == Posture.STANDING
                         and ctx.standing_timer.elapsed >= a["standing_immobile_check_s"])
            if check_now and not ctx.check_active:
                events.append("CHECK_STANDING_IMMOBILE")
            if ctx.check_active and not check_now:
                events.append("CHECK_CLEARED")
            ctx.check_active = check_now

        alert = select_alert(ctx.mode, ctx.latched, ctx.moving_seen, ctx.check_active)
        if ctx.mode == Mode.POST_FALL:
            elapsed = ctx.timer.elapsed
        else:
            elapsed = ctx.standing_timer.elapsed
        if ctx.floor_y is not None and l_used and pelvis_y == pelvis_y:
            pelvis_norm = (ctx.floor_y - pelvis_y) / l_used
        else:
            pelvis_norm = NAN
        return TrackResult(
            track_id=ctx.track_id, t=t, posture=posture_out, mode=ctx.mode, alert=alert, events=events,
            features={key: feats[key] for key in FEATURE_KEYS},
            l_trunk_ref=l_used if l_used else NAN, pelvis_y_norm=pelvis_norm, descent_speed=descent,
            immobile_elapsed_s=elapsed, window_status=status, max_displacement=max_disp,
            fall_event_t_s=ctx.fall_event_t if ctx.fall_event_t is not None else NAN,
            instant_posture=pr.posture,
        )
