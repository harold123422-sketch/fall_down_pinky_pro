"""카메라 영상을 /camera/image_raw 로 발행하는 노드.

입력은 USB 웹캠 번호(예: 2) 또는 영상 주소(예: 핑키 스트림 http://192.168.4.1:8000/video).

구조: 별도 스레드가 카메라에서 계속 읽어 '가장 최근 프레임'만 보관하고,
      타이머가 새 프레임이 있을 때만 발행한다.
      -> 옛 프레임이 쌓여 영상이 늦어지거나 끊기는 것을 막고,
         스트림이 끊겨도 자동으로 다시 접속한다.
"""
import os
import threading
import time

import cv2
import rclpy
from cv_bridge import CvBridge
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


class FrameReader(threading.Thread):
    """카메라를 계속 읽어서 최신 프레임 한 장만 유지한다. 실패하면 다시 연다."""

    def __init__(self, device, logger):
        super().__init__(daemon=True)
        self.device = device
        self.log = logger
        self.lock = threading.Lock()
        self.frame = None
        self.seq = 0               # 새 프레임이 들어올 때마다 1 증가
        self.t = 0.0               # 마지막 프레임을 받은 시각 (time.monotonic)
        self.running = True
        self.connected = False

    def _open(self):
        if isinstance(self.device, str) and not self.device.isdigit():
            # 스트림 지연 줄이기: FFmpeg가 영상을 오래 분석하며 프레임을 쌓아 두지 않도록 버퍼링/분석을 최소화.
            # (연결하는 몇 초 동안 쌓인 옛 프레임을 한꺼번에 읽으면 시작 직후 영상이 늦어지고 끊긴다)
            os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS",
                                  "fflags;nobuffer|flags;low_delay|probesize;32768|analyzeduration;0")
            cap = cv2.VideoCapture(self.device, cv2.CAP_FFMPEG)         # 주소
        else:
            cap = cv2.VideoCapture(int(self.device), cv2.CAP_V4L2)      # USB 웹캠 번호
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)                         # 가능하면 버퍼를 최소로
            return cap
        cap.release()
        return None

    def run(self):
        cap = None
        while self.running:
            if cap is None:
                cap = self._open()
                if cap is None:
                    if self.connected is not False:
                        self.log.warning(f'{self.device} 에 연결할 수 없습니다. 1초 뒤 다시 시도합니다')
                    self.connected = False
                    time.sleep(1.0)
                    continue
                self.connected = True
                self.log.info(f'{self.device} 연결됨')
            ok, frame = cap.read()
            if not ok:
                if self.running and rclpy.ok():          # 종료 중에는 로그를 남기지 않음
                    self.log.warning('프레임을 읽지 못했습니다. 다시 연결합니다')
                cap.release()
                cap = None
                self.connected = False
                time.sleep(0.5)
                continue
            with self.lock:
                self.frame = frame
                self.seq += 1
                self.t = time.monotonic()      # 이 프레임을 받은 시각
        if cap is not None:
            cap.release()

    def latest(self):
        with self.lock:
            return self.frame, self.seq

    def latest_full(self):
        """(프레임, 순번, 받은 시각). 시각이 필요한 노드(fall_core_node)용."""
        with self.lock:
            return self.frame, self.seq, self.t

    def stop(self):
        self.running = False
        self.join(timeout=2)


class CameraNode(Node):
    def __init__(self):
        super().__init__('camera_node')

        # 파라미터:
        #   ros2 run fall_detection camera_node --ros-args -p device:=2
        #   ros2 run fall_detection camera_node --ros-args -p device:=http://192.168.4.1:8000/video
        # device: 카메라 번호 또는 영상 주소 (두 타입 모두 허용하려고 dynamic_typing 사용)
        # fps: 발행 속도의 상한. 실제로는 카메라가 새 프레임을 주는 속도를 넘지 않는다
        self.declare_parameter('device', 2, ParameterDescriptor(dynamic_typing=True))
        self.declare_parameter('fps', 30.0)
        device = self.get_parameter('device').value
        fps = self.get_parameter('fps').value
        self.min_interval = 1.0 / fps

        self.bridge = CvBridge()   # OpenCV 이미지 <-> ROS Image 메시지 변환기
        # 카메라 영상은 센서용 QoS(최신 프레임 우선, 유실 허용)를 쓰는 게 관례다
        self.pub = self.create_publisher(Image, '/camera/image_raw', qos_profile_sensor_data)

        self.reader = FrameReader(device, self.get_logger())
        self.reader.start()
        self.last_seq = 0
        self.last_pub = 0.0
        self.timer = self.create_timer(1.0 / 60.0, self.tick)   # 60Hz로 확인만 하고, 새 프레임일 때만 발행
        self.get_logger().info(f'camera {device} -> /camera/image_raw (최대 {fps} fps)')

    def tick(self):
        frame, seq = self.reader.latest()
        if frame is None or seq == self.last_seq:
            return                                  # 새 프레임이 없음
        now = time.monotonic()
        if now - self.last_pub < self.min_interval * 0.9:
            return                                  # fps 상한 (이 프레임은 건너뜀, 다음엔 더 최신 프레임이 발행됨)
        self.last_seq = seq
        self.last_pub = now
        msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
        msg.header.stamp = self.get_clock().now().to_msg()   # 이 프레임의 시각 (나중에 분석에 중요)
        msg.header.frame_id = 'camera'
        self.pub.publish(msg)

    def destroy_node(self):
        self.reader.stop()
        super().destroy_node()


def main():
    rclpy.init()
    node = CameraNode()
    try:
        rclpy.spin(node)        # 종료될 때까지 타이머/콜백을 계속 돌린다
    except (KeyboardInterrupt, ExternalShutdownException):   # Ctrl+C 또는 외부 종료 신호
        pass
    node.destroy_node()
    if rclpy.ok():           # 이미 종료됐으면 다시 끄지 않는다
        rclpy.shutdown()
