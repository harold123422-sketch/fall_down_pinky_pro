"""위험 단계 (비위험 / 주의 / 위험). 경보 -> 단계 매핑은 config/thresholds.yaml 의 risk_levels."""
from enum import Enum


class Level(Enum):
    SAFE = 0       # 비위험
    CAUTION = 1    # 주의
    DANGER = 2     # 위험


LEVEL_KO = {Level.SAFE: "비위험", Level.CAUTION: "주의", Level.DANGER: "위험"}

# yaml에 risk_levels가 없을 때의 기본값
DEFAULT_MAP = {
    "NONE": "SAFE",
    "CHECK_STANDING_IMMOBILE": "CAUTION",
    "POST_FALL_MOVING": "CAUTION",
    "FALL_EVENT": "DANGER",
    "EMERGENCY_POST_FALL_IMMOBILE": "DANGER",
}


def level_for(alert_name, cfg=None):
    """경보 이름 -> Level."""
    table = (cfg or {}).get("risk_levels") or DEFAULT_MAP
    name = table.get(alert_name, DEFAULT_MAP.get(alert_name, "SAFE"))
    return Level[name]
