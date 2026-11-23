# fall_down_pinky_pro

Pinky Pro 팀 프로젝트의 **낙상 감지 비전 파트**입니다. YOLO-pose(COCO 17 관절)로 사람의 자세를 규칙 기반으로
판정하고, 낙상 후 무움직임을 **비위험 / 주의 / 위험** 단계로 알립니다. ROS 2 Jazzy 패키지 이름은 `fall_detection`입니다.

> 판정은 보조 정보입니다. 최종 판단은 사람(관제·구조대)이 합니다.
> 모든 임계값은 합성 자세로만 시험했고 실제 영상·IMU 데이터로는 아직 정하지 않았습니다.

## 전체 구조

```
[핑키 카메라] --pinky_stream.py--> http://<핑키>:8000/video (MJPEG)
                                        │  WiFi
                                        ▼
                        [PC] fall_core_node : 영상 읽기 → YOLO-pose → 추적 → fall_core 판정 → 화면 창
                                        │  /fall_status (JSON)
                                        ▼
                        [PC] fall_monitor  : 터미널에 상태 한 줄 + 변화 멘트 (비위험/주의/위험)
```

YOLO는 **PC CPU**에서 돌고, 핑키는 영상만 보냅니다. 영상이 HTTP로 오므로 PC와 핑키의 ROS 도메인을 맞출 필요가 없습니다.

## 빠른 시작 (핑키 카메라)

PC가 핑키 와이파이(`pinky_XXXX`)에 연결된 상태에서 진행합니다.

**① 핑키: 카메라 스트림 켜기** (Jupyter `http://192.168.4.1:8888` → Kernel → Shut Down All Kernels → New → Terminal)

`robot/pinky_stream.py`를 핑키 홈 폴더에 올려 둔 뒤 (Jupyter Upload 또는 `scp robot/pinky_stream.py pinky@192.168.4.1:~/`):

```bash
nohup python3 ~/pinky_stream.py > ~/stream.log 2>&1 &     # 끄기: pkill -f pinky_stream.py
```

확인: PC 브라우저에서 `http://192.168.4.1:8000/snapshot` 에 사진이 나오면 OK.

**② PC 터미널 1: YOLO 판정 노드 (영상 창이 뜸, 창에서 `q`로 종료)**

```bash
source /opt/ros/jazzy/setup.bash && source ~/ros2_ws/install/setup.bash
ros2 run fall_detection fall_core_node --ros-args \
    -p source:=http://192.168.4.1:8000/video -p model:=/절대경로/yolo11n-pose.pt
```

**③ PC 터미널 2: 터미널 모니터**

```bash
source /opt/ros/jazzy/setup.bash && source ~/ros2_ws/install/setup.bash
ros2 run fall_detection fall_monitor
```

- 노트북 웹캠으로 하려면 ②에서 `-p source:=0` (카메라 번호는 `ls /dev/video*`로 확인)
- 핑키 와이파이에는 인터넷이 없으므로 모델은 이름이 아니라 **절대 경로**로 지정하세요
- 카메라 없이 화면만 보려면 ② 대신 `python3 tools/demo_status_publisher.py --speed 4`

## 설치

```bash
cd ~/ros2_ws/src
git clone https://github.com/<계정>/fall_down_pinky_pro.git fall_detection     # 폴더 이름을 fall_detection 으로
cd fall_detection && pip install -r requirements.txt
cd ~/ros2_ws && source /opt/ros/jazzy/setup.bash
rosdep install --from-paths src/fall_detection --ignore-src -y
colcon build --packages-select fall_detection --symlink-install
```

`--symlink-install`로 빌드하면 이후 `.py`를 고쳐도 다시 빌드할 필요가 없습니다 (`setup.py`를 고쳤을 때만 다시 빌드).

## 실행 파일

| 이름 | 실행 | 하는 일 |
|---|---|---|
| `fall_core_node` | `ros2 run fall_detection fall_core_node` | 영상 → YOLO-pose → STANDING·낙상·경보 판정 → `/fall_status`, 화면 창 |
| `fall_monitor` | `ros2 run fall_detection fall_monitor` | `/fall_status`를 터미널에 표시 (상태 한 줄 / 20초 요약 / 대시보드) |
| `camera_node` | `ros2 run fall_detection camera_node` | 카메라·스트림 → `/camera/image_raw` (다른 ROS 노드와 영상 공유용) |
| `fall_node` | `ros2 run fall_detection fall_node` | 처음 만든 뼈대 (몸통 각도 하나로 `SUSPECT`만 판정). 참고용으로 유지 |
| `robot/pinky_stream.py` | 핑키에서 `python3 pinky_stream.py` | 핑키 카메라를 MJPEG(`:8000/video`, `/snapshot`)로 내보냄 |
| `tools/run_video.py` | `python3 tools/run_video.py --source clip.mp4` | 영상 → 프레임별 CSV + 오버레이 영상 (ROS 불필요) |
| `tools/plot_features.py` | `python3 tools/plot_features.py out/features.csv` | CSV → 특징값 그래프 (낙상 시점 세로선) |
| `tools/demo_status_publisher.py` | `python3 tools/demo_status_publisher.py --speed 4` | 가짜 시나리오로 `/fall_status` 발행 (모니터 시험용) |

