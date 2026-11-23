"""낙상 감지 코어 (순수 Python: numpy, PyYAML만 사용, ROS 의존성 없음).

영상 파일 테스트(tools/run_video.py)와 ROS 노드(ros/fall_node_adapter.py)가 같은 코드를 공유한다.
"""
from fall_core.config import load_thresholds
from fall_core.engine import FallCoreEngine, TrackResult
from fall_core.states import Alert, Mode, Posture

__all__ = ["load_thresholds", "FallCoreEngine", "TrackResult", "Alert", "Mode", "Posture"]
