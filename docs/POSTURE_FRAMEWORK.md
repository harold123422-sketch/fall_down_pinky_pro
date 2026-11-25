# 자세별 판정 기준 (1막 낙상 감지)

> 코드: `fall_core/posture_framework.py` · 숫자: `config/thresholds.yaml`
> 모든 숫자는 **임시값, 실제 데이터로 확정 예정**입니다. ⚠ 표시는 사용자가 임상적으로 확인해야 하는 부분입니다.
> 자세 이름 표기: 이 문서는 `Stand Upright`처럼 씁니다. 코드·yaml에서는 같은 이름을 대문자와 밑줄로 씁니다 (`Stand Upright` = `STAND_UPRIGHT`).

---

## 읽는 법

| 용어 | 뜻 |
|---|---|
| **높이** | 바닥 기준선 위 높이 ÷ 몸통 길이. 서 있을 때 골반 높이는 약 2, 바닥에 앉거나 누우면 약 0 |
| **바닥 근처** | 높이 ≤ **0.35** (`near_floor`). 손바닥 지지는 "손목이 바닥 근처"로 대신함 |
| **체간 기울기** | 어깨 중점 → 골반 중점 선이 수직선과 이루는 각도. 0° 수직, 90° 수평 |
| **무릎 내각** | 고관절–무릎–발목 각도. 180° 완전 신전 |
| **몸통 길이** | 어깨 중점–골반 중점 거리. 서 있을 때 잰 값 |
| **바닥 기준선** | 서 있을 때 양 발목의 높이. 서 있는 모습을 본 적이 없으면 가장 낮게 보인 관절점 |

**판정 순서** (위에서부터 먼저 맞는 자세로 결정)

Unknown → Lying → Elbow Support → Bear Pose → Quadruped → Sit Floor → Kneel → Sit Heel → Reclined Supported → Sit Chair → Squat → Forward Flexion → Standing → Other

새 자세는 **0.4초 이상** 이어져야 화면 이름이 바뀝니다 (깜빡임 방지).

**카드 보는 법**
- **조건**: 모두 만족해야 그 자세 (yaml 이름으로 숫자를 바꿀 수 있음)
- **코드 흐름**: 실제 코드를 한국어로 옮긴 것. 오른쪽 줄 번호로 VS Code에서 `Ctrl+G`
- **위험**: 평상시(낙상 장면을 못 봤을 때)와 낙상 후

---

## Unknown (판단 불가)

> 어깨나 골반이 하나도 보이지 않거나, 바닥 기준선·몸통 길이를 아직 모를 때

```
어깨(좌·우 중 하나라도)와 골반(좌·우 중 하나라도)이 안 보이면   → Unknown        [152~153줄]
Unknown 프레임은 이전 자세를 그대로 유지
```

---

## Lying family (누운 계열)

공통 조건: **골반 높이 ≤ 0.5** (`lying_pelvis_max`) **그리고 어깨 높이 ≤ 0.45** (`lying_shoulder_max`)
→ 체간 기울기는 보지 않으므로, 카메라 쪽으로 누워 몸통이 짧게 보여도 잡힙니다.

### Lying Fetal (태아 자세)

> 옆으로 누워 무릎을 가슴 쪽으로 당긴 자세

| 기준 | 임시값 | yaml 이름 |
|---|---|---|
| Lying 공통 조건 | | |
| 무릎 중점–어깨 중점 거리 | ≤ 0.9 | `fetal_knee_chest_max` |
| 무릎 내각 (작은 쪽) | ≤ 110° | `fetal_knee_angle_max` |

```
만약 Lying이고                                                         [164~166줄]
   무릎–어깨 거리 ≤ 0.9 그리고 무릎 내각 ≤ 110° 이면   → Lying Fetal
```

- **위험**: 평상시 **3초** 이어지면 주의 (통증·위험 신호 후보), 30초 무움직임이면 주의 / 낙상 후 회복 단계 1

### Lying Side L · Lying Side R (좌측와위 · 우측와위)

> 옆으로 누워 양 어깨가 위아래로 겹쳐 보이는 자세. L/R = 바닥에 닿은 쪽

