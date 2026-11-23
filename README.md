# fall_down_pinky_pro

YOLO-pose로 사람의 관절을 찾아 **넘어짐 의심 상태**를 판정하는 ROS 2 노드입니다.
Pinky Pro 팀 프로젝트의 낙상 감지 비전 파트이며, 현재는 **뼈대(skeleton) 단계**입니다.

> 판정은 보조 정보입니다. 최종 판단은 사람(관제·구조대)이 합니다.

## 구성

```
[camera_node] --/camera/image_raw--> [fall_node] --/fall_status--> 관제, 로봇, 터미널
   웹캠 → ROS 이미지            YOLO-pose + 판정
                                     ↑
                           pose_logic.py (ROS와 무관한 판정 규칙)
```

| 노드 | 역할 |
|---|---|
| `camera_node` | USB 웹캠 영상을 `/camera/image_raw`로 발행 (실제 핑키 카메라 대용) |
| `fall_node` | 이미지를 구독해 YOLO-pose로 관절을 찾고, 상태를 `/fall_status`로 발행 |

## 현재 판정 상태

| 상태 | 의미 | 구현 |
|---|---|---|
| `NO_PERSON` | 사람이 보이지 않음 | 완료 |
| `NORMAL` | 정상 | 완료 |
| `SUSPECT` | 몸통이 누운 자세 (확인 필요) | 완료 (몸통 각도 ≥ 60°) |
| `FALL` | 급하강 + 누움 | **미구현** (`pose_logic.py`의 `decide()`) |
| `NEEDS_HELP` | 넘어진 뒤 정지 | **미구현** |

몸통 각도는 골반 중점 → 어깨 중점 선이 수직선과 이루는 각도입니다 (0° 서 있음, 90° 누움).
60°라는 기준값은 임시값이며 영상으로 조정해야 합니다.

## 요구 사항

- Ubuntu + ROS 2 Jazzy
- Python 3.12, `ultralytics`, `opencv-python`, `numpy` (`cv_bridge`는 ROS 패키지)
- 웹캠 1대
- 모델: `yolo11n-pose.pt` (처음 실행할 때 자동 다운로드)

## 빌드

```bash
cd ~/ros2_ws/src
git clone <이 저장소 주소> fall_detection
cd ~/ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-select fall_detection --symlink-install
source install/setup.bash
```

## 실행

```bash
# 터미널 1: 웹캠 (device는 /dev/videoN 의 N)
ros2 run fall_detection camera_node --ros-args -p device:=0

# 터미널 2: 낙상 노드 (show:=true 면 관절이 그려진 창, q 또는 ESC로 종료)
ros2 run fall_detection fall_node --ros-args -p show:=true

# 터미널 3: 결과 확인
ros2 topic echo /fall_status
```

`/fall_status` 출력 예:

```json
{"state": "NORMAL", "person_conf": 0.91, "stamp": 1795420243.27, "infer_ms": 23.1}
```

### 파라미터

| 노드 | 파라미터 | 기본값 | 설명 |
|---|---|---|---|
| `camera_node` | `device` | 2 | 카메라 번호 |
| `camera_node` | `fps` | 30.0 | 발행 주기 |
| `fall_node` | `model` | `yolo11n-pose.pt` | 모델 파일 |
| `fall_node` | `imgsz` | 480 | 입력 크기 (작을수록 빠름) |
| `fall_node` | `person_conf` | 0.4 | 사람 검출 최소 신뢰도 |
| `fall_node` | `show` | false | 화면 표시 |

## 알려진 한계

- 화면(2D) 기준 각도라서, 카메라 쪽으로 쓰러지면 각도가 작게 나옵니다.
- 여러 명이 있으면 신뢰도가 가장 높은 한 명만 판정합니다.
- 상태가 `NORMAL`과 `NO_PERSON` 사이에서 깜빡일 수 있습니다 (연속 프레임 필터 없음).
- 실제 핑키 카메라 토픽 이름은 `/camera/image_raw`로 가정했으며 확인이 필요합니다.
- GPU 없이 CPU에서 동작 확인 (yolo11n-pose 기준).

## 라이선스

이 저장소의 코드는 Apache-2.0입니다 (`LICENSE`).
`ultralytics`는 AGPL-3.0이므로, 배포나 상업적 사용 전에 라이선스를 확인하세요.
