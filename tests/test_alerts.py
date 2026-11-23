"""지시서 6절 테스트 10~16: FALL_EVENT, 낙상 후 무움직임 -> 긴급, 회복, track 소실."""
import pytest

import synthetic_poses as sp
from fall_core import FallCoreEngine


def _fall(cfg, target, still_s, fall_s=0.6, **kw):
    """기립 3초 -> fall_s초 동안 target 자세로 이동 -> still_s초 정지."""
    sim = sp.Sim(FallCoreEngine(cfg), **kw)
    sim.hold(sp.standing(), 3)
    t_start = sim.t
    sim.move(sp.standing(), target, fall_s)
    sim.hold(target, still_s)
    return sim, t_start


def test_10_fast_descent_is_fall_event(cfg):
    sim, _ = _fall(cfg, sp.side_lying(), 3)
    assert len(sim.event_times("FALL_EVENT")) == 1
    assert sim.last().mode.name == "POST_FALL"
    assert sim.last().fall_event_t_s == pytest.approx(sim.event_times("FALL_EVENT")[0])


def test_11_slow_controlled_descent_is_not_fall_and_no_emergency(cfg):
    sim, _ = _fall(cfg, sp.side_lying(), 35, fall_s=4.0)        # 4초에 걸쳐 천천히 눕기
    assert sim.event_times("FALL_EVENT") == []
    assert sim.alerts() <= {"NONE"}                              # 이후 35초 정지해도 경보 없음
    assert sim.last().mode.name == "NORMAL"


def test_12_post_fall_side_lying_30s_is_emergency(cfg):
    sim, _ = _fall(cfg, sp.side_lying(), 40)
    t_fall = sim.event_times("FALL_EVENT")[0]
    emerg = sim.event_times("EMERGENCY_POST_FALL_IMMOBILE")
    assert len(emerg) == 1 and 27.0 <= emerg[0] - t_fall <= 36.0   # 낙상 후 약 30초
    assert sim.last().alert.name == "EMERGENCY_POST_FALL_IMMOBILE"


@pytest.mark.parametrize("name,target", [("sitting", sp.sitting_floor()), ("curled", sp.curled())])
def test_13_emergency_regardless_of_posture(cfg, name, target):
    sim, _ = _fall(cfg, target, 40)
    t_fall = sim.event_times("FALL_EVENT")
    assert len(t_fall) == 1, f"{name}: 낙상 사건이 발생해야 함"
    emerg = sim.event_times("EMERGENCY_POST_FALL_IMMOBILE")
    assert len(emerg) == 1 and 27.0 <= emerg[0] - t_fall[0] <= 36.0


def test_14_wrist_movement_after_fall_is_post_fall_moving_no_emergency(cfg):
    sim, _ = _fall(cfg, sp.side_lying(), 20)
    lying = sp.side_lying()
    moved = sp.shift(lying, (9, 10), 60, -40)                    # 낙상 20초 후 손목만 움직임
    sim.move(lying, moved, 1.0)
    sim.hold(moved, 22)
    assert "POST_FALL_MOVING" in sim.alerts()
    assert "EMERGENCY_POST_FALL_IMMOBILE" not in sim.alerts()
    assert sim.last().immobile_elapsed_s < 25.0                  # 타이머가 초기화됨 (움직임 직후부터 다시 셈)


def test_15_recovery_clears_emergency(cfg):
    sim, _ = _fall(cfg, sp.side_lying(), 33)
    assert "EMERGENCY_POST_FALL_IMMOBILE" in sim.alerts()
    sim.move(sp.side_lying(), sp.standing(), 2.0)                # 스스로 일어남
    sim.hold(sp.standing(), 5)                                   # STANDING 3초 이상 유지
    assert len(sim.event_times("RECOVERED")) == 1
    assert sim.last().mode.name == "RECOVERED"
    assert sim.last().alert.name == "NONE"


def test_16a_track_lost_5s_same_id_keeps_post_fall(cfg):
    sim, _ = _fall(cfg, sp.side_lying(), 8)
    assert sim.last().mode.name == "POST_FALL"
    sim.gap(5)                                                   # 화면에서 5초 사라짐
    sim.hold(sp.side_lying(), 3)
    assert sim.last().mode.name == "POST_FALL"
    assert sim.event_times("RECOVERED") == []


def test_16b_track_lost_5s_new_id_is_readopted(cfg):
    sim, _ = _fall(cfg, sp.side_lying(), 8)
    sim.gap(5)
    sim.track_id = 2                                             # 추적기가 새 번호를 줌
    sim.hold(sp.side_lying(), 3)
    assert "TRACK_READOPTED" in [e for _, r in sim.log for e in r.events]
    assert sim.last().mode.name == "POST_FALL"


def test_16c_lost_longer_than_hold_drops_state(cfg):
    sim, _ = _fall(cfg, sp.side_lying(), 8)
    sim.gap(cfg["alerts"]["track_lost_hold_s"] + 2)              # 유지 시간(10초)을 넘김
    sim.hold(sp.side_lying(), 3)
    assert sim.last().mode.name == "NORMAL"                      # 상태가 사라지고 새 track으로 시작
