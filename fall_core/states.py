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


class Alert(Enum):         # 우선순위 높은 순 (숫자가 클수록 높음)
    EMERGENCY_POST_FALL_IMMOBILE = 7   # 긴급: 낙상 후 어떤 자세든 30초 무움직임
    POST_FALL_MOVING = 6               # 낙상 후 움직임 있음 (확인 필요)
    SELF_RECOVERABLE = 5               # 낙상 후 스스로 일어나는 경로 (팔꿈치 지지, 바닥 앉기, 네발, 무릎 서기)
    FALL_EVENT = 4                     # 낙상 사건 발생 (임시 규칙)
    CHECK_POSTURE_IMMOBILE = 3         # 평상시: 바닥 자세 등으로 오래 무움직임 (posture_risk.immobile_check_s)
    POSTURE_CAUTION = 2                # 평상시: 주의 자세가 이어짐 (posture_risk.caution_after_s)
    CHECK_STANDING_IMMOBILE = 1        # 확인 요청: 기립 30초 무움직임
    NONE = 0
    # 조절된 자세(쪼그림, 줍기)는 경보 없이 자세 이름으로만 표시 (posture_risk 의 note)
