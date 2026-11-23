# STANDING 판정 모듈 사양 (지시서 2~5절 그대로)

> 원본: Downloads/ClaudeCode_standing_build_prompt.md 의 2~5절. 이 문서를 구현하면서 정한 가정은 README의 '구현하며 정한 가정'을 참고.

## 2. 해부학적 정의 (사양)

### 2-1. COCO 17 keypoints와 해부학적 대응

| idx | COCO 이름 | 해부학적 근사 | 비고 |
|---|---|---|---|
| 0 | nose | 두부(cephalic) 위치 | 두부 움직임 판정에 사용 |
| 5, 6 | L/R shoulder | glenohumeral joint 중심 부근 (acromion 근방) | |
| 9, 10 | L/R wrist | radiocarpal joint | palm 근사 |
| 11, 12 | L/R hip | hip joint center (femoral head 투영) 부근 | ASIS/PSIS 아님 |
| 13, 14 | L/R knee | tibiofemoral joint 중심 | **patella 근사로 사용** |
| 15, 16 | L/R ankle | talocrural joint (malleoli 부근) | **calcaneus 근사로 사용** |

- **Shoulder midpoint** = (5 + 6) / 2
- **Pelvis midpoint** = (11 + 12) / 2 → 체질량중심(COM)의 2D 근사로 사용 (Sacrum S2 IMU 위치와 비교 예정)
- **Trunk length (L_trunk)** = shoulder midpoint – pelvis midpoint 거리 → 모든 길이·변위의 정규화 기준
- COCO에는 **patella, calcaneus, metatarsal head, palm, toe가 없다.** 위 근사의 한계를 코드 주석에 명시한다.

### 2-2. STANDING (기립 자세) 정의

**임상적 정의**: 양측 하지가 **수직 정렬(vertical alignment)** 되어 있고, **hip joint neutral (flexion/extension 0°)**, **knee full extension (0°)**, **ankle neutral (plantigrade, 0° dorsiflexion/plantarflexion)** 이며, 체간(trunk)이 직립(upright)인 **양하지 체중지지(bilateral weight-bearing) 자세**.
즉, 양측 patella가 hip joint 직하방(inferior)에 위치하고, hip – knee – ankle(calcaneus 근사)이 일직선을 이룬다.

**카메라 판정 조건 (모두 만족해야 STANDING)**

| # | 해부학적 조건 | 2D 계산 | 임계값 키 |
|---|---|---|---|
| S1 | 하지 수직 정렬: hip – knee – ankle 일직선 (knee extension) | 좌·우 각각 hip–knee–ankle **관절 내각** ≥ `knee_extension_min_deg` (180° = 완전 신전) | `standing.knee_extension_min_deg` (TBD, 초기값 160) |
| S2 | Hip joint neutral: 체간–대퇴 정렬 | 좌·우 각각 shoulder–hip–knee 내각 ≥ `hip_extension_min_deg` | `standing.hip_extension_min_deg` (TBD, 초기값 160) |
| S3 | Patella가 hip 직하방 | \|knee_x − hip_x\| / L_trunk ≤ `knee_hip_horizontal_max` (좌·우 각각) | `standing.knee_hip_horizontal_max` (TBD, 초기값 0.25) |
| S4 | 수직 순서 (cranial → caudal) | 이미지 y 좌표: shoulder < hip < knee < ankle (y는 아래로 증가) | — |
| S5 | 체간 직립 (trunk upright) | shoulder midpoint – pelvis midpoint 선의 **수직선 대비 경사각** ≤ `trunk_tilt_max_deg` (0~90°로 표현) | `standing.trunk_tilt_max_deg` (TBD, 초기값 20) |
| S6 | 양측성 (bilateral) | S1~S3을 **좌·우 모두** 만족 | — |

**판정 보류 (UNKNOWN)**
- idx 5, 6, 11, 12, 13, 14, 15, 16 중 하나라도 confidence < `keypoint_conf_min`이면 해당 프레임은 `UNKNOWN`.
- `UNKNOWN`은 STANDING도 NOT_STANDING도 아니다. 이전 상태를 유지하되 로그에 기록한다.

**2D 한계 (코드 주석과 README에 명시)**
- 정면(frontal view)에서는 sagittal plane의 hip/knee flexion이 투영으로 **작게 보이거나 보이지 않는다.** 정면에서 knee를 20° 굽혀도 일직선처럼 보일 수 있다.
- 측면(sagittal view)에서는 반대편 하지가 가려질(occlusion) 수 있다.
- 따라서 STANDING 판정은 시점(view)에 따라 오차가 있으며, 이 오차는 IMU(L anterior mid-thigh, L medial tibia)와 비교해 정량화할 예정이다.

### 2-3. 무움직임 (Immobility) 공통 정의

**임상적 정의**: **의도적 움직임(voluntary movement)** 이 관찰되지 않는 상태. 상지(upper extremity), 두부(cephalic), 체간(trunk), 하지(lower extremity) 어느 분절에서도 의미 있는 변위가 없음.