## 판정 규칙

사양 원문은 `docs/SPEC_standing.md`. 모든 숫자는 `config/thresholds.yaml`에 있고 코드에는 하드코딩하지 않았습니다.

| 상태/경보 | 조건 |
|---|---|
| `STANDING` | 양측 knee 신전, hip neutral, knee가 hip 직하방, 수직 순서(어깨<골반<무릎<발목), 체간 직립. 0.5초 이상 유지 |
| `UNKNOWN` | 어깨·골반·무릎·발목 중 신뢰도 낮은 관절이 있음. 이전 상태 유지 |
| `FALL_EVENT` (임시 규칙) | 직전 기립 + 골반의 정규화 하강 속도 ≥ 1.5 몸통길이/초 + 골반이 바닥 근처 |
| `EMERGENCY_POST_FALL_IMMOBILE` | 낙상 후 **자세와 무관하게** 30초 무움직임 |
| `POST_FALL_MOVING` | 낙상 후 움직임 관찰 |
| `CHECK_STANDING_IMMOBILE` | 기립 상태로 30초 무움직임 |
| `RECOVERED` | 낙상 후 STANDING을 3초 이상 유지 |

| 위험 단계 | 경보 (`thresholds.yaml`의 `risk_levels`에서 변경) |
|---|---|
| 비위험 | 경보 없음, 회복 후 |
| 주의 | 기립 30초 무움직임, 낙상 후 움직임 |
| 위험 | 낙상 직후, 낙상 후 30초 무움직임(긴급) |

시연에서 30초를 줄이려면 `post_fall_immobile_emergency_s`, `standing_immobile_check_s`만 바꾸면 됩니다.

## 터미널 모니터

```bash
ros2 run fall_detection fall_monitor                                  # 기본: 상태 한 줄 + 변화 멘트
ros2 run fall_detection fall_monitor --ros-args -p mode:=summary      # 20초마다 요약 (-p summary_s:=10.0)
ros2 run fall_detection fall_monitor --ros-args -p mode:=live         # 관절 위치까지 계속 갱신되는 대시보드
ros2 run fall_detection fall_monitor --ros-args -p plain:=true        # 파일 저장용 (색·같은 자리 갱신 없음)
```

기본 모드 화면 예:

```
21:54:42  ● 사람 #1을(를) 확인했습니다. 안정 상태입니다.                                    (초록)
21:54:52  🚨 낙상 위험 감지! 사람 #1이(가) 빠르게 바닥으로 내려갔습니다. 상태를 파악 중입니다... (빨강)
21:54:59  🚨🚨 긴급! 사람 #1이(가) 낙상 후 30초 동안 움직이지 않습니다. 즉시 확인이 필요합니다!  (빨간 배경)
21:55:02  ✅ 회복 확인: 사람 #1이(가) 스스로 일어나 서 있습니다. 안정 상태로 돌아갑니다.       (초록)
● 안정 상태 진행 중... (사람 #1 · 서 있음 · 정지 3초째 · 안정 유지 1분 12초)   ← 이 줄만 그 자리에서 갱신
```

요약 모드에서도 단계가 **올라가는 순간**은 20초를 기다리지 않고 바로 한 줄로 알립니다 (`-p alert_now:=false`로 끔).

## 파라미터

| 노드 | 파라미터 | 기본값 | 설명 |
|---|---|---|---|
| `fall_core_node` | `source` | `2` | 카메라 번호 또는 영상 주소 (`http://...`) |
| | `model` | `yolo11n-pose.pt` | 모델 경로 (오프라인이면 절대 경로) |
| | `imgsz` / `person_conf` | `480` / `0.4` | YOLO 입력 크기 / 사람 검출 최소 신뢰도 |
| | `show` | `true` | 화면 창 표시 |
| | `thresholds` | (비움) | 임계값 파일 경로. 비우면 기본 `config/thresholds.yaml` |
| | `camera_id` / `publish_keypoints` | `cam0` / `true` | 메시지에 넣을 카메라 이름 / 17점 좌표 포함 여부 |
| | `stats_interval_s` | `5.0` | 속도 통계 출력 간격 |
| `fall_monitor` | `mode` | `status` | `status` / `summary` / `live` |
| | `summary_s` / `alert_now` / `plain` | `20.0` / `true` / `false` | 요약 간격 / 즉시 알림 / 색 없이 출력 |
| `camera_node` | `device` / `fps` | `2` / `30.0` | 카메라 번호 또는 주소 / 최대 발행 속도 |

`pinky_stream.py` 옵션: `--port 8000 --fps 15 --quality 70 --swap-rb(색이 푸를 때) --host`.

## `/fall_status` 형식 (std_msgs/String, JSON)

