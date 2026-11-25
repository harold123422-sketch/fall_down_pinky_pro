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
from fall_core.incident import IncidentManager  # noqa: E402
from fall_core.status import build_status  # noqa: E402
from fall_core.voice_out import VoiceOut  # noqa: E402


def scenario():
    """(설명, 시작 자세, 끝 자세, 걸리는 시간(가상 초)) 목록."""
    stand, lying = sp.standing(), sp.side_lying()
    waving = sp.shift(stand, (9, 10), 70, -90)
    elbow, side_sit, quad, half = sp.side_lying_on_elbow(), sp.sit_floor_side(), sp.quadruped(), sp.kneel_half_left()
    return [
        ("서 있음", stand, stand, 20),
        ("계속 가만히 서 있음 (30초 넘으면 주의)", stand, stand, 15),
        ("손을 흔듦", stand, waving, 1.5), ("손을 흔듦", waving, stand, 1.5),
        ("서 있음", stand, stand, 4),
        ("낙상!", stand, lying, 0.6),
        ("쓰러진 채 가만히 있음 (30초: 음성 질문 -> 10초 무반응: 보고 예고 -> 10초 뒤 보고)", lying, lying, 56),
        ("팔꿈치로 상체를 듦 (회복 2단계)", lying, elbow, 1.5), ("팔꿈치 지지 측와위", elbow, elbow, 4),
        ("측좌위로 앉음 (회복 3단계)", elbow, side_sit, 1.5), ("측좌위", side_sit, side_sit, 4),
        ("네발 자세 (회복 4단계)", side_sit, quad, 1.5), ("사지 착지", quad, quad, 4),
        ("반무릎 서기 (회복 5단계)", quad, half, 1.5), ("반무릎 서기", half, half, 4),
        ("일어섬 (회복 6단계)", half, stand, 1.5), ("다시 서 있음 (회복 확인)", stand, stand, 6),
        ("천천히 바닥에 누움 (낙상 아님)", stand, lying, 4), ("바닥에 누워 있음 (5초 넘으면 주의)", lying, lying, 8),
        ("무릎을 가슴으로 당김 (태아 자세)", lying, sp.lying_fetal(), 1.5), ("태아 자세", sp.lying_fetal(), sp.lying_fetal(), 6),
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=4.0, help="시간 배속 (기본 4배)")
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--loop", action="store_true", help="끝나면 처음부터 반복")
    ap.add_argument("--voice", default="off", choices=["off", "pc", "pinky", "both"],
                    help="음성 출력 (기본 off: 문장은 /pinky_voice 토픽과 터미널에만)")
    ap.add_argument("--robot-say-url", default="http://192.168.4.1:8000/say")
    a = ap.parse_args()

    rclpy.init()
    node = rclpy.create_node("demo_status_publisher")
    pub = node.create_publisher(String, "/fall_status", 10)
    pubs = {"voice": node.create_publisher(String, "/pinky_voice", 10),
            "control": node.create_publisher(String, "/fall_report", 10),
            "guardian": node.create_publisher(String, "/guardian_alert", 10)}
    voice = VoiceOut(a.voice, a.robot_say_url, log=lambda s: print("   ", s),
                     style=load_thresholds().get("voice_style"))
    cfg = load_thresholds()
    print(f"데모 시작 (x{a.speed:g}배속). 다른 터미널에서: ros2 run fall_detection fall_monitor")
    try:
        while rclpy.ok():
            engine, t = FallCoreEngine(cfg), 0.0
            incidents = IncidentManager(cfg, "demo")
            dt_virtual = a.speed / a.fps
            for name, p0, p1, secs in scenario():
                print(f"  - {name}")
                steps = max(1, int(secs / dt_virtual))
                for i in range(steps):
                    t += dt_virtual
                    pose = sp.blend(p0, p1, (i + 1) / steps)
                    det = {"track_id": 1, "kpts": sp.jitter(pose, sp.np.random.default_rng(i), 1.0), "box_conf": 0.9}
                    res = engine.update(t, [det])
                    for act in incidents.update(t, time.time(), res):       # 응급 대응 순서
                        out = String()
                        out.data = json.dumps({"text": act.text, **act.data}, ensure_ascii=False)
                        pubs[act.kind].publish(out)
                        if act.kind == "voice":
                            voice.say(act.text, key=act.data.get("key"))
                    msg = String()
                    msg.data = json.dumps(build_status("demo", time.time(), [det], res, cfg,
                                                       incidents=incidents.summaries(t)), ensure_ascii=False)
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
