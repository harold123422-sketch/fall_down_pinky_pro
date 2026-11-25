"""낙상 보고서와 응급 대응 순서 (음성 질문 -> 무반응 -> 보고 예고 -> 관제·보호자 보고), 음성 출력."""
import synthetic_poses as sp
from fall_core import FallCoreEngine
from fall_core.incident import IncidentManager
from fall_core.voice_out import VoiceOut, choose_tts, local_say

WALL0 = 1795500000.0


class Run:
    """엔진 + 대응 순서를 함께 돌리고, 할 일(Action)을 시각과 함께 모은다."""

    def __init__(self, cfg):
        self.sim = sp.Sim(FallCoreEngine(cfg))
        self.mgr = IncidentManager(cfg, "pinky1")
        self.acts, self.n = [], 0

    def go(self):
        for t, r in self.sim.log[self.n:]:
            self.acts += [(t, a) for a in self.mgr.update(t, WALL0 + t, [r])]
        self.n = len(self.sim.log)
        return self

    def kinds(self, kind):
        return [(t, a) for t, a in self.acts if a.kind == kind]

    def voices(self):
        return [a.text for _, a in self.kinds("voice")]

    def states(self):
        return [a.data.get("state") for _, a in self.kinds("control")]


def _fall_and_lie(cfg, still_s):
    run = Run(cfg)
    run.sim.hold(sp.standing(), 3)
    run.sim.move(sp.standing(), sp.side_lying(), 0.6)
    run.sim.hold(sp.side_lying(), still_s)
    return run.go()


def test_no_response_reports_to_control_and_guardian(cfg):
    run = _fall_and_lie(cfg, 56)
    v = cfg["voice"]
    assert run.voices() == [v["ask"], v["announce"].format(delay=10), v["reported"]]
    assert run.states() == ["FALL_DETECTED", "ASKING", "ANNOUNCED", "REPORTED"]
    t_fall = run.sim.event_times("FALL_EVENT")[0]
    t_ask = [t for t, a in run.kinds("voice") if a.data["key"] == "ask"][0]
    t_ann = [t for t, a in run.kinds("voice") if a.data["key"] == "announce"][0]
    t_rep = [t for t, a in run.kinds("control") if a.data["state"] == "REPORTED"][0]
    assert 27 <= t_ask - t_fall <= 36                  # 낙상 후 약 30초 무움직임에서 질문
    assert abs((t_ann - t_ask) - 10) < 0.2              # 10초 무반응 -> 보고 예고
    assert abs((t_rep - t_ann) - 10) < 0.2              # 10초 뒤 보고
    report = [a for _, a in run.kinds("control") if a.data["state"] == "REPORTED"][0]
    text = report.data["report_text"]
    for must in ("m/s", "수직 낙하", "우측와위", "움직임이 없습니다", "반응이 없었습니다", "확인이 필요합니다", "거실"):
        assert must in text, must
    assert report.data["fall"]["peak_speed_mps"] > 1.0 and report.data["pre_posture"] == "STAND_UPRIGHT"
    guard = run.kinds("guardian")
    assert len(guard) == 1 and "관제통신센터에 함께 보고" in guard[0][1].text


def test_movement_while_asking_is_responded_not_reported(cfg):
    run = _fall_and_lie(cfg, 34)                         # 질문 직후
    lying = sp.side_lying()
    moved = sp.shift(lying, (9, 10), 60, -40)            # 팔을 움직여 대답
    run.sim.move(lying, moved, 1.0)
    run.sim.hold(moved, 8)
    run.go()
    assert "RESPONDED" in run.states() and "REPORTED" not in run.states()
    assert cfg["voice"]["responded"] in run.voices()
    assert any("움직임은 확인되었지만" in a.text for _, a in run.kinds("guardian"))


def test_recovery_closes_and_releases_guardian(cfg):
    run = _fall_and_lie(cfg, 56)
    run.sim.move(sp.side_lying(), sp.standing(), 2)
    run.sim.hold(sp.standing(), 5)
    run.go()
    assert run.states()[-1] == "CLOSED"
    assert run.voices()[-1] == cfg["voice"]["recovered"]
    assert "[알림 해제]" in run.kinds("guardian")[-1][1].text      # 보호자에게 알렸으면 해제도 알림
    assert run.mgr.summaries(run.sim.t) == []


def test_recovery_before_ask_does_not_notify_guardian(cfg):
    run = _fall_and_lie(cfg, 5)
    run.sim.move(sp.side_lying(), sp.standing(), 2)
    run.sim.hold(sp.standing(), 5)
    run.go()
    assert run.states() == ["FALL_DETECTED", "CLOSED"]
    assert run.kinds("guardian") == []                    # 보호자에게 알린 적이 없으면 해제 알림도 없음


