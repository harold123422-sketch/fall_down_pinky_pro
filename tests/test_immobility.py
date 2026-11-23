"""지시서 6절 테스트 6~9: 기립 무움직임 -> 확인 요청(CHECK), 긴급(EMERGENCY)은 아님."""
import synthetic_poses as sp
from fall_core import FallCoreEngine


def _sim(cfg, **kw):
    return sp.Sim(FallCoreEngine(cfg), **kw)


def test_06_standing_still_30s_gives_check_not_emergency(cfg):
    sim = _sim(cfg, jitter_px=1.0)                    # +-1px 잡음
    sim.hold(sp.standing(), 35)
    check = sim.event_times("CHECK_STANDING_IMMOBILE")
    assert len(check) == 1 and 27.0 <= check[0] <= 33.0          # 약 30초 시점
    assert "EMERGENCY_POST_FALL_IMMOBILE" not in sim.alerts()
    assert sim.last().alert.name == "CHECK_STANDING_IMMOBILE"


def test_07_wrist_moves_after_29s_resets_timer_no_alert(cfg):
    sim = _sim(cfg, jitter_px=1.0)
    sim.hold(sp.standing(), 29)
    moved = sp.shift(sp.standing(), (9, 10), 60)     # 양 손목 60px(0.4 L_trunk) 이동
    sim.move(sp.standing(), moved, 1.0)
    sim.hold(moved, 5)
    assert sim.alerts() == {"NONE"}                  # 경보 없음
    assert sim.event_times("CHECK_STANDING_IMMOBILE") == []
    assert sim.last().immobile_elapsed_s < 6.0       # 타이머가 초기화되어 다시 세는 중


def test_08_postural_sway_noise_is_not_movement(cfg):
    """+-2% L_trunk(=3px) 수준의 sway는 움직임이 아니므로 CHECK가 발생해야 한다."""
    sim = _sim(cfg, jitter_px=0.02 * sp.L)
    sim.hold(sp.standing(), 35)
    check = sim.event_times("CHECK_STANDING_IMMOBILE")
    assert len(check) == 1 and 27.0 <= check[0] <= 33.0


def test_09_irregular_fps_gives_same_result_as_test_06(cfg):
    sim = _sim(cfg, jitter_px=1.0, irregular=True, seed=3)     # 프레임 간격 1/15~1/5초
    sim.hold(sp.standing(), 35)
    check = sim.event_times("CHECK_STANDING_IMMOBILE")
    assert len(check) == 1 and 27.0 <= check[0] <= 34.0
    assert "EMERGENCY_POST_FALL_IMMOBILE" not in sim.alerts()
