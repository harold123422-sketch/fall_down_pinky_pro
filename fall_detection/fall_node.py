"""/camera/image_raw 를 받아 YOLO-pose로 관절을 찾고, 낙상 상태를 /fall_status 로 발행한다."""
import json
import time

import rclpy
from cv_bridge import CvBridge
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image
from std_msgs.msg import String
from ultralytics import YOLO

from fall_detection.pose_logic import FallJudge


class FallNode(Node):
    def __init__(self):
        super().__init__('fall_node')

        # 모델 이름만 쓰면 처음 실행할 때 자동 다운로드된다. 다른 모델은 -p model:=경로 로 지정
        self.declare_parameter('model', 'yolo11n-pose.pt')
        self.declare_parameter('imgsz', 480)         # 작을수록 빠르다 (CPU 환경)
        self.declare_parameter('person_conf', 0.4)   # 사람 검출 최소 신뢰도
        self.declare_parameter('show', False)        # True면 관절이 그려진 창을 띄운다

        self.model = YOLO(self.get_parameter('model').value)
        self.imgsz = self.get_parameter('imgsz').value
        self.person_conf = self.get_parameter('person_conf').value
        self.show = self.get_parameter('show').value

        self.bridge = CvBridge()
        self.judge = FallJudge()

        # 구독: 이미지가 올 때마다 on_image 가 호출된다
        self.sub = self.create_subscription(
            Image, '/camera/image_raw', self.on_image, qos_profile_sensor_data)
        # 발행: 판정 결과. 처음엔 JSON 문자열로 시작 (나중에 커스텀 메시지로 바꿀 수 있다)
        self.pub = self.create_publisher(String, '/fall_status', 10)

        self.last_state = None
        self.get_logger().info('fall_node 시작: /camera/image_raw -> /fall_status')

    def on_image(self, msg):
        frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        t = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9   # 카메라가 찍은 시각

        t0 = time.monotonic()
        result = self.model(frame, imgsz=self.imgsz, conf=self.person_conf, verbose=False)[0]
        infer_ms = (time.monotonic() - t0) * 1000

        state, person_conf = 'NO_PERSON', 0.0
        if result.keypoints is not None and len(result.boxes) > 0:
            # 여러 명이면 신뢰도가 가장 높은 한 명만 본다 (골격 버전. 다인 추적은 나중에)
            best = int(result.boxes.conf.argmax())
            kpts = result.keypoints.data[best].cpu().numpy()      # (17, 3): x, y, 신뢰도
            person_conf = float(result.boxes.conf[best])
            state = self.judge.update(t, kpts)

        out = String()
        out.data = json.dumps({
            'state': state,
            'person_conf': round(person_conf, 3),
            'stamp': round(t, 3),
            'infer_ms': round(infer_ms, 1),
        })
        self.pub.publish(out)

        if state != self.last_state:                  # 상태가 바뀔 때만 로그
            self.get_logger().info(f'상태 변경: {self.last_state} -> {state}')
            self.last_state = state

        if self.show:
            import cv2
            annotated = result.plot()      # 관절과 박스가 그려진 이미지 (한 번만 만들어서 재사용)
            angle = self.judge.history[-1][1] if self.judge.history else None
            label = f'{state}  angle={angle:.0f}' if angle is not None else state
            cv2.putText(annotated, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
            cv2.imshow('fall_node', annotated)
            key = cv2.waitKey(1) & 0xFF          # 눌린 키 (아무것도 안 누르면 255)
            if key in (ord('q'), 27):            # q 또는 ESC
                cv2.destroyAllWindows()
                raise KeyboardInterrupt          # main()의 except가 받아서 정상 종료한다


def main():
    rclpy.init()
    node = FallNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):   # Ctrl+C 또는 외부 종료 신호
        pass
    node.destroy_node()
    if rclpy.ok():           # 이미 종료됐으면 다시 끄지 않는다
        rclpy.shutdown()