def test_slip_down_from_chair_creates_incident(cfg):
    run = Run(cfg)
    chair, floor = sp.chair_upright(), sp.sit_floor_long()
    run.sim.hold(chair, 4)
    run.sim.move(chair, floor, 1.2)
    run.sim.hold(floor, 3)
    run.go()
    ctrl = run.kinds("control")
    assert ctrl and ctrl[0][1].data["fall_type"] == "SLIP_DOWN"
    assert "슬립다운" in ctrl[0][1].text and "의자 앉기" in ctrl[0][1].text


def test_slow_sit_down_from_chair_is_not_slip(cfg):
    run = Run(cfg)
    chair, floor = sp.chair_upright(), sp.sit_floor_long()
    run.sim.hold(chair, 4)
    run.sim.move(chair, floor, 6.0)                       # 6초에 걸쳐 스스로 앉음
    run.sim.hold(floor, 3)
    run.go()
    assert run.kinds("control") == []


def test_lateral_fall_shape(cfg):
    run = Run(cfg)
    far = sp.side_lying()
    far[:, 0] += 250                                      # 골반이 옆으로 크게 이동하며 넘어짐
    run.sim.hold(sp.standing(), 3)
    run.sim.move(sp.standing(), far, 0.6)
    run.sim.hold(far, 2)
    run.go()
    m = run.kinds("control")[0][1].data["fall"]
    assert m["shape"] == "LATERAL" and m["direction"] == "화면 오른쪽"
    assert "이동하며 넘어짐" in m["shape_ko"]


def test_person_lost_after_fall_is_reported(cfg):
    run = _fall_and_lie(cfg, 3)
    run.sim.gap(7)
    run.go()
    for t in (run.sim.t + 0.1,):                          # 검출이 없는 프레임도 대응 순서에 알려 줌
        run.acts += [(t, a) for a in run.mgr.update(t, WALL0 + t, [])]
    assert "LOST" in run.states()


def test_metrics_in_meters_follow_trunk_length(cfg):
    cfg["subject"]["trunk_length_m"] = 1.0
    run = _fall_and_lie(cfg, 2)
    m = run.kinds("control")[0][1].data["fall"]
    assert abs(m["peak_speed_mps"] - m["peak_speed_trunk_s"]) < 1e-6     # 몸통 1m면 m/s = 몸통길이/초


# ---------------------------------------------------------------- 음성 출력
def test_voice_falls_back_to_pc_when_pinky_fails():
    said = []
    vo = VoiceOut("pinky", "http://x/say", log=lambda s: None, poster=lambda t, k=None: False,
                  pc_sayer=lambda t, k=None: said.append(t) or "pc", sync=True)
    assert vo.say("테스트") == ["pc"] and said == ["테스트"]


def test_voice_uses_pinky_when_it_works():
    vo = VoiceOut("pinky", "http://x/say", log=lambda s: None, poster=lambda t, k=None: True,
                  pc_sayer=lambda t, k=None: "pc", sync=True)
    assert vo.say("테스트") == ["pinky"]


def test_voice_off_and_both():
    assert VoiceOut("off", log=lambda s: None, sync=True).say("x") == []
    vo = VoiceOut("both", "http://x/say", log=lambda s: None, poster=lambda t, k=None: True,
                  pc_sayer=lambda t, k=None: "pc", sync=True)
    assert vo.say("x") == ["pinky", "pc"]


def test_choose_tts_order():
    assert choose_tts(lambda c: c in ("espeak", "espeak-ng"))[0] == "espeak-ng"
    assert choose_tts(lambda c: False) is None
    assert local_say("x", which=lambda c: False) is None
    assert local_say("x", which=lambda c: c == "espeak", dry_run=True) == "dry-run:espeak"


def test_voice_style_is_applied_to_command():
    from fall_core.voice_out import build_tts_command
    style = {"voice_name": "Korean+Alicia", "rate": 10, "pitch": 30}
    spd = build_tts_command("안녕", style, which=lambda c: c == "spd-say")
    assert spd[:3] == ["spd-say", "-o", "espeak-ng"] and "-y" in spd and "Korean+Alicia" in spd
    assert spd[spd.index("-r") + 1] == "10" and spd[spd.index("-p") + 1] == "30" and spd[-1] == "안녕"
    esp = build_tts_command("안녕", {"voice_name": "Korean+Alicia", "pitch": 30}, which=lambda c: c == "espeak-ng")
    assert esp[esp.index("-v") + 1] == "ko+Alicia" and esp[esp.index("-p") + 1] == "65"


def test_recorded_audio_is_preferred(tmp_path):
    (tmp_path / "ask.wav").write_bytes(b"RIFF")
    style = {"audio_dir": str(tmp_path)}
    yes = lambda c: c in ("paplay", "spd-say")  # noqa: E731
    assert local_say("x", style, key="ask", which=yes, dry_run=True) == "dry-run:audio:ask.wav"
    assert local_say("x", style, key="announce", which=yes, dry_run=True) == "dry-run:spd-say"   # 녹음 없으면 합성
