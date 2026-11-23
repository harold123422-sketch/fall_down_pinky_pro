"""thresholds.yaml 읽기."""
from pathlib import Path

import yaml

# 저장소 루트의 config/thresholds.yaml (소스에서 직접 실행할 때의 기본 위치)
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "config" / "thresholds.yaml"


def find_default_path():
    """소스 위치 -> ROS 설치 위치(share/fall_detection/config) 순서로 찾는다."""
    if DEFAULT_PATH.exists():
        return DEFAULT_PATH
    try:
        from ament_index_python.packages import get_package_share_directory
        p = Path(get_package_share_directory("fall_detection")) / "config" / "thresholds.yaml"
        if p.exists():
            return p
    except Exception:
        pass
    raise FileNotFoundError("thresholds.yaml 을 찾을 수 없습니다")


def load_thresholds(path=None):
    """임계값을 dict로 읽는다. 값을 바꿔 시험하려면 반환된 dict를 수정해서 쓰면 된다."""
    p = Path(path) if path else find_default_path()
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)
