# 응급 대응과 보고 (낙상 후 음성 안내 → 관제·보호자 보고)

> 코드: `fall_core/incident.py`(대응 순서), `fall_core/fall_metrics.py`(낙상 모양), `fall_core/voice_out.py`(음성)
> 숫자와 문구: `config/thresholds.yaml` 의 `subject`, `fall_type`, `response`, `voice`
> 모든 시간과 문구는 **임시값, 실제 운영 기준으로 확정 예정**입니다. ⚠ = 사용자 확인 필요

---

## 흐름

```
낙상 감지 (Standing family에서 빠른 골반 하강, 또는 Sit Chair·Reclined Supported에서 슬립다운)
  📡 관제: "거실(pinky1): Stand Upright 상태에서 0.5초 만에 수직 낙하 (골반 하강 약 1.6 m/s). 상태를 파악 중입니다."
  │
  ├─ 낙상 후 30초 무움직임 (긴급)
  │    🔊 핑키: "응급상황으로 판단됩니다. 움직이실 수 있으십니까?"
  │    📡 관제: 음성으로 반응을 확인하는 중
  │    │
  │    ├─ 10초 안에 움직임 (또는 스스로 일어나는 자세로 바뀜)
  │    │    🔊 핑키: "움직임이 확인되었습니다. 보호자에게 알리고 계속 지켜보겠습니다."
  │    │    📱 보호자: 넘어짐 감지, 움직임은 있으나 상태 확인 필요
  │    │    (그 뒤 다시 30초 무움직임이면 다시 질문)
  │    │
  │    └─ 10초 동안 반응 없음
  │         🔊 핑키: "10초 후 보호자 및 관제통신센터에 현재 상황을 보고하겠습니다."
  │         └─ 10초 뒤
  │              📡 관제: 119 전달용 보고서 (아래 예시)
  │              📱 보호자: 긴급 알림
  │              🔊 핑키: "보호자와 관제통신센터에 보고했습니다. 도움이 올 때까지 무리하게 움직이지 마세요."
  │
  ├─ 낙상 후 화면에서 5초 이상 사라짐 → 📡 관제: 위치 확인 필요
  └─ 언제든 Stand Upright 3초 유지 (회복)
       🔊 핑키: "일어나신 것이 확인되었습니다. 불편한 곳이 있으면 보호자에게 알려 주세요."
       📡 관제: 사건 종료,  📱 보호자: 알림 해제 (보호자에게 알렸던 경우만)
```

## 119 전달용 보고서 예시

> [14:25:00 발생] 거실(pinky1)에서 양하지 기립 상태였던 분이 0.8초 만에 수직 낙하(제자리에서 주저앉듯 넘어짐)했습니다(골반 하강 약 1.1 m/s, 0.9 m). 현재 우측와위(오른쪽이 바닥) 자세로 50초째 움직임이 없습니다. 일어나려는 시도는 보이지 않았습니다. 음성 질문("응급상황으로 판단됩니다. 움직이실 수 있으십니까?")에 반응이 없었습니다. 카메라 자동 판정이며 확인이 필요합니다.

## 낙상 모양 계산

| 항목 | 계산 | yaml 이름 |
|---|---|---|
| 하강 시작 | 골반이 가장 높던 곳에서 몸통 길이 × 0.1 이상 내려가기 시작한 시점 | `descent_start_drop` |
| 걸린 시간 | 하강 시작 → 바닥 도달 (초) | |
| 하강 속도 | 몸통 길이/초 × 대상자 몸통 길이(m) = m/s (평균, 최고) | `trunk_length_m` ⚠ |
| 수직 낙하 | 골반 수평 이동 ÷ 수직 하강 ≤ 0.5 | `vertical_ratio_max` |
| 옆으로 이동하며 넘어짐 | 위 비율 > 0.5. 화면 기준 왼쪽·오른쪽 방향 표시 (앞·뒤는 2D라 알 수 없음) | |
| 슬립다운 | Sit Chair Upright·Slumped·Reclined Supported → 바닥 자세(Lying·Sit Floor)로 3초 안에, 골반이 몸통 길이 × 0.5 이상 내려옴 | `slip_down_max_s`, `slip_down_min_drop` ⚠ |

- **m/s 값은 근사치**입니다. 2D 화면 투영이고, `trunk_length_m`(지금 임시값 0.5 m)을 줄자로 잰 대상자 몸통 길이(acromion–greater trochanter)로 바꿔야 의미가 있습니다. IMU(Sacrum S2)로 확인 예정입니다.
- 같은 판정을 6초에 걸쳐 천천히 의자에서 바닥으로 앉으면 슬립다운이 **아닙니다** (테스트로 확인).

## 토픽

