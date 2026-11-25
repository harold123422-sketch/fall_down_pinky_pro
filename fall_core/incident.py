"""낙상 사건 기록과 응급 대응 순서 (음성 질문 -> 보고). Python.

엔진 결과(TrackResult)를 받아 낙상 사건마다 아래 순서를 따라가며 할 일(Action)을 돌려준다.

  낙상 감지 ──> (낙상 후 30초 무움직임 = 긴급)
     │            └─> 🔊 "응급상황으로 판단됩니다. 움직이실 수 있으십니까?"        [음성 질문 중]
     │                   ├─ 10초 안에 움직임 ──> 🔊 "움직임이 확인되었습니다..."     [반응 확인] -> 보호자·관제 알림
     │                   │                        (다시 30초 무움직임이면 다시 질문)
     │                   └─ 반응 없음 ──> 🔊 "10초 후 ... 보고하겠습니다."          [보고 예고]
     │                                     └─ 10초 뒤 ──> 📡 관제 보고 + 📱 보호자 알림 [보고 완료]
     └─ 언제든 기립 3초 유지(회복) ──> 🔊 "일어나신 것이 확인되었습니다..."           [회복·종료]

Action.kind
  voice    : 핑키(또는 PC 스피커)로 말할 문장
  control  : 관제 시스템 보고 (/fall_report)
  guardian : 보호자 알림 (/guardian_alert)

시간 기준과 문구는 config/thresholds.yaml 의 response, voice 블록. 전부 [확인 필요].
카메라 판정은 보조 신호다. 보고 문장에도 "카메라 자동 판정이며 확인이 필요합니다"를 넣는다.
"""
import time
from dataclasses import dataclass, field

from fall_core.posture_framework import KO

STATE_KO = {
    "FALL_DETECTED": "낙상 감지", "ASKING": "음성 질문 중", "RESPONDED": "반응 확인", "ANNOUNCED": "보고 예고",
    "REPORTED": "보호자·관제 보고 완료", "LOST": "화면에서 사라짐", "CLOSED": "회복·종료",
}
STAGE_KO = {1: "바닥에 누움", 2: "팔꿈치 지지", 3: "바닥 앉기", 4: "네발 자세", 5: "무릎 서기", 6: "서기"}


@dataclass
class Action:
    kind: str                  # voice | control | guardian
    text: str
    data: dict = field(default_factory=dict)


@dataclass
class Incident:
    incident_id: str
    track_id: int
    t_fall: float              # 엔진 시각 (초)
    wall_fall: float           # 실제 시각 (time.time)
    fall_type: str
    metrics: dict
    pre_posture: str
    state: str = "FALL_DETECTED"
    t_state: float = 0.0
    last_seen_t: float = 0.0
    landing_posture: str = None
    current_posture: str = None
    immobile_s: float = 0.0
    max_stage: int = None
    ask_t: float = None
    report_due: float = None
    asked: int = 0
    responded: int = 0
    guardian_notified: bool = False
    moved_during_countdown: bool = False
    lost_notified: bool = False
    log: list = field(default_factory=list)       # [(실제 시각 문자열, 상태)]


def _ko(name):
    return KO.get(name, name or "알 수 없음")


def _hms(wall):
    return time.strftime("%H:%M:%S", time.localtime(wall))