| 기준 | 임시값 | yaml 이름 |
|---|---|---|
| Lying 공통 조건, Lying Fetal 아님 | | |
| 양 어깨 세로 차이 | ≥ 0.15 | `side_stack_min` |
| 양 어깨 가로 거리 | ≤ 0.35 | `side_width_max` |

```
세로 = |왼어깨 y − 오른어깨 y| ÷ 몸통 길이                              [167~172줄]
가로 = |왼어깨 x − 오른어깨 x| ÷ 몸통 길이
만약 세로 ≥ 0.15 그리고 가로 ≤ 0.35 이면
   → 화면에서 더 아래(바닥 쪽)에 있는 어깨 쪽의 Lying Side L / R
한쪽 어깨만 보이면                                                       [174~175줄]
   → 안 보이는 쪽이 바닥에 깔린 Lying Side로 추정
```

- **위험**: 평상시 **5초** 이어지면 주의 (보지 못한 낙상 가능), 30초 무움직임이면 주의 / 낙상 후 회복 단계 1
- **2D 주의**: 카메라 방향에 따라 Lying Flat과 헷갈릴 수 있음

### Lying Flat (앙와위 또는 복와위)

> 등이나 배를 대고 누운 자세. 2D 관절점으로는 둘을 구분하지 못해 하나로 묶음 (프레임워크 7절)

```
Lying이고, Lying Fetal도 Lying Side도 아니면 (양 어깨가 나란함)   → Lying Flat   [173줄]
```

- **위험**: 평상시 **5초** 이어지면 주의, 30초 무움직임이면 주의 / 낙상 후 회복 단계 1
- **2D 주의**: 앙와위·복와위 구분 불가

---

## Elbow Support (팔꿈치 지지)

공통 조건:

| 기준 | 임시값 | yaml 이름 |
|---|---|---|
| 골반 높이 | ≤ 0.4 | `sit_floor_pelvis_max` |
| 어깨 높이 (상체가 들림) | ≥ 0.4 | `elbow_shoulder_min` |
| 체간 기울기 | 25° ~ 75° | `elbow_tilt_min_deg`, `elbow_tilt_max_deg` |
| 팔꿈치가 바닥 근처이고 같은 쪽 어깨 바로 아래 (가로 거리) | ≤ 0.5 | `elbow_under_shoulder_max` |

```
골반·어깨·기울기 조건을 만족하면, 마지막 조건을 만족하는 팔꿈치 수를 셈      [178~185줄]
   2개 → Prone On Elbows
   1개 → Side Lying On Elbow
```

### Prone On Elbows (팔꿈치 지지 복와위)

- **위험**: 평상시 **5초** 이어지면 주의 (바닥에서 일어나는 중일 수 있음), 30초 무움직임이면 주의 / 낙상 후 회복 단계 2
- **2D 주의**: 복와위인지 확실하지 않음

### Side Lying On Elbow (팔꿈치 지지 측와위)

- **위험**: 평상시 **5초** 이어지면 주의, 30초 무움직임이면 주의 / 낙상 후 회복 단계 2

---

## Quadruped family (네발 계열)

공통 조건: **체간 기울기 ≥ 45°** (`quad_tilt_min_deg`) **그리고 골반 높이 > 0.4**

### Bear Pose (손·발 지지)

> 손과 발로 지지하고 무릎은 바닥에서 뜬 자세

```
손목이 바닥 근처 그리고 발목이 바닥 근처                                  [191~194줄]
그리고 보이는 무릎이 모두 바닥에서 뜸(높이 > 0.35)
그리고 네발 계열 공통 조건                       → Bear Pose
```

- **위험**: 평상시 **3초** 이어지면 주의 (일어서기 직전일 수 있음), 30초 무움직임이면 주의 / 낙상 후 회복 단계 4

### Quadruped · Crawling (사지 착지 · 기기)

> 손과 무릎으로 지지한 자세. 골반이 움직이면 Crawling

