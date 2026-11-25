"""낙상 사건(FALL_EVENT, 임시 규칙)과 경보 선택.

FALL_EVENT 임시 규칙 (모두 만족, 숫자는 임시값이며 IMU(Sacrum S2) 데이터로 확정 예정):
  F1. 직전 fall_prior_standing_s초 이내에 STANDING이었음
  F2. pelvis midpoint의 정규화 하강 속도 = delta(pelvis_y) / L_trunk_ref / delta_t >= descent_speed_min
      (이미지 y는 아래로 증가)
  F3. 하강 시작 후 fall_max_duration_s초 이내에 pelvis midpoint가 floor 기준선 근처에 도달
      floor 기준선 = 최근 STANDING 구간 ankle(15, 16) 평균 y
      근처 = |pelvis_y - floor_y| / L_trunk_ref <= pelvis_floor_max
조절된 하강(앉기, 눕기, 줍기)과 구분하는 핵심은 '하강 속도'다.

경보 우선순위: EMERGENCY_POST_FALL_IMMOBILE > POST_FALL_MOVING > FALL_EVENT > CHECK_STANDING_IMMOBILE > NONE
"""
import math

from fall_core.states import Alert, Mode


class FallEventDetector:
    def __init__(self, cfg):
        self.f = cfg["fall_event"]

    def descent_speed(self, history, t, l_ref):
        """최근 fall_max_duration_s 안에서 가장 큰 정규화 하강 속도 (몸통길이/초). 계산 불가면 nan."""
        if l_ref is None or not (l_ref > 1e-6) or len(history) == 0:
            return float("nan")
        recent = [s for s in history.window(t, self.f["fall_max_duration_s"])
                  if s.features.get("pelvis_y") is not None and not math.isnan(s.features["pelvis_y"])]
        if len(recent) < 2:
            return float("nan")
        now = recent[-1]
        best = float("nan")
        for s in recent[:-1]:
            dt = now.t - s.t
            if dt < self.f["descent_min_dt_s"]:
                continue
            v = (now.features["pelvis_y"] - s.features["pelvis_y"]) / l_ref / dt
            if math.isnan(best) or v > best:
                best = v
        return best

    def check(self, t, last_standing_t, descent_speed, pelvis_y, floor_y, l_ref):
        """F1~F3를 모두 만족하면 True."""
        f = self.f
        if last_standing_t is None or t - last_standing_t > f["fall_prior_standing_s"]:
            return False                                                     # F1
        if math.isnan(descent_speed) or descent_speed < f["descent_speed_min"]:
            return False                                                     # F2
        if floor_y is None or l_ref is None or math.isnan(pelvis_y):
            return False
        return abs(pelvis_y - floor_y) / l_ref <= f["pelvis_floor_max"]      # F3


def select_alert(mode, latched, moving_seen, check_active,
                 self_recovering=False, posture_check=False, posture_caution=False):
    """한 track에 한 번에 가장 높은 경보 하나만 돌려준다.

    낙상 후(POST_FALL): 긴급(한 번 발령되면 회복 전까지 유지) > 스스로 일어나는 중(처음 자리 잡은 자세보다 회복 단계가 올라감)
                        > 움직임 있음 > 낙상 직후
    평상시           : 자세 무움직임 확인 > 주의 자세 > 기립 무움직임 확인 > 없음
    """
    if mode == Mode.POST_FALL:
        if latched:
            return Alert.EMERGENCY_POST_FALL_IMMOBILE
        if self_recovering:
            return Alert.SELF_RECOVERABLE
        return Alert.POST_FALL_MOVING if moving_seen else Alert.FALL_EVENT
    if posture_check:
        return Alert.CHECK_POSTURE_IMMOBILE
    if posture_caution:
        return Alert.POSTURE_CAUTION
    return Alert.CHECK_STANDING_IMMOBILE if check_active else Alert.NONE
