#!/usr/bin/env python3
"""카메라 없이 터미널 모니터를 시험하는 데모: 가짜 자세로 시나리오를 돌려 /fall_status 를 발행한다.

시나리오: 서 있음(비위험) -> 가만히 30초(주의) -> 손 흔듦(비위험) -> 낙상(위험) -> 30초 정지(긴급) -> 일어남(회복)

  python3 tools/demo_status_publisher.py --speed 4      # 4배속 (30초 판정을 약 8초에 볼 수 있음)
  ros2 run fall_detection fall_monitor                   # 다른 터미널에서

fall_core_node 와 같은 /fall_status 를 발행하므로 실제 카메라 없이 화면과 단계 구분을 확인할 수 있다.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import rclpy  # noqa: E402
import synthetic_poses as sp  # noqa: E402
from std_msgs.msg import String  # noqa: E402

from fall_core import FallCoreEngine, load_thresholds  # noqa: E402
from fall_core.status import build_status  # noqa: E402


def scenario():
    """(설명, 시작 자세, 끝 자세, 걸리는 시간(가상 초)) 목록."""
    stand, lying = sp.standing(), sp.side_lying()
    waving = sp.shift(stand, (9, 10), 70, -90)
    return [
        ("서 있음", stand, stand, 20),
        ("계속 가만히 서 있음 (30초 넘으면 주의)", stand, stand, 15),
        ("손을 흔듦", stand, waving, 1.5), ("손을 흔듦", waving, stand, 1.5),
        ("서 있음", stand, stand, 4),
        ("낙상!", stand, lying, 0.6),
        ("쓰러진 채 가만히 있음 (30초 넘으면 긴급)", lying, lying, 36),
        ("스스로 일어남", lying, stand, 2),
        ("다시 서 있음 (회복)", stand, stand, 6),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=4.0, help="시간 배속 (기본 4배)")
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--loop", action="store_true", help="끝나면 처음부터 반복")
    a = ap.parse_args()

    rclpy.init()
    node = rclpy.create_node("demo_status_publisher")
    pub = node.create_publisher(String, "/fall_status", 10)
    cfg = load_thresholds()
    print(f"데모 시작 (x{a.speed:g}배속). 다른 터미널에서: ros2 run fall_detection fall_monitor")
    try:
        while rclpy.ok():
            engine, t = FallCoreEngine(cfg), 0.0
            dt_virtual = a.speed / a.fps
            for name, p0, p1, secs in scenario():
                print(f"  - {name}")
                steps = max(1, int(secs / dt_virtual))
                for i in range(steps):
                    t += dt_virtual
                    pose = sp.blend(p0, p1, (i + 1) / steps)
                    det = {"track_id": 1, "kpts": sp.jitter(pose, sp.np.random.default_rng(i), 1.0), "box_conf": 0.9}
                    res = engine.update(t, [det])
                    msg = String()
                    msg.data = json.dumps(build_status("demo", time.time(), [det], res, cfg), ensure_ascii=False)
                    pub.publish(msg)
                    time.sleep(1.0 / a.fps)
            if not a.loop:
                break
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == "__main__":
    main()