**카메라 판정**
- 대상 분절 keypoint: nose(0), L/R wrist(9, 10), L/R shoulder(5, 6), pelvis midpoint, L/R ankle(15, 16)
- 각 keypoint의 시간 창(`window_s`) 내 **최대 변위 / L_trunk_ref** 를 계산한다.
  - `L_trunk_ref`는 해당 track_id의 **최근 STANDING 구간에서의 trunk length** 를 쓴다. 누운 자세에서는 투영으로 trunk가 짧게 보여 정규화가 왜곡되기 때문이다. STANDING 기록이 없으면 최근 `window_s` 동안의 최대 trunk length를 쓴다.
- 모든 대상 keypoint의 정규화 변위가 `displacement_max`보다 작으면 그 창은 "무움직임".
- 시간은 **프레임 수가 아니라 프레임 타임스탬프(초)** 로 계산한다 (CPU에서 FPS가 8~9로 변동).
- 신뢰도 낮은 keypoint는 변위 계산에서 제외하되, 대상 keypoint의 `min_valid_keypoint_ratio` 미만만 남으면 그 구간은 판정 보류(타이머 정지, 초기화하지 않음).
- 움직임이 관찰되면 무움직임 타이머를 0으로 초기화한다.

**생리적 미세 동요(postural sway)는 움직임이 아니다**: 정상 기립 시에도 COM은 수 mm~수 cm 흔들린다. `displacement_max`는 이 sway보다 크게 잡아야 오경보가 나지 않는다 (TBD, 초기값 0.05 = trunk length의 5%).

### 2-4. 경보 1 — 낙상 후 무움직임 → 긴급 (EMERGENCY_POST_FALL_IMMOBILE)

**임상적 정의**: 낙상 사건(fall event) 이후 **자세와 무관하게**(supine, prone, side-lying, sitting, kneeling, quadruped, 웅크린 자세 등 모두 포함) 의도적 움직임이 **30초 이상** 없음. 의식 저하, 심한 손상, 스스로 일어나지 못하는 상태(long lie의 초기 단계)를 의심하며 **즉시 구조 확인**이 필요하다.

**판정 순서**
1. `FALL_EVENT` 발생 → track_id를 `POST_FALL` 모드로 전환 (2-5절).
2. `POST_FALL` 모드에서는 **posture 분류 결과와 상관없이** 무움직임 타이머를 돌린다.
3. 무움직임이 연속 `post_fall_immobile_emergency_s`초(**30.0초, 임상 기준 확정**) 지속 → `EMERGENCY_POST_FALL_IMMOBILE`.
4. 해제 조건: STANDING이 `recovery_standing_min_s`초 이상 유지되면 `RECOVERED`로 전환하고 POST_FALL 모드 종료.
   - 움직임만 다시 생긴 경우(예: 누운 채 팔을 흔듦)는 긴급을 해제하지 않고 `POST_FALL_MOVING` 상태로 표시한다 (사람이 확인할 때까지 유지).
5. 사람이 화면에서 사라지면(track 소실) `POST_FALL` 상태를 `track_lost_hold_s`초 동안 유지하고, 그 안에 같은 위치에서 재검출되면 이어서 판정한다.

### 2-5. FALL_EVENT (임시 정의 — 다음 단계에서 IMU 데이터로 확정)

> 이번 단계의 핵심은 STANDING이지만, 2-4절이 동작하려면 낙상 사건 트리거가 필요하므로 **임시 규칙**을 둔다. 모든 숫자는 TBD이며, IMU(Sacrum S2) 기준 낙상 시점과 맞춘 데이터로 다시 정한다.

**임상적 정의**: 의도하지 않게 신체가 지면 또는 더 낮은 면으로 내려앉는 사건. 조절된 하강(controlled descent: 앉기, 눕기, 줍기)과 구분되는 핵심은 **하강 속도**다.

**카메라 임시 규칙 (모두 만족)**
- F1. 직전 `fall_prior_standing_s`초 이내에 STANDING이었음
- F2. Pelvis midpoint의 **정규화 하강 속도** = Δ(pelvis_y) / L_trunk_ref / Δt 가 `descent_speed_min` 이상 (이미지 y는 아래로 증가)
- F3. 하강 시작 후 `fall_max_duration_s`초 이내에 pelvis midpoint가 floor 기준선 근처에 도달
  - floor 기준선 = 해당 track의 최근 STANDING 구간 ankle(15, 16) 평균 y
  - "근처" = |pelvis_y − floor_y| / L_trunk_ref ≤ `pelvis_floor_max`
- F1~F3 만족 시 `FALL_EVENT` 발생, 타임스탬프 기록.

### 2-6. 경보 2 — 기립 무움직임 → 확인 요청 (CHECK_STANDING_IMMOBILE)

**임상적 정의**: 기립 자세에서 의도적 움직임이 **30초 이상** 없음. 정상적인 정적 기립(대기, 관찰)일 가능성이 높지만, 동결(freezing)이나 의식 변화의 가능성도 있으므로 **관제의 영상 확인을 요청**한다. 긴급이 아니다.