| 기준 | 임시값 | yaml 이름 |
|---|---|---|
| 손목이 바닥 근처, 무릎이 바닥 근처 | ≤ 0.35 | `near_floor` |
| 네발 계열 공통 조건 | | |
| (Crawling) 골반 수평 이동 속도 | ≥ 0.15 몸통/초 | `crawl_speed_min` |

```
손목·무릎이 바닥 근처 그리고 네발 계열 공통 조건이면                        [196~199줄]
   골반 이동 ≥ 0.15 몸통/초  → Crawling
   그 외                     → Quadruped
```

- **위험**: 평상시 **3초** 이어지면 주의 (보지 못한 낙상 후 일어나는 중일 수 있음) / 낙상 후 회복 단계 4
  (Quadruped는 30초 무움직임이면 주의, Crawling은 이동 중이라 무움직임 검사 없음)

---

## Sitting family (앉기 계열)

### Sit Floor 공통 조건 (바닥 앉기)

**골반 높이 ≤ 0.4** (`sit_floor_pelvis_max`) **그리고 체간 기울기 ≤ 45°** (`sit_trunk_max_deg`)
아래 순서로 세부 자세를 확인합니다: Sit Floor Side → Sit Floor Knees Up → Sit Floor Cross → Sit Floor Long → Sit Floor [202~223줄]

### Sit Floor Side (측좌위)

> 두 무릎을 한쪽으로 접고 반대쪽 손으로 바닥을 짚은 자세 (측와위에서 일어나는 경로)

| 기준 | 임시값 | yaml 이름 |
|---|---|---|
| Sit Floor 공통 조건, 양 무릎이 보임 | | |
| 무릎 내각 (굽힘) | ≤ 120° | `knees_up_angle_max` |
| 두 무릎이 골반의 같은 쪽으로 쏠린 거리 (평균) | ≥ 0.4 | `side_sit_knee_shift_min` |
| 손목 하나 이상이 바닥 근처 | ≤ 0.35 | `near_floor` |

```
왼무릎 쏠림 = (왼무릎 x − 골반 x) ÷ 몸통 길이                              [205~208줄]
오른무릎 쏠림 = (오른무릎 x − 골반 x) ÷ 몸통 길이
두 값이 같은 방향이고 평균 ≥ 0.4, 무릎 굽힘, 손이 바닥   → Sit Floor Side
```

- **위험**: 평상시 30초 무움직임이면 주의 / 낙상 후 회복 단계 3

### Sit Floor Knees Up (무릎 세워 앉기)

```
가장 높은 무릎 높이 ≥ 0.5 (knees_up_min)                                 [209~212줄]
그리고 무릎 내각 ≤ 120° (knees_up_angle_max)             → Sit Floor Knees Up
```

- **위험**: 평상시 30초 무움직임이면 주의 (낙상 후 휴식 가능) / 낙상 후 회복 단계 3

### Sit Floor Cross (책상다리 앉기)

> 정면 영상에서만 판단. 측면에서는 양 고관절이 겹쳐 보여 판단하지 않음

| 기준 | 임시값 | yaml 이름 |
|---|---|---|
| 양 고관절 가로 거리 (정면인지 확인) | ≥ 0.2 | `cross_hip_width_min` |
| 무릎 내각 (굽힘) | ≤ 120° | `knees_up_angle_max` |
| 무릎 사이 거리 ÷ 고관절 사이 거리 | ≥ 2.5 | `cross_knee_spread_min` |
| 양 발목 사이 거리 | ≤ 0.35 | `cross_ankle_gap_max` |

```
고관절 폭이 보이고, 무릎이 굽고,                                          [213~220줄]
무릎이 고관절 폭의 2.5배 이상 벌어지고, 발목이 모이면   → Sit Floor Cross
```

- **위험**: 평상시 30초 무움직임이면 주의 / 낙상 후 회복 단계 3
- **2D 주의**: 정면에서만 판단 가능

### Sit Floor Long (장좌위)

```
무릎 내각 ≥ 150° (long_sit_knee_min_deg) 그리고 무릎이 바닥 근처   → Sit Floor Long   [221~222줄]
```

- **위험**: 평상시 30초 무움직임이면 주의 (낙상 후 회복 경로) / 낙상 후 회복 단계 3