class IncidentManager:
    def __init__(self, cfg, camera_id="cam0", location=None):
        self.cfg = cfg
        self.r = cfg["response"]
        self.v = cfg["voice"]
        self.camera_id = camera_id
        self.location = location or cfg.get("subject", {}).get("location", "")
        ask_on = self.r["ask_on"]
        self.ask_alert = "EMERGENCY_POST_FALL_IMMOBILE" if ask_on == "EMERGENCY" else ask_on
        self.incidents = {}       # key = 낙상 시각(엔진 시각)

    # ------------------------------------------------------------------ 공개 API
    def update(self, t, wall, results):
        """엔진 결과 한 프레임을 반영하고, 이번에 할 일(Action) 목록을 돌려준다."""
        actions, seen = [], set()
        for r in results:
            ft = r.fall_event_t_s
            if ft is None or ft != ft:
                continue
            key = round(ft, 6)
            inc = self.incidents.get(key)
            if inc is None and "FALL_EVENT" in r.events:
                inc = self._new(r, t, wall)
                self.incidents[key] = inc
                actions += self._on_fall(inc, r, t, wall)
            if inc is None or inc.state == "CLOSED":
                continue
            seen.add(key)
            if inc.lost_notified:
                inc.lost_notified = False
                actions.append(self._control(inc, wall, f"{self._where()}: 사람이 다시 보입니다. 계속 지켜봅니다."))
            inc.track_id, inc.last_seen_t = r.track_id, t
            inc.current_posture = r.posture_class
            inc.landing_posture = inc.landing_posture or r.landing_posture
            inc.immobile_s = r.immobile_elapsed_s
            if r.recovery_stage is not None:
                inc.max_stage = max(inc.max_stage or 0, r.recovery_stage)
            actions += self._step(inc, r, t, wall)
        for key, inc in self.incidents.items():                     # 낙상 후 화면에서 사라진 사람
            if key in seen or inc.state == "CLOSED" or inc.lost_notified:
                continue
            if t - inc.last_seen_t >= self.r["lost_notice_s"]:
                inc.lost_notified = True
                actions.append(self._control(inc, wall, f"{self._where()}: 낙상 후 사람이 화면에서 "
                                             f"{t - inc.last_seen_t:.0f}초째 보이지 않습니다. 위치 확인이 필요합니다.",
                                             state="LOST"))
        return actions

    def summaries(self, t):
        """/fall_status 에 넣을 진행 중 사건 요약 (터미널 상태 줄용)."""
        out = []
        for inc in self.incidents.values():
            if inc.state == "CLOSED":
                continue
            item = {"incident_id": inc.incident_id, "track_id": inc.track_id, "state": inc.state,
                    "state_ko": STATE_KO[inc.state], "immobile_s": round(inc.immobile_s, 1)}
            if inc.state == "ASKING" and inc.ask_t is not None:
                item["wait_left_s"] = round(max(0.0, self.r["response_window_s"] - (t - inc.ask_t)), 1)
            if inc.state == "ANNOUNCED" and inc.report_due is not None:
                item["countdown_s"] = round(max(0.0, inc.report_due - t), 1)
            out.append(item)
        return out

    # ------------------------------------------------------------------ 상태 진행
    def _new(self, r, t, wall):
        iid = f"{self.camera_id}-{time.strftime('%Y%m%d-%H%M%S', time.localtime(wall))}-{r.track_id}"
        return Incident(iid, r.track_id, r.fall_event_t_s, wall, r.fall_type or "FALL", r.fall_metrics or {},
                        r.pre_fall_posture, t_state=t, last_seen_t=t)

    def _set(self, inc, state, t, wall):
        inc.state, inc.t_state = state, t
        inc.log.append((_hms(wall), state))

    def _on_fall(self, inc, r, t, wall):
        inc.log.append((_hms(wall), "FALL_DETECTED"))
        acts = [self._control(inc, wall, self.fall_summary(inc))]
        if self.v.get("on_fall"):
            acts.insert(0, Action("voice", self.v["on_fall"], {"incident_id": inc.incident_id, "key": "on_fall"}))
        return acts

    def _step(self, inc, r, t, wall):
        acts = []
        moving = r.window_status.name == "MOVING" or r.alert.name == "SELF_RECOVERABLE"
        if "RECOVERED" in r.events or r.mode.name == "RECOVERED":
            self._set(inc, "CLOSED", t, wall)
            acts.append(self._voice(inc, "recovered"))
            acts.append(self._control(inc, wall, f"{self._where()}: 스스로 일어나 서 있는 것이 확인되어 사건을 종료합니다.",
                                      state="CLOSED"))
            if inc.guardian_notified:
                acts.append(self._guardian(inc, wall, f"[알림 해제] {self._where()}: {_hms(wall)}에 스스로 일어난 것이 "
                                                      "확인되었습니다. 불편한 곳이 없는지 확인해 주세요."))
            return [a for a in acts if a is not None]

        if inc.state in ("FALL_DETECTED", "LOST") and r.alert.name == self.ask_alert:
            acts += self._ask(inc, t, wall)
        elif inc.state == "ASKING":
            if moving:
                self._set(inc, "RESPONDED", t, wall)
                inc.responded += 1
                acts.append(self._voice(inc, "responded"))
                acts.append(self._control(inc, wall, f"{self._where()}: 음성 질문 후 움직임이 확인되었습니다. "
                                          f"현재 {_ko(inc.current_posture)}. 계속 지켜봅니다."))
                acts.append(self._guardian(inc, wall, f"[낙상 알림] {_hms(inc.wall_fall)} {self._where()}에서 넘어짐이 "
                                                      "감지되었습니다. 음성 질문 후 움직임은 확인되었지만 상태 확인이 필요합니다."))
                inc.guardian_notified = True
            elif t - inc.ask_t >= self.r["response_window_s"]:
                self._set(inc, "ANNOUNCED", t, wall)
                inc.report_due = t + self.r["report_delay_s"]
                acts.append(self._voice(inc, "announce"))
                acts.append(self._control(inc, wall, f"{self._where()}: 음성 질문에 {self.r['response_window_s']:.0f}초 동안 "
                                          f"반응이 없습니다. {self.r['report_delay_s']:.0f}초 후 보고합니다."))
        elif inc.state == "ANNOUNCED":
            if moving:
                inc.moved_during_countdown = True
            if t >= inc.report_due:
                self._set(inc, "REPORTED", t, wall)
                text = self.report_text(inc, wall)
                acts.append(self._control(inc, wall, text, full=True))
                acts.append(self._guardian(inc, wall, f"[낙상 긴급 알림] {_hms(inc.wall_fall)} {self._where()}에서 넘어짐이 "
                                                      f"감지되었고 {inc.immobile_s:.0f}초 이상 움직임이 없어 관제통신센터에 "
                                                      "함께 보고했습니다. 바로 확인해 주세요."))
                inc.guardian_notified = True
                acts.append(self._voice(inc, "reported"))
        elif inc.state == "RESPONDED" and r.immobile_elapsed_s >= self.r["reask_immobile_s"] \
                and t - inc.t_state >= self.r["reask_immobile_s"]:
            acts += self._ask(inc, t, wall)                          # 반응 뒤 다시 오래 움직이지 않음
        return [a for a in acts if a is not None]

    def _ask(self, inc, t, wall):
        self._set(inc, "ASKING", t, wall)
        inc.ask_t = t
        inc.asked += 1
        return [self._voice(inc, "ask"),
                self._control(inc, wall, f"{self._where()}: 낙상 후 {inc.immobile_s:.0f}초째 움직임이 없어 "
                                         "음성으로 반응을 확인하고 있습니다.")]

    # ------------------------------------------------------------------ 문장
    def _where(self):
        return f"{self.location}({self.camera_id})" if self.location else self.camera_id

    def fall_summary(self, inc):
        m = inc.metrics or {}
        if not m:
            return f"{self._where()}: {_ko(inc.pre_posture)} 상태에서 낙상이 감지되었습니다. 상태를 파악 중입니다."
        return (f"{self._where()}: {_ko(inc.pre_posture)} 상태에서 {m.get('duration_s', 0):.1f}초 만에 "
                f"{m.get('shape_ko', '넘어짐')} (골반 하강 약 {m.get('peak_speed_mps', 0):.1f} m/s). 상태를 파악 중입니다.")

    def report_text(self, inc, wall):
        """119에 그대로 읽어 줄 수 있는 보고 문장."""
        m = inc.metrics or {}
        parts = [f"[{_hms(inc.wall_fall)} 발생] {self._where()}에서 {_ko(inc.pre_posture)} 상태였던 분이"]
        if m:
            parts.append(f"{m.get('duration_s', 0):.1f}초 만에 {m.get('shape_ko', '넘어짐')}했습니다"
                         f"(골반 하강 약 {m.get('peak_speed_mps', 0):.1f} m/s, {m.get('drop_m', 0):.1f} m).")
        else:
            parts.append("넘어졌습니다.")
        parts.append(f"현재 {_ko(inc.current_posture)} 자세로 {inc.immobile_s:.0f}초째 움직임이 없습니다.")
        if inc.max_stage and inc.max_stage >= 2:
            parts.append(f"일어나려는 시도가 있었습니다(최고 {STAGE_KO.get(inc.max_stage, '')}).")
        else:
            parts.append("일어나려는 시도는 보이지 않았습니다.")
        parts.append(f"음성 질문(\"{self.v['ask']}\")에 반응이 없었습니다.")
        if inc.moved_during_countdown:
            parts.append("보고 직전에 약간의 움직임이 확인되었습니다.")
        parts.append("카메라 자동 판정이며 확인이 필요합니다.")
        return " ".join(parts)

    # ------------------------------------------------------------------ Action 만들기
    def _voice(self, inc, key):
        text = self.v.get(key, "")
        if not text:
            return None
        text = text.format(delay=int(round(self.r["report_delay_s"])))
        return Action("voice", text, {"incident_id": inc.incident_id, "key": key})

    def _control(self, inc, wall, text, state=None, full=False):
        m = inc.metrics or {}
        data = {
            "incident_id": inc.incident_id, "state": state or inc.state, "state_ko": STATE_KO[state or inc.state],
            "time": _hms(wall), "fall_time": _hms(inc.wall_fall),
            "camera_id": self.camera_id, "location": self.location,
            "track_id": inc.track_id, "fall_type": inc.fall_type, "fall": m,
            "pre_posture": inc.pre_posture, "landing_posture": inc.landing_posture,
            "current_posture": inc.current_posture,
            "immobile_s": round(inc.immobile_s, 1), "max_recovery_stage": inc.max_stage,
            "voice_asked": inc.asked, "responded": inc.responded, "guardian_notified": inc.guardian_notified,
            "summary": text, "full_report": full,
        }
        if full:
            data["report_text"] = text
        return Action("control", text, data)

    def _guardian(self, inc, wall, text):
        return Action("guardian", text, {"incident_id": inc.incident_id, "time": _hms(wall), "state": inc.state,
                                         "location": self.location, "camera_id": self.camera_id})