**판정**
- STANDING이면서 무움직임이 연속 `standing_immobile_check_s`초(기본 30.0초) 지속 → `CHECK_STANDING_IMMOBILE`.
- 움직임이 관찰되거나 STANDING이 아니게 되면 해제(`CHECK_CLEARED`). 단, STANDING에서 FALL_EVENT로 넘어가면 2-4절 규칙이 우선한다.

### 2-7. 경보 우선순위
`EMERGENCY_POST_FALL_IMMOBILE` > `POST_FALL_MOVING` > `FALL_EVENT` > `CHECK_STANDING_IMMOBILE` > `NONE`
한 track_id에는 한 번에 가장 높은 경보 하나만 표시한다.

---

## 3. 상태와 경보 (states.py)

```python
class Posture(Enum):
    UNKNOWN = 0
    STANDING = 1
    NOT_STANDING = 2
    # 이후 추가 예정 (지금은 정의만, 미구현):
    # SITTING, KNEELING_BILATERAL, HALF_KNEELING, QUADRUPED,
    # DEEP_SQUAT, SIDE_LYING, SUPINE, PRONE

class Mode(Enum):          # track_id별 모드
    NORMAL = 0
    POST_FALL = 1
    RECOVERED = 2

class Alert(Enum):         # 우선순위 높은 순
    EMERGENCY_POST_FALL_IMMOBILE = 4   # 긴급: 낙상 후 어떤 자세든 30초 무움직임
    POST_FALL_MOVING = 3               # 낙상 후 움직임 있음 (확인 필요)
    FALL_EVENT = 2                     # 낙상 사건 발생 (임시 규칙)
    CHECK_STANDING_IMMOBILE = 1        # 확인 요청: 기립 30초 무움직임
    NONE = 0
    # 이후 추가 예정:
    # SELF_RECOVERABLE (bilateral kneeling, quadruped, 상지 체중지지)
    # CONTROLLED_POSTURE (deep squat, 줍기, child's pose)
```

---

## 4. config/thresholds.yaml

```yaml
# 모든 각도: degree, 모든 길이: trunk length(L_trunk) 대비 비율, 시간: second
keypoint_conf_min: 0.5            # TBD

standing:
  knee_extension_min_deg: 160     # TBD: hip-knee-ankle 내각, 180 = full extension
  hip_extension_min_deg: 160      # TBD: shoulder-hip-knee 내각, 180 = neutral
  knee_hip_horizontal_max: 0.25   # TBD: |knee_x - hip_x| / L_trunk
  trunk_tilt_max_deg: 20          # TBD: 수직선 대비 체간 경사
  min_duration_s: 0.5             # TBD: 이 시간 이상 조건 유지 시 STANDING 확정 (깜빡임 방지)

immobility:
  window_s: 2.0                   # TBD: 변위 계산 시간 창
  displacement_max: 0.05          # TBD: postural sway보다 커야 함
  min_valid_keypoint_ratio: 0.5

alerts:
  post_fall_immobile_emergency_s: 30.0  # 확정(임상 기준): 낙상 후 어떤 자세든 무움직임 → 긴급
  standing_immobile_check_s: 30.0       # 확인 요청 기준 (긴급 아님)
  recovery_standing_min_s: 3.0          # TBD: 이 시간 이상 STANDING 유지 시 회복
  track_lost_hold_s: 10.0               # TBD: track 소실 시 POST_FALL 상태 유지 시간

fall_event:                     # 임시 규칙, IMU 데이터로 재결정
  fall_prior_standing_s: 2.0      # TBD
  descent_speed_min: 1.5          # TBD: trunk length / s
  fall_max_duration_s: 1.5        # TBD: 하강 시작~바닥 도달 최대 시간
  pelvis_floor_max: 0.6           # TBD: |pelvis_y - floor_y| / L_trunk_ref
```

> 시연 시 30초를 줄이고 싶으면 yaml에서 `post_fall_immobile_emergency_s`, `standing_immobile_check_s`만 바꾼다. 코드는 바꾸지 않는다.

---

## 5. 로그 (tools/run_video.py 출력 CSV)

프레임마다 track_id별 1행:
- `frame_idx`, `t_s`(프레임 타임스탬프, 초), `track_id`, `box_conf`
- 17점 각각 `kp{i}_x`, `kp{i}_y`, `kp{i}_c` (51열)
- `L_trunk`, `knee_angle_L`, `knee_angle_R`, `hip_angle_L`, `hip_angle_R`, `knee_hip_dx_L`, `knee_hip_dx_R`, `trunk_tilt_deg`
- `L_trunk_ref`, `pelvis_y_norm`(floor 기준), `descent_speed`
- `posture`, `mode`, `immobile_elapsed_s`, `alert`, `fall_event_t_s`
- 영상 타임스탬프는 OpenCV `CAP_PROP_POS_MSEC`로 읽고, 나중에 ffprobe 추출값으로 바꿔 끼울 수 있게 함수로 분리한다.

오버레이 영상: 점·골격·track_id, 좌상단에 `posture`, `trunk_tilt`, `knee_angle L/R`, 무움직임 경과초, 경보를 표시.