### Sit Floor (바닥 앉기, 세부 미구분)

```
Sit Floor 공통 조건은 맞지만 위 4가지에 해당하지 않으면   → Sit Floor     [223줄]
```

- **위험**: 평상시 30초 무움직임이면 주의 / 낙상 후 회복 단계 3

### Sit Heel (뒤꿈치 위 앉기, seiza)

> 무릎을 꿇고 엉덩이를 발뒤꿈치 위에 내린 자세

```
무릎이 바닥 근처                                                          [237~238줄]
그리고 Kneel 조건(골반이 무릎보다 0.6 이상 높음)이 아님
그리고 골반 높이 > 0.4, 체간 기울기 ≤ 45°           → Sit Heel
```

- **위험**: 평상시 30초 무움직임이면 주의 / 낙상 후 회복 단계 5

### Sit Chair Upright · Sit Chair Slumped (의자 앉기 바른 자세 · 체간 처짐)

> 좌석은 보이지 않으므로 "골반 높이 ≈ 무릎 높이"로 판단

| 기준 | 임시값 | yaml 이름 |
|---|---|---|
| \|골반 높이 − 무릎 평균 높이\| | ≤ 0.15 | `chair_pelvis_knee_max` |
| 발목이 바닥 근처, 골반 높이 > 0.4 | | |
| (Slumped) 체간 기울기 | ≥ 20° | `slumped_tilt_min_deg` |
| (Slumped) 또는 양 어깨 높이 차이 | ≥ 0.25 | `slumped_shoulder_dy_min` |

```
골반 ≈ 무릎 높이, 발이 바닥                                               [247~253줄]
   체간 ≥ 20° 또는 한쪽 어깨가 처짐   → Sit Chair Slumped
   그 외                               → Sit Chair Upright
```

- **위험 (Sit Chair Upright)**: 오래 앉아 있어도 정상 / 낙상 후 회복 단계 5
- **위험 (Sit Chair Slumped)**: 평상시 **10초** 이어지면 주의 (의식저하 의심 후보) / 낙상 후 회복 단계 5
- **2D 주의**: 허벅지가 수평인 90° Squat Partial과 구분하지 못함

---

## Kneeling family (무릎 계열)

공통 조건: **무릎이 바닥 근처** 그리고 **골반이 바닥 쪽 무릎보다 0.6 이상 높음** (`kneel_pelvis_above_knee_min`)
그리고 **체간 기울기 ≤ 30°** (`kneel_trunk_max_deg`) [226~236줄]

### Kneel Bilateral (양측 무릎 서기)

```
양 무릎이 모두 바닥 근처                                → Kneel Bilateral
한쪽 무릎만 바닥이고 반대 무릎이 가려졌거나 낮으면      → Kneel Bilateral
```

- **위험**: 평상시 30초 무움직임이면 주의 (회복 경로) / 낙상 후 회복 단계 5

### Kneel Half L · Kneel Half R (반무릎 서기)

> L/R = 바닥에 닿은 무릎 쪽

```
한쪽 무릎만 바닥 근처이고 반대 무릎 높이 ≥ 0.6 (half_kneel_other_knee_min)
   → 바닥에 닿은 무릎 쪽의 Kneel Half L / R
```

- **위험**: 평상시 30초 무움직임이면 주의 (일어서기 직전) / 낙상 후 회복 단계 5

---

## Reclined Supported (기댄 반와위, 침대·소파)

> 프레임워크 판단 순서 표에 없어서 Sit Chair 앞에 넣었습니다 ⚠

| 기준 | 임시값 | yaml 이름 |
|---|---|---|
| 체간 기울기 | ≥ 45° | `reclined_tilt_min_deg` |
| 골반 높이 | 0.4 초과 ~ 1.6 이하 | `reclined_pelvis_max` |
| 양 발목이 모두 바닥 근처는 아님 (다리가 침대·소파 위) | | |

```
체간이 많이 기울고, 골반이 바닥보다 높고, 발이 바닥에 없으면   → Reclined Supported   [241~244줄]
```

