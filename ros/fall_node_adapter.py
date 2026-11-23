"""fall_core를 호출하는 ROS 노드. 기존 fall_detection/fall_node.py 는 건드리지 않고 별도 노드로 추가했다.

구조 (영상이 끊기는 문제를 줄이기 위한 설계)
  - 이 노드가 카메라/스트림을 '직접' 읽는다 (camera_node -> ROS 이미지 토픽 -> fall_node 의 중간 전송 없음).
  - 읽기 스레드: 항상 최신 프레임만 보관 (옛 프레임이 쌓여서 영상이 늦어지는 것을 막음, 끊기면 자동 재접속)
  - 메인 스레드: 가장 최근 프레임만 YOLO 처리 -> 추적 -> fall_core -> 화면 표시. 처리가 느리면 중간 프레임은 건너뜀.
  - 화면 아래에 읽기 fps, 처리 fps, YOLO ms, 지연(프레임이 찍힌 뒤 화면에 나오기까지)을 표시한다.

/fall_status (std_msgs/String, JSON) 출력 형식은 fall_core/status.py 참고.
  state=가장 높은 경보 이름(없으면 NONE, 사람이 없으면 NO_PERSON), level=SAFE|CAUTION|DANGER (비위험|주의|위험),
  tracks=[{track_id, posture, mode, alert, level, ..., kpts(17점)}].
  터미널 대시보드는 `ros2 run fall_detection fall_monitor` 로 본다.
"""
import json
import time

import cv2
import rclpy
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String
from ultralytics import YOLO

from fall_core import FallCoreEngine, load_thresholds
from fall_core.iou_tracker import IoUTracker
from fall_core.status import build_status
from fall_core.viz import draw_tracks
from fall_core.yolo_io import build_detections, parse_result
from fall_detection.camera_node import FrameReader


class FallCoreNode(Node):
    def __init__(self):
        super().__init__("fall_core_node")
        self.declare_parameter("source", 2, ParameterDescriptor(dynamic_typing=True))   # 번호 또는 http 주소
        self.declare_parameter("model", "yolo11n-pose.pt")
        self.declare_parameter("imgsz", 480)
        self.declare_parameter("person_conf", 0.4)
        self.declare_parameter("show", True)
        self.declare_parameter("thresholds", "")
        self.declare_parameter("camera_id", "cam0")
        self.declare_parameter("publish_keypoints", True)
        self.declare_parameter("stats_interval_s", 5.0)
        p = self.get_parameter
        self.source = p("source").value
        self.imgsz = p("imgsz").value
        self.person_conf = p("person_conf").value
        self.show = p("show").value
        self.camera_id = p("camera_id").value
        self.publish_keypoints = p("publish_keypoints").value
        self.stats_interval = p("stats_interval_s").value

        thr = p("thresholds").value
        self.cfg = load_thresholds(thr or None)
        self.engine = FallCoreEngine(self.cfg)
        self.tracker = IoUTracker()
        self.model = YOLO(p("model").value)
        self.pub = self.create_publisher(String, "/fall_status", 10)
        self.reader = FrameReader(self.source, self.get_logger())
        self.get_logger().info(f"fall_core_node: source={self.source} -> /fall_status (q 또는 ESC로 종료)")

    def run(self):
        self.reader.start()
        conf_min = self.cfg["keypoint_conf_min"]
        last_seq, n_proc, infer_sum = 0, 0, 0.0
        stats_t, stats_seq = time.monotonic(), 0
        footer, last_img, last_new = "", None, time.monotonic()
        while rclpy.ok():
            frame, seq, tcap = self.reader.latest_full()
            if frame is None or seq == last_seq:                 # 새 프레임이 없으면 잠깐 쉼
                if self.show:
                    if last_img is not None and time.monotonic() - last_new > 1.0:
                        stale = last_img.copy()
                        cv2.putText(stale, "NO SIGNAL (reconnecting...)", (10, 60), cv2.FONT_HERSHEY_SIMPLEX,
                                    0.8, (0, 0, 255), 2, cv2.LINE_AA)
                        cv2.imshow("fall_core", stale)
                    if cv2.waitKey(5) & 0xFF in (ord("q"), 27):
                        break
                else:
                    time.sleep(0.005)
                rclpy.spin_once(self, timeout_sec=0)
                continue
            last_seq, last_new = seq, time.monotonic()

            t0 = time.monotonic()
            res = self.model(frame, imgsz=self.imgsz, conf=self.person_conf, verbose=False)[0]
            infer_ms = (time.monotonic() - t0) * 1000
            boxes, confs, kpts = parse_result(res)
            ids = self.tracker.update(boxes, tcap)
            dets = build_detections(ids, boxes, confs, kpts)
            results = self.engine.update(tcap, dets)

            msg = String()
            msg.data = json.dumps(build_status(self.camera_id, self.get_clock().now().nanoseconds * 1e-9,
                                               dets, results, self.cfg, self.publish_keypoints), ensure_ascii=False)
            self.pub.publish(msg)
            for r in results:
                for e in r.events:
                    self.get_logger().info(f"[ID{r.track_id}] {e}")

            n_proc += 1
            infer_sum += infer_ms
            now = time.monotonic()
            if now - stats_t >= self.stats_interval:                # 속도 통계 (끊김 진단용)
                dt = now - stats_t
                cap_fps, proc_fps = (seq - stats_seq) / dt, n_proc / dt
                footer = (f"capture {cap_fps:.1f} fps | processed {proc_fps:.1f} fps | "
                          f"YOLO {infer_sum / n_proc:.0f} ms | latency {(now - tcap) * 1000:.0f} ms")
                self.get_logger().info(footer)
                stats_t, stats_seq, n_proc, infer_sum = now, seq, 0, 0.0

            if self.show:
                last_img = draw_tracks(frame.copy(), dets, results, conf_min, footer=footer)
                cv2.imshow("fall_core", last_img)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
            rclpy.spin_once(self, timeout_sec=0)

        self.reader.stop()
        cv2.destroyAllWindows()


def main():
    rclpy.init()
    node = FallCoreNode()
    try:
        node.run()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.reader.stop()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
