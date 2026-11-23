"""상태 Enum. 확장용 자리 포함."""
from enum import Enum


class Posture(Enum):
    UNKNOWN = 0
    STANDING = 1
    NOT_STANDING = 2
    # 이후 추가 예정 (지금은 정의만, 미구현):
    # SITTING, KNEELING_BILATERAL, HALF_KNEELING, QUADRUPED,
    # DEEP_SQUAT, SIDE_LYING, SUPINE, PRONE


class Mode(Enum):          # track_id별 모드
    NORMAL = 0
    POST_FALL = 1
    RECOVERED = 2


class Alert(Enum):         # 우선순위 높은 순
    EMERGENCY_POST_FALL_IMMOBILE = 4   # 긴급: 낙상 후 어떤 자세든 30초 무움직임
    POST_FALL_MOVING = 3               # 낙상 후 움직임 있음 (확인 필요)
    FALL_EVENT = 2                     # 낙상 사건 발생 (임시 규칙)
    CHECK_STANDING_IMMOBILE = 1        # 확인 요청: 기립 30초 무움직임
    NONE = 0
    # 이후 추가 예정:
    # SELF_RECOVERABLE (bilateral kneeling, quadruped, 상지 체중지지)
    # CONTROLLED_POSTURE (deep squat, 줍기, child's pose)