- **위험**: 오래 있어도 정상 (침대·소파) / 회복 단계 없음
- **2D 주의**: 등받이·침대는 보이지 않아 높이와 기울기로만 추정

---

## Standing family (기립 계열)

### Squat Partial · Squat Deep (부분 쪼그림 · 깊은 쪼그림)

| 기준 | 임시값 | yaml 이름 |
|---|---|---|
| 발목이 바닥 근처 | ≤ 0.35 | `near_floor` |
| 무릎 내각 | ≤ 140° | `squat_knee_angle_max` |
| 골반 높이 | 0.4 초과 ~ 1.6 이하 | `squat_partial_pelvis_max` |
| (Squat Deep) 골반 높이 | ≤ 0.9 | `squat_deep_pelvis_max` |

```
발이 바닥, 무릎 굽힘, 골반이 중간~낮음이면                                [256~260줄]
   골반 ≤ 0.9   → Squat Deep
   그 외        → Squat Partial
```

- **위험**: 조절된 하강으로 봄. 평상시 30초 무움직임이면 주의 / 낙상 후 회복 단계 5
- **2D 주의**: Squat Deep은 Sit Floor와 골반 높이로만 구분 (경계가 가까움)

### Forward Flexion (체간 전방 굴곡)

> 무릎을 편 채 몸을 숙인 자세 (줍기 등)

```
체간 기울기 ≥ 45° (flexion_tilt_min_deg)                                [263~265줄]
그리고 무릎 내각 ≥ 150° (flexion_knee_min_deg) 그리고 발이 바닥   → Forward Flexion
```

- **위험**: 조절된 자세. 평상시 30초 무움직임이면 주의 / 낙상 후 회복 단계 6

### Walking (보행)

> 두 가지 중 하나면 보행. 카메라가 사람을 따라가거나 카메라 쪽으로 걸어와 골반이 화면에서 안 움직여도 ②로 잡힘

| 기준 | 임시값 | yaml 이름 |
|---|---|---|
| 골반 높이 | > 1.6 | `squat_partial_pelvis_max` |
| 체간 기울기 | ≤ 45° | `lean_tilt_max_deg` |
| ① 골반 수평 이동 속도 | ≥ 0.3 몸통/초 | `walk_speed_min` |
| ② 보행 주기: 최근 1.5초 동안 양 발목(왼−오른) 위치 차이가 번갈아 부호를 바꿈 | 변화 폭 ≥ 0.25, 1회 이상 엇갈림 | `gait_window_s`, `gait_amp_min`, `gait_alt_min`, `gait_min_alternations` |

```
보행 주기 = 양 발목 위치 차이(왼 − 오른)를 1.5초 동안 기록                 [engine.py _gait]
   측면에서 걸으면 가로 차이가, 카메라 쪽으로 걸어오면 세로 차이가 더 크게 변함 → 더 크게 변하는 쪽을 봄
   변화 폭 ≥ 0.25 이고, 왼발 앞 ↔ 오른발 앞으로 1번 이상 바뀌면 보행 주기
골반이 높고, 체간이 서 있고, (골반 이동 ≥ 0.3 또는 보행 주기) 이면   → Walking
```

- **위험**: 정상 / 낙상 후 회복 단계 6

### Stand One Leg (단하지 기립)

| 기준 | 임시값 | yaml 이름 |
|---|---|---|
| 체간 기울기 | ≤ 20° | `trunk_tilt_max_deg` (standing) |
| 지지하는 발목이 바닥 근처 | ≤ 0.35 | `near_floor` |
| 반대 발목 높이 (들림) | ≥ 0.25 | `one_leg_lift_min` |
| 지지하는 쪽 무릎 내각 | ≥ 160° | `knee_extension_min_deg` (standing) |

```
왼발·오른발 각각을 지지발로 두고 위 조건을 확인                             [272~276줄]
   맞으면 → Stand One Leg (지지발 쪽을 근거에 기록)
```

- **위험**: 평상시 **3초** 이어지면 주의 (균형 위험 관찰) ⚠ / 낙상 후 회복 단계 6

### Stand Upright (양하지 기립)

