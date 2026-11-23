"""USB 웹캠 영상을 /camera/image_raw 로 발행하는 노드.

실제 핑키 카메라가 연결되기 전에, 외부 웹캠을 핑키 카메라 대신 쓰기 위한 노드다.
"""
import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image


class CameraNode(Node):
    def __init__(self):
        super().__init__('camera_node')

        # 파라미터: 실행할 때 바깥에서 바꿀 수 있는 설정값
        #   ros2 run fall_detection camera_node --ros-args -p device:=2
        self.declare_parameter('device', 2)      # /dev/video2 = USB2.0 PC CAMERA
        self.declare_parameter('fps', 30.0)
        device = self.get_parameter('device').value
        fps = self.get_parameter('fps').value

        self.cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            raise RuntimeError(f'카메라 {device}번을 열 수 없습니다')

        self.bridge = CvBridge()   # OpenCV 이미지 <-> ROS Image 메시지 변환기
        # 카메라 영상은 센서용 QoS(최신 프레임 우선, 유실 허용)를 쓰는 게 관례다
        self.pub = self.create_publisher(Image, '/camera/image_raw', qos_profile_sensor_data)
        self.timer = self.create_timer(1.0 / fps, self.tick)   # 1/fps초마다 tick 호출
        self.get_logger().info(f'camera {device} -> /camera/image_raw ({fps} fps)')

    def tick(self):
        ok, frame = self.cap.read()
        if not ok:
            self.get_logger().warning('프레임을 읽지 못했습니다')
            return
        msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
        msg.header.stamp = self.get_clock().now().to_msg()   # 이 프레임의 시각 (나중에 분석에 중요)
        msg.header.frame_id = 'camera'
        self.pub.publish(msg)

    def destroy_node(self):
        self.cap.release()
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
