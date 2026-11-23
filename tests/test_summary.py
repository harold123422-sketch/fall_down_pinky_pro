"""20초 요약: 시간 창 모으기, 종합 판단 문장, 단계가 올라갈 때만 즉시 알림."""
import synthetic_poses as sp
from fall_core import FallCoreEngine
from fall_core.monitor_view import WindowSummary, escalations
from fall_core.status import build_status


def _msgs(sim, cfg):
    return [(t, build_status("cam0", t, [d], [r], cfg)) for (t, r), d in zip(sim.log, sim.dets)]


def _summarize(msgs, interval=1000.0):
    ws = WindowSummary(interval)
    for t, m in msgs:
        ws.add(t, m, f"t={t:.0f}")
    return ws.flush("끝", color=False)


def test_normal_standing_summary(cfg):
    sim = sp.Sim(FallCoreEngine(cfg))
    sim.hold(sp.standing(), 15)
    text = _summarize(_msgs(sim, cfg))
    assert "20초 요약" not in text and "1000초 요약" in text      # 제목에 구간 길이가 들어감
    # 서 있음은 0.5초 이상 유지돼야 확정되므로 처음 0.5초는 제외되어 100%가 아니라 90%대
    assert "특이사항 없음" in text and "서 있음 9" in text
    assert "단계 변화" not in text                                 # 단계가 안 바뀌면 생략
    assert "관절 위치" in text and "발목" in text


def test_caution_when_standing_still_30s(cfg):
    sim = sp.Sim(FallCoreEngine(cfg))
    sim.hold(sp.standing(), 35)
    text = _summarize(_msgs(sim, cfg))
    assert "비위험(" in text and "주의(" in text and "→" in text   # 단계 변화 기록
    assert "서서 정지(확인 요청)" in text
    assert "정지가 최대" in text


def test_danger_after_fall_says_check_now(cfg):
    sim = sp.Sim(FallCoreEngine(cfg))
    sim.hold(sp.standing(), 3)
    sim.move(sp.standing(), sp.side_lying(), 0.6)
    sim.hold(sp.side_lying(), 36)
    text = _summarize(_msgs(sim, cfg))
    assert "[위험]" in text and "위험한 상태입니다" in text and "즉시 확인" in text
    assert "낙상 감지" in text and "낙상 후 정지(긴급)" in text


def test_recovered_after_danger_is_reported_as_past(cfg):
    sim = sp.Sim(FallCoreEngine(cfg))
    sim.hold(sp.standing(), 3)
    sim.move(sp.standing(), sp.side_lying(), 0.6)
    sim.hold(sp.side_lying(), 8)
    sim.move(sp.side_lying(), sp.standing(), 2)
    sim.hold(sp.standing(), 6)
    text = _summarize(_msgs(sim, cfg))
    assert "위험 단계가 있었지만 지금은 비위험" in text


def test_many_unknown_says_check_camera(cfg):
    pose = sp.with_conf(sp.with_conf(sp.standing(), 15, 0.1), 16, 0.1)
    sim = sp.Sim(FallCoreEngine(cfg))
    sim.hold(pose, 10)
    text = _summarize(_msgs(sim, cfg))
    assert "관절이 잘 보이지 않아" in text and "카메라 각도" in text


def test_no_person_and_no_signal():
    ws = WindowSummary(20)
    empty = {"camera_id": "c", "stamp": 0, "state": "NO_PERSON", "level": "SAFE",
             "keypoint_conf_min": 0.5, "limits": {}, "tracks": []}
    for i in range(5):
        ws.add(float(i), empty, f"t{i}")
    assert "사람이 보이지 않았습니다" in ws.flush("끝", color=False)
    assert "신호가 없었습니다" in WindowSummary(20).flush("끝", color=False)


def test_window_due_and_reset_after_flush(cfg):
    ws = WindowSummary(20.0)
    sim = sp.Sim(FallCoreEngine(cfg))
    sim.hold(sp.standing(), 1)
    t, m = _msgs(sim, cfg)[0]
    ws.add(100.0, m, "a")
    assert not ws.due(119.9) and ws.due(120.0)
    ws.flush("b", color=False)
    assert ws.t0 is None and ws.n == 0 and not ws.due(500.0)


def test_escalations_only_when_level_rises(cfg):
    sim = sp.Sim(FallCoreEngine(cfg))
    sim.hold(sp.standing(), 33)                                # 주의까지 올라감
    msgs = _msgs(sim, cfg)
    prev, lines = {}, []
    for _, m in msgs:
        lines += escalations(prev, m, "t", color=False)
    assert len(lines) == 1 and "[주의]" in lines[0]            # 주의로 '올라간' 한 번만 알림
    sim.move(sp.standing(), sp.side_lying(), 0.6)
    sim.hold(sp.side_lying(), 2)
    for _, m in _msgs(sim, cfg)[len(msgs):]:
        lines += escalations(prev, m, "t", color=False)
    assert len(lines) == 2 and "[위험]" in lines[1]            # 위험으로 올라갈 때 한 번 더