> Standing 사양의 S1~S6을 그대로 씀 (`docs/SPEC_standing.md`, `fall_core/posture.py`)

| 조건 | 기준 | 임시값 |
|---|---|---|
| S1 | 양측 무릎 내각 | ≥ 160° |
| S2 | 양측 어깨–고관절–무릎 각 | ≥ 160° |
| S3 | 무릎이 고관절 바로 아래 (가로 거리) | ≤ 0.25 |
| S4 | 위아래 순서: 어깨 < 골반 < 무릎 < 발목 | |
| S5 | 체간 기울기 | ≤ 20° |
| S6 | S1~S3을 좌·우 모두 만족 | |

```
S1~S6을 모두 만족하면   → Stand Upright                                  [277~278줄]
```

- **위험**: 정상. 30초 무움직임이면 주의 (기립 무움직임 확인 요청) / 낙상 후 이 자세로 **3초** 유지하면 회복

### Stand Lean Support (지지 기립)

> 벽·보행기에 기댄 자세. 지지물은 보이지 않아 체간 기울기로만 판단 ⚠

```
골반 높이 > 1.6, 체간 기울기 20° 초과 ~ 45° 이하 (lean_tilt_max_deg)     [279~281줄]
그리고 발이 바닥, 무릎 내각 ≥ 150°                     → Stand Lean Support
```

- **위험**: 평상시 30초 무움직임이면 주의 / 낙상 후 회복 단계 6

---

## Other (기타)

```
위 어느 자세에도 맞지 않으면   → Other (체간 기울기와 골반 높이를 근거에 기록)   [284줄]
```

- **위험**: 정상으로 봄 / 회복 단계 없음

---

## 위험 단계 한눈에 보기

### 평상시 (낙상 장면을 못 봤을 때) ⚠

| 자세 | 이어지면 주의 | 무움직임이면 주의 | 낙상 후 회복 단계 |
|---|---|---|---|
| Stand Upright | – | 30초 | 6 (3초 유지 시 회복) |
| Stand One Leg | 3초 | – | 6 |
| Stand Lean Support | – | 30초 | 6 |
| Walking | – | – | 6 |
| Forward Flexion | – | 30초 | 6 |
| Squat Partial · Squat Deep | – | 30초 | 5 |
| Sit Chair Upright | – | – | 5 |
| Sit Chair Slumped | 10초 | – | 5 |
| Sit Heel | – | 30초 | 5 |
| Kneel Bilateral · Kneel Half L / R | – | 30초 | 5 |
| Quadruped · Bear Pose | 3초 | 30초 | 4 |
| Crawling | 3초 | – | 4 |
| Sit Floor Side · Knees Up · Cross · Long · Sit Floor | – | 30초 | 3 |
| Prone On Elbows · Side Lying On Elbow | 5초 | 30초 | 2 |
| Lying Side L / R · Lying Flat | 5초 | 30초 | 1 |
| Lying Fetal | 3초 | 30초 | 1 |
| Reclined Supported · Other | – | – | 없음 |

- 숫자는 `thresholds.yaml`의 `posture_risk`에서 바꿉니다.
- 평상시에는 **주의(노랑)까지만** 올라갑니다. **위험(빨강)은 낙상 장면을 본 경우에만** 냅니다.
- 주의 자세끼리 바뀌면(예: Lying Side → Lying Fetal) 시간을 이어서 세므로 중간에 "안정"으로 떨어지지 않습니다.

### 낙상 장면을 본 뒤

```
Standing family ──(빠른 골반 하강 + 바닥 도달)──> 🚨 낙상 감지 [위험]
   │
   ├─ 어떤 자세든 30초 무움직임 ───────────────> 🚨 긴급 [위험]   (회복 전까지 유지)
   ├─ 처음 자리 잡은 자세보다 회복 단계가 올라감 ──> ⚠ 스스로 일어나는 중 [주의]
   ├─ 그 외에 움직임이 보임 ────────────────────> ⚠ 낙상 후 움직임 [주의]
   └─ Stand Upright 3초 유지 ───────────────────> ✅ 회복 [비위험]
```

