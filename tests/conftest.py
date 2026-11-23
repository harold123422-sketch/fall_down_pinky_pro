import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))            # ROS 없이 fall_core를 바로 import
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fall_core.config import load_thresholds  # noqa: E402


@pytest.fixture
def cfg():
    """매 테스트마다 새 dict (테스트 안에서 값을 바꿔도 다른 테스트에 영향 없음)."""
    return load_thresholds(ROOT / "config" / "thresholds.yaml")