| 토픽 | 받는 곳 | 내용 (std_msgs/String, JSON) |
|---|---|---|
| `/fall_status` | 터미널 모니터 등 | 매 프레임 자세·경보, `incidents`(진행 중 대응: 상태, 남은 초) |
| `/fall_report` | **관제 시스템** | 사건마다 상태가 바뀔 때: `incident_id`, `state`(FALL_DETECTED·ASKING·ANNOUNCED·REPORTED·RESPONDED·LOST·CLOSED), `fall`(모양·속도), 직전·착지·현재 자세, 무움직임 초, `report_text`(보고 시) |
| `/guardian_alert` | **보호자 알림** | 반응 확인, 긴급 보고, 알림 해제 문장 |
| `/pinky_voice` | 기록 | 핑키가 말한 문장 |

⚠ **토픽까지만 만들었습니다.** 실제로 보호자 휴대폰(문자·메신저)이나 관제 서버로 보내는 부분은 팀의 관제 시스템 방식에 맞춰 이 토픽을 받아 전달해야 합니다. 119 자동 신고는 하지 않습니다 (관제자가 보고서를 확인하고 전달).

## 핑키 스피커로 말하기

```
[PC] fall_core_node ──HTTP POST {"text": ...}──> [핑키] pinky_stream.py /say ──> 핑키 스피커
          └─ 핑키가 말할 수 없거나(501) 연결이 안 되면 ──> PC(노트북) 스피커로 대신 말함
```

- 핑키에서 영상과 음성을 **같은 프로그램**이 처리합니다: `python3 ~/pinky_stream.py`
  - 시작할 때 `음성(/say): 켜짐 - espeak-ng`처럼 나오면 핑키가 말할 수 있는 상태입니다.
  - `사용할 수 없음`이 나오면 핑키에 한국어 음성 도구가 없는 것입니다. 인터넷이 되는 상태에서 `sudo apt install espeak-ng`.
  - ⚠ **핑키에 음성용 스피커(오디오 출력)가 있는지는 확인하지 못했습니다.** 부저만 있다면 PC 스피커가 대신 말합니다.
- 브라우저 시험: `http://192.168.4.1:8000/say?text=안녕하세요`
- 소리 없이 시험: 핑키에서 `python3 ~/pinky_stream.py --voice-dry-run` (말할 문장만 터미널에 출력)
- 노드 옵션: `-p voice_target:=pinky`(기본, 실패하면 PC) / `pc` / `both` / `off`
- 음성 주소는 영상 주소에서 자동으로 만듭니다 (`…:8000/video` → `…:8000/say`). 다르면 `-p robot_say_url:=...`
- 문구는 `thresholds.yaml`의 `voice`에서 바꿉니다. 빈 문자열이면 말하지 않습니다 (`on_fall`은 지금 꺼 둠).

### 목소리 바꾸기

| 방법 | 어디서 | 예 |
|---|---|---|
| 목소리 종류 | `voice_style.voice_name` | `"Korean+Alicia"` (목록: `python3 tools/voice_preview.py --list`) |
| 빠르기·높이·크기 | `voice_style.rate` / `pitch` / `volume` | -100 ~ 100 |
| **내 목소리로 녹음** | `voice_style.audio_dir` 폴더의 `<문구 이름>.wav` | `ask.wav`가 있으면 기계음 대신 재생 |

```bash
python3 tools/voice_preview.py --all                                   # 지금 설정으로 모든 문구 들어 보기
python3 tools/voice_preview.py --all --voice-name "Korean+Alicia" --pitch 30   # 다른 목소리로 미리 듣기
python3 tools/voice_preview.py --record ask                            # 'ask' 문구를 내 목소리로 녹음 (~/fall_voice/ask.wav)
python3 tools/voice_preview.py --record-all                            # 모든 문구 차례로 녹음
scp -r ~/fall_voice pinky@192.168.4.1:~/                                # 핑키에서도 녹음 재생
```

문구 이름: `ask`(질문), `announce`(보고 예고), `responded`(반응 확인), `reported`(보고 완료), `recovered`(회복).
녹음 파일을 쓰면 `announce`처럼 숫자가 들어간 문구는 `report_delay_s`를 바꿔도 녹음 내용은 그대로이니 함께 다시 녹음하세요.
- `/say`는 인증이 없어 같은 와이파이의 누구나 핑키를 말하게 할 수 있습니다. 필요할 때만 켜세요.

## 확인이 필요한 항목 ⚠

- 질문 시점(낙상 후 30초 무움직임), 반응 대기 10초, 보고 예고 10초가 운영 기준에 맞는지
- 낙상 순간에도 바로 말을 걸지 (`voice.on_fall`, 지금은 꺼짐)
- 보고 예고 중에 움직임이 생겨도 그대로 보고할지 (지금은 보고하고 "보고 직전 움직임 확인"을 보고서에 적음)
- 보호자에게 어느 단계부터 알릴지 (지금은 반응 확인·긴급 보고·해제)
- `trunk_length_m`, 슬립다운 3초 기준
- 핑키 스피커 유무