- 낙상 판정 기준(골반 하강 속도 1.5 몸통/초)은 임시값이며 **IMU로 확정 예정**입니다.
- 넘어져서 바로 바닥에 앉은 상태(회복 단계 3)는 "회복 중"이 아닙니다. 그보다 높은 단계로 올라가야 회복 중으로 봅니다.

### 회복 경로

| 회복 단계 | 자세 |
|---|---|
| 1 | Lying Side L / R, Lying Flat, Lying Fetal |
| 2 | Prone On Elbows, Side Lying On Elbow |
| 3 | Sit Floor Side, Sit Floor Long, Sit Floor Cross, Sit Floor Knees Up, Sit Floor |
| 4 | Quadruped, Bear Pose, Crawling |
| 5 | Kneel Bilateral, Kneel Half L / R, Sit Heel, Squat, Sit Chair |
| 6 | Standing family (Stand Upright 3초 유지 시 회복) |

---

## 자세 전이 (터미널에 ↪ 로 표시)

| 터미널 표시 | 언제 |
|---|---|
| 🚨 낙상 위험 감지 | 낙상 판정 (Fall Descent) |
| 조절된 하강 (Controlled Descent) | Standing family → Squat·Kneel·Sit Floor·Lying (낙상 판정 없이) |
| 서기→의자 앉기 / 의자 앉기→서기 | Standing ↔ Sit Chair |
| 앉기→눕기 / 눕기→앉기 | Sit Floor ↔ Lying |
| 측와위→팔꿈치 지지→측좌위 (Side To Sit) | Lying Side → Side Lying On Elbow, Side Lying On Elbow → Sit Floor |
| 돌아눕기 (Roll) | Lying Flat ↔ Lying Side (Lying Fetal은 제외) |
| 눕기→네발 | Lying · Elbow Support → Quadruped family |
| 네발→무릎 서기 | Quadruped family → Kneeling family |
| 반무릎→서기 | Kneel Half → Standing |
| ✅ 회복 확인 (Recovery Path) | 낙상 후 회복 판정 |

---

## 견고성 장치 (YOLO 재학습 없이)

| 장치 | 내용 | yaml 이름 |
|---|---|---|
| 관절 떨림 보정 | 두 프레임 모두 보이는 관절점만 평균 | `keypoint_alpha` 0.6 |
| 깜빡임 방지 | 새 자세가 0.4초 이상 이어져야 바뀜, Unknown은 이전 자세 유지 | `min_hold_s` |
| 바닥 기준선 추정 | 서 있는 모습을 못 봤으면 최근 2초의 가장 낮은 관절점 | `floor_estimate_window_s` |
| 관절 결측 | 규칙마다 필요한 점만 확인. 한쪽 어깨만 보이면 가려진 쪽이 바닥인 Lying Side로 추정 | |
| 카메라 쪽으로 누움 | 기울기 대신 어깨·골반 높이로 Lying을 잡음 | |

## 검증 범위

- 합성 자세 23개가 모두 의도한 자세로 분류됨. 관절점 ±4.5px 흔들기 100회에서 95% 이상, 몸통 길이 ±10%, 좌우 반전에서도 유지 (`tests/test_posture_framework.py`).
- **합성 자세는 규칙에 맞춰 만든 것이라 실제 사람의 정확도를 보증하지 않습니다.** 핑키 시점에서 각 자세를 찍어 `tools/run_video.py`로 확인해야 합니다.

## 확인이 필요한 항목 ⚠

- 평상시 표의 시간 기준, 그리고 **낙상 장면 없이 바닥에 누워 30초 무움직임**을 위험으로 올릴지
- 회복 판정: Stand Upright 3초 vs Sit Floor 도달
- Stand One Leg 3초를 주의로 볼지
- Reclined Supported의 판정 위치, 침대 위 낙상을 이번 범위에서 뺄지
- Quadruped를 평상시에도 주의로 볼지 (바닥 청소 같은 일상 동작과의 구분)
- 정면/측면 기준 (지금은 둘 다 동작, Sit Floor Cross만 정면에서 판단)
- 모든 임시값 (특히 바닥 근처 0.35, 낙상 하강 속도 1.5)
