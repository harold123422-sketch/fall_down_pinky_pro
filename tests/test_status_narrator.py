"""상태 한 줄 + 변화 알림: 안정이면 새 줄 없음, 위험은 빨강 멘트, 회복은 초록."""
import synthetic_poses as sp
from fall_core import FallCoreEngine
from fall_core.monitor_view import StatusNarrator, display_width, fit_width
from fall_core.status import build_status

RED, EMERG, YELLOW, GREEN = "\x1b[1;31m", "\x1b[1;97;41m", "\x1b[33m", "\x1b[32m"


def _feed(narr, sim, cfg, start=0):
    """sim.log[start:] 를 메시지로 만들어 넣고, 새로 생긴 멘트 줄과 마지막 메시지를 돌려준다."""
    lines, msg = [], None
    for (t, r), d in list(zip(sim.log, sim.dets))[start:]:
        msg = build_status("cam0", t, [d], [r], cfg)
        lines += narr.update(msg, t, f"{t:05.1f}")
    return lines, msg


def test_stable_standing_prints_one_line_then_only_status(cfg):
    sim, narr = sp.Sim(FallCoreEngine(cfg)), StatusNarrator(color=False)
    sim.hold(sp.standing(), 20)
    lines, msg = _feed(narr, sim, cfg)
    assert len(lines) == 1 and "안정 상태입니다" in lines[0]      # 20초 동안 새 줄은 처음 1줄뿐
    status = narr.status_line(msg, sim.t)
    assert "안정 상태 진행 중" in status and "서 있음" in status and "안정 유지" in status


def test_fall_is_red_with_assessing_message(cfg):
    sim, narr = sp.Sim(FallCoreEngine(cfg)), StatusNarrator(color=True)
    sim.hold(sp.standing(), 3)
    n = len(sim.log)
    _feed(narr, sim, cfg)
    sim.move(sp.standing(), sp.side_lying(), 0.6)
    sim.hold(sp.side_lying(), 3)
    lines, msg = _feed(narr, sim, cfg, n)
    assert any("낙상 위험 감지" in ln and "파악 중" in ln and ln.startswith(RED) for ln in lines)
    assert any("몸 상태" in ln and "누워" in ln for ln in lines)
    st = narr.status_line(msg, sim.t)
    assert st.startswith(RED) and "낙상 후 움직임 확인 중" in st


def test_emergency_then_recovery(cfg):
    sim, narr = sp.Sim(FallCoreEngine(cfg)), StatusNarrator(color=True)
    sim.hold(sp.standing(), 3)
    sim.move(sp.standing(), sp.side_lying(), 0.6)
    sim.hold(sp.side_lying(), 33)
    lines, msg = _feed(narr, sim, cfg)
    emerg = [ln for ln in lines if "긴급" in ln]
    assert len(emerg) == 1 and emerg[0].startswith(EMERG) and "즉시 확인" in emerg[0]
    assert "긴급 상황 지속 중" in narr.status_line(msg, sim.t)
    n = len(sim.log)
    sim.move(sp.side_lying(), sp.standing(), 2)
    sim.hold(sp.standing(), 5)
    lines, msg = _feed(narr, sim, cfg, n)
    assert any("회복 확인" in ln and ln.startswith(GREEN) for ln in lines)
    assert "회복 후 안정 상태 진행 중" in narr.status_line(msg, sim.t)


def test_check_is_yellow_and_clears_green(cfg):
    sim, narr = sp.Sim(FallCoreEngine(cfg)), StatusNarrator(color=True)
    sim.hold(sp.standing(), 33)
    lines, _ = _feed(narr, sim, cfg)
    assert any("주의" in ln and ln.startswith(YELLOW) for ln in lines)
    n = len(sim.log)
    waving = sp.shift(sp.standing(), (9, 10), 70, -90)
    sim.move(sp.standing(), waving, 1.0)
    sim.hold(waving, 1)
    lines, _ = _feed(narr, sim, cfg, n)
    assert any("다시 움직임이 확인" in ln and ln.startswith(GREEN) for ln in lines)


def test_person_disappears_after_fall_is_red(cfg):
    sim, narr = sp.Sim(FallCoreEngine(cfg)), StatusNarrator(color=False)
    sim.hold(sp.standing(), 3)
    sim.move(sp.standing(), sp.side_lying(), 0.6)
    sim.hold(sp.side_lying(), 2)
    _feed(narr, sim, cfg)
    empty = {"camera_id": "c", "stamp": 0, "state": "NO_PERSON", "level": "SAFE",
             "keypoint_conf_min": 0.5, "limits": {}, "tracks": []}
    lines = narr.update(empty, sim.t + 1, "x")
    assert len(lines) == 1 and "낙상 후 사람이 화면에서 사라졌습니다" in lines[0]
    assert "사람이 보이지 않습니다" in narr.status_line(empty, sim.t + 2)


def test_status_line_fits_terminal_width():
    s = "● 안정 상태 진행 중... (사람 #1 · 서 있음 · 정지 12초째 · 안정 유지 3분 12초)"
    cut = fit_width(s, 40)
    assert display_width(cut) <= 40 and cut.endswith("…")
    assert fit_width("짧음", 40) == "짧음"
