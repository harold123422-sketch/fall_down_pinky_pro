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

## 실행 순서 (처음부터 끝까지)

### 0. 준비 (한 번만)

```bash
# 파이썬 패키지 설치 (이미 있으면 건너뜀)
pip install ultralytics opencv-python numpy

# 저장소 받기: ROS 작업공간의 src 안에 fall_detection 이라는 폴더 이름으로 받는다
cd ~/ros2_ws/src
git clone <이 저장소 주소> fall_detection
```

### 1. 빌드 (코드를 처음 받았거나 setup.py를 고쳤을 때)

```bash
cd ~/ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --packages-select fall_detection --symlink-install
```

`--packages-select`는 이 패키지만 빌드한다는 뜻입니다 (작업공간 전체 빌드는 오래 걸림).
`--symlink-install`을 쓰면 이후 `.py` 코드를 고쳐도 다시 빌드할 필요가 없습니다.

### 2. 카메라 번호 확인

```bash
ls /dev/video*
```

`/dev/video0`이면 번호는 `0`입니다. 노트북 내장 카메라가 보통 0이고, 외부 USB 웹캠은 2 이상일 수 있습니다.
같은 카메라가 번호 2개로 보일 수 있으니, 안 열리면 다음 번호를 시도하세요.

### 3. 실행 (터미널 3개)

**새 터미널을 열 때마다** 아래 두 줄을 먼저 실행해야 합니다.

```bash
source /opt/ros/jazzy/setup.bash
source ~/ros2_ws/install/setup.bash
```

| 순서 | 터미널 | 명령 | 하는 일 |
|---|---|---|---|
| 1 | 터미널 1 | `ros2 run fall_detection camera_node --ros-args -p device:=0` | 웹캠 영상을 `/camera/image_raw`로 발행 |
| 2 | 터미널 2 | `ros2 run fall_detection fall_node --ros-args -p show:=true` | 관절 인식 + 상태 판정, 화면 표시 |
| 3 | 터미널 3 | `ros2 topic echo /fall_status` | 상태가 흐르는 것을 확인 |

- 터미널 1(카메라)을 **먼저** 켜고, 2~3초 뒤에 터미널 2를 켭니다.
- 터미널 2를 처음 실행하면 `yolo11n-pose.pt`(약 6MB)를 자동 다운로드합니다. 인터넷 연결이 필요하고, 완료될 때까지 수십 초 걸릴 수 있습니다.
- `device:=0`의 숫자는 2단계에서 확인한 번호로 바꿉니다.

### 4. 동작 확인

| 자세 | 화면의 상태 | 몸통 각도(angle) |
|---|---|---|
| 서 있기 | `NORMAL` | 0° 근처 |
| 숙이기, 물건 줍기 | `NORMAL` | 30~50° |
| 옆으로 눕기 | `SUSPECT` | 90° 근처 |
| 화면에 사람 없음 | `NO_PERSON` | - |

### 5. 종료

- **fall_node**: 화면 창을 클릭한 뒤 `q` 또는 `ESC`, 또는 터미널에서 `Ctrl+C`
- **camera_node**: 해당 터미널에서 `Ctrl+C`
- 터미널을 못 찾겠을 때 한 번에 끄기:

```bash
pkill -INT -f "fall_detection/(camera_node|fall_node)"
```

### 문제가 생겼을 때

| 증상 | 원인과 해결 |
|---|---|
| `Package 'fall_detection' not found` | 3단계의 `source` 두 줄을 실행하지 않았거나 빌드를 안 함 |
| `카메라 N번을 열 수 없습니다` | 카메라 번호가 틀렸거나 다른 프로그램이 카메라를 사용 중. 2단계로 번호 다시 확인 |
| 창이 안 뜸 | `-p show:=true`를 빼먹음. SSH 접속이면 화면 표시가 안 될 수 있음 |
| `/fall_status`가 안 나옴 | 터미널 1(카메라)이 꺼져 있거나, 첫 실행 모델 다운로드가 아직 진행 중 |
| 상태가 `NORMAL`과 `NO_PERSON`을 오감 | 알려진 한계 (연속 프레임 필터 없음) |
| 느림 | `-p imgsz:=320`으로 입력 크기를 줄여 보기 |

### 출력 형식

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