```json
{"camera_id": "cam0", "stamp": 1795436994.65, "state": "FALL_EVENT", "level": "DANGER",
 "keypoint_conf_min": 0.5, "limits": {"emergency_s": 30.0, "check_s": 30.0, "pelvis_floor_max": 0.6},
 "tracks": [{"track_id": 1, "posture": "NOT_STANDING", "mode": "POST_FALL", "alert": "FALL_EVENT",
             "level": "DANGER", "window": "IMMOBILE", "immobile_elapsed_s": 4.2, "trunk_tilt_deg": 88.0,
             "knee_angle_L": 176.0, "knee_angle_R": 178.0, "hip_angle_L": 170.0, "hip_angle_R": 171.0,
             "descent_speed": 0.1, "pelvis_height": 0.1, "box_conf": 0.9, "kpts": [[x, y, conf], ...17개]}]}
```

`state`는 가장 높은 경보 이름 (경보가 없으면 `NONE`, 사람이 없으면 `NO_PERSON`), `level`은 `SAFE|CAUTION|DANGER`.

## 테스트

```bash
python3 -m pytest tests -q       # ROS 없이 실행. 지시서의 16개 시나리오 포함 49개
```

가짜 17점 자세(`tests/synthetic_poses.py`)로 기립, 무릎 굽힘, 체간 굴곡, 옆으로 누움, 빠른/느린 하강,
낙상 후 정지·움직임·회복, 추적 소실, 불규칙한 프레임 간격, 터미널 멘트를 시험합니다.

## 한계

- **2D 영상입니다.** 정면에서는 hip/knee flexion이 투영으로 작게 보이고(정면에서 무릎을 20° 굽혀도 일직선처럼 보일 수 있음),
  측면에서는 반대편 다리가 가려질 수 있습니다. STANDING 판정 오차는 IMU로 정량화할 예정입니다.
- COCO에는 patella, calcaneus, metatarsal head, palm, toe가 없습니다. knee를 patella, ankle을 calcaneus의 근사로 씁니다.
- 판정은 STANDING 하나만 구현되어 있습니다. 앉음·무릎 꿇음·누움 같은 세부 자세는 아직 없어서,
  **낙상 없이 누운 채 가만히 있는 경우는 `비위험`으로 남습니다.**
- 추적기는 IoU와 중심 거리만 쓰는 간단한 방식이라, 여러 명이 걸치면 번호가 자주 바뀔 수 있습니다
  (ultralytics의 ByteTrack은 `lap` 설치가 필요해 쓰지 않음).
- 화면의 `latency`는 PC가 프레임을 받은 뒤부터의 지연이며, 핑키→PC 전송 지연은 포함하지 않습니다.
  스트림 연결 직후 몇 초는 쌓인 프레임을 따라잡느라 늦을 수 있습니다.
- `pinky_stream.py`는 인증이 없어 같은 와이파이의 누구나 영상을 볼 수 있습니다. 필요할 때만 켜세요.

## 구현하며 정한 가정 (사양에 없거나 모호했던 부분)

1. 긴급이 한 번 발령되면 움직임이 생겨도 해제하지 않고 `RECOVERED`로만 해제합니다.
2. 낙상 직후 `post_fall_settle_s`(3초) 동안의 움직임은 몸이 자리잡는 중으로 보고 `POST_FALL_MOVING`으로 보지 않습니다.
3. `POST_FALL_MOVING`은 한 번 표시되면 회복/긴급 전까지 유지합니다.
4. 하강 속도는 최근 `fall_max_duration_s` 안에서 `descent_min_dt_s` 이상 떨어진 샘플 쌍 중 최댓값입니다.
5. 변위는 시간 창 안 점들 사이의 최대 거리(지름)를 `L_trunk_ref`로 나눈 값입니다.
6. 소실된 `POST_FALL` track은 같은 위치(`track_readopt_max_dist`)에 새 번호로 나타나면 이어 붙입니다.
7. `pelvis_height`(`pelvis_y_norm`)는 `(floor_y - pelvis_y) / L_trunk_ref`: 서 있으면 다리 길이만큼(몸통의 2~3배), 누우면 약 0.
8. 위험 단계 매핑에서 `FALL_EVENT`(낙상 직후)를 위험으로 두었습니다.
9. 새 노드를 담은 파이썬 패키지 이름이 `ros`입니다. 너무 일반적인 이름이라 나중에 `fall_ros` 등으로 바꾸는 것을 권장합니다.

## 폴더 구조

```
fall_core/        판정 코어 (순수 Python: numpy, PyYAML)
  keypoints.py geometry.py states.py posture.py history.py immobility.py alerts.py engine.py
  iou_tracker.py yolo_io.py viz.py risk.py status.py monitor_view.py config.py
ros/              fall_node_adapter.py (fall_core_node), fall_monitor.py
fall_detection/   camera_node.py, fall_node.py + pose_logic.py (초기 뼈대)
robot/            pinky_stream.py (핑키에서 실행)
config/           thresholds.yaml
tools/            run_video.py, plot_features.py, demo_status_publisher.py
tests/            pytest
docs/             SPEC_standing.md
```

## 라이선스

이 저장소의 코드는 Apache-2.0입니다 (`LICENSE`). `ultralytics`는 AGPL-3.0이므로 배포나 상업적 사용 전에 라이선스를 확인하세요.
