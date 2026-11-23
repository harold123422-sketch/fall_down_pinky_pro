"""무움직임(Immobility) 판정.

임상적 정의: 의도적 움직임(voluntary movement)이 관찰되지 않는 상태.
카메라 판정: 대상 keypoint(nose, 양 wrist, 양 shoulder, pelvis midpoint, 양 ankle) 각각의
  시간 창(window_s) 내 최대 변위(점들 사이 최대 거리) / L_trunk_ref 가 모두 displacement_max 미만이면
  그 창은 '무움직임'.

- 시간은 프레임 수가 아니라 타임스탬프(초)로 계산한다 (CPU에서 FPS가 변동).
- 신뢰도 낮은 keypoint는 변위 계산에서 제외. 남은 대상이 min_valid_keypoint_ratio 미만이면 판정 보류
  (타이머는 멈추지만 초기화하지 않는다).
- 정상 기립에서도 COM은 수 mm~수 cm 흔들린다(postural sway). displacement_max는 이보다 커야 한다.
"""
from enum import Enum

import numpy as np

from fall_core.keypoints import (L_ANKLE, L_HIP, L_SHOULDER, L_WRIST, NOSE, R_ANKLE, R_HIP,
                                 R_SHOULDER, R_WRIST, midpoint)

TARGET_NAMES = ("nose", "wrist_L", "wrist_R", "shoulder_L", "shoulder_R", "pelvis", "ankle_L", "ankle_R")


class WindowStatus(Enum):
    MOVING = 0
    IMMOBILE = 1
    INDETERMINATE = 2     # 판정 보류 (데이터 부족, 신뢰도 낮음, 기준 길이 없음)


def target_points(k, conf_min):
    """한 프레임의 대상 지점. 신뢰도가 낮으면 None."""
    def pt(i):
        return k[i, :2] if k[i, 2] >= conf_min else None
    return {
        "nose": pt(NOSE),
        "wrist_L": pt(L_WRIST), "wrist_R": pt(R_WRIST),
        "shoulder_L": pt(L_SHOULDER), "shoulder_R": pt(R_SHOULDER),
        "pelvis": midpoint(k, L_HIP, R_HIP, conf_min),
        "ankle_L": pt(L_ANKLE), "ankle_R": pt(R_ANKLE),
    }


def _diameter(points):
    p = np.asarray(points, dtype=float)
    d = p[:, None, :] - p[None, :, :]
    return float(np.sqrt((d ** 2).sum(-1)).max())


def evaluate_window(samples, l_ref, cfg):
    """시간 창 안의 샘플들로 움직임 여부를 판정한다.

    반환: (WindowStatus, 최대 정규화 변위, 창이 덮는 시간(초))
    """
    im = cfg["immobility"]
    conf_min = cfg["keypoint_conf_min"]
    if l_ref is None or not (l_ref > 1e-6) or len(samples) < 2:
        return WindowStatus.INDETERMINATE, float("nan"), 0.0
    span = samples[-1].t - samples[0].t
    if span < im["window_s"] * im["min_window_fill"]:
        return WindowStatus.INDETERMINATE, float("nan"), span     # 창이 아직 덜 찼음

    tracks = {name: [] for name in TARGET_NAMES}
    for s in samples:
        for name, p in target_points(s.kpts, conf_min).items():
            if p is not None:
                tracks[name].append(p)
    disp = {name: _diameter(pts) / l_ref for name, pts in tracks.items() if len(pts) >= 2}
    if len(disp) / len(TARGET_NAMES) < im["min_valid_keypoint_ratio"]:
        return WindowStatus.INDETERMINATE, float("nan"), span
    max_disp = max(disp.values())
    status = WindowStatus.MOVING if max_disp >= im["displacement_max"] else WindowStatus.IMMOBILE
    return status, max_disp, span


class ImmobilityTimer:
    """무움직임이 연속된 시간을 센다. 움직임이 보이면 0으로 초기화, 판정 보류 구간은 멈춘다."""

    def __init__(self):
        self.elapsed = 0.0
        self.active = False
        self.last_t = None

    def reset(self, t=None):
        self.elapsed, self.active, self.last_t = 0.0, False, t

    def resume(self, t):
        """관측이 끊겼다가 돌아왔을 때: 끊긴 시간은 세지 않는다."""
        self.last_t = t

    def update(self, t, status, span_s=0.0):
        dt = 0.0 if self.last_t is None else max(0.0, t - self.last_t)
        self.last_t = t
        if status == WindowStatus.MOVING:
            self.elapsed, self.active = 0.0, False
        elif status == WindowStatus.IMMOBILE:
            if not self.active:
                self.active = True
                self.elapsed = span_s       # 창 전체가 이미 정지였으므로 그만큼 인정
            else:
                self.elapsed += dt
        # INDETERMINATE: 그대로 둔다 (멈춤)
        return self.elapsed
