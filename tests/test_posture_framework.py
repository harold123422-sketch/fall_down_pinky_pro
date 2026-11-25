"""세부 자세 분류(프레임워크 A~E)와 자세별 위험 판단, 낙상 후 회복 경로."""
import numpy as np
import pytest

import synthetic_poses as sp
from fall_core import FallCoreEngine
from fall_core.posture_framework import classify_framework, transition_name

FLOOR, L = 650.0, 150.0
MIRROR = [0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15]      # 좌우 관절 번호 맞바꿈


# ---------------------------------------------------------------- 분류기 (한 프레임)
@pytest.mark.parametrize("want", list(sp.ALL_POSTURES))
def test_each_posture_is_classified(cfg, want):
    r = classify_framework(sp.ALL_POSTURES[want](), FLOOR, L, cfg)
    assert r.name == want, r.reason


@pytest.mark.parametrize("want", list(sp.ALL_POSTURES))
def test_posture_survives_keypoint_jitter(cfg, want):
    """관절점이 ±4.5px(몸통 길이의 3%) 흔들려도 95% 이상 같은 자세."""
    rng = np.random.default_rng(7)
    base = sp.ALL_POSTURES[want]()
    hits = sum(classify_framework(sp.jitter(base, rng, 4.5), FLOOR, L, cfg).name == want for _ in range(100))
    assert hits >= 95, f"{want}: {hits}/100"


@pytest.mark.parametrize("want", list(sp.ALL_POSTURES))
def test_posture_survives_trunk_length_error_and_mirror(cfg, want):
    base = sp.ALL_POSTURES[want]()
    for l_ref in (135.0, 165.0):                                         # 몸통 길이 추정 ±10%
        assert classify_framework(base, FLOOR, l_ref, cfg).name == want
    mir = base.copy()
    mir[:, 0] = 600 - mir[:, 0]
    mir = mir[MIRROR]
    expect = {"KNEEL_HALF_L": "KNEEL_HALF_R", "LYING_SIDE_R": "LYING_SIDE_L"}.get(want, want)
    assert classify_framework(mir, FLOOR, L, cfg).name == expect        # 좌우가 바뀌면 왼·오른쪽 이름도 바뀜


def test_missing_shoulders_or_floor_is_unknown(cfg):
    k = sp.standing()
    k[5, 2] = k[6, 2] = 0.1
    assert classify_framework(k, FLOOR, L, cfg).name == "UNKNOWN"
    assert classify_framework(sp.standing(), None, L, cfg).name == "UNKNOWN"


def test_transition_names():
    assert transition_name("STAND_UPRIGHT", "SIT_CHAIR_UPRIGHT") == "STAND_TO_SIT"
    assert transition_name("SIT_CHAIR_UPRIGHT", "STAND_UPRIGHT") == "SIT_TO_STAND"
    assert transition_name("FORWARD_FLEXION", "LYING_SIDE_R") == "CONTROLLED_DESCENT"
    assert transition_name("LYING_SIDE_R", "SIDE_LYING_ON_ELBOW") == "SIDE_TO_SIT"
    assert transition_name("LYING_SIDE_R", "LYING_FLAT") == "ROLL"
    assert transition_name("LYING_FLAT", "QUADRUPED") == "LIE_TO_QUADRUPED"
    assert transition_name("QUADRUPED", "KNEEL_HALF_L") == "QUADRUPED_TO_KNEEL"
    assert transition_name("KNEEL_HALF_L", "STAND_UPRIGHT") == "KNEEL_TO_STAND"
    assert transition_name("STAND_UPRIGHT", "STAND_UPRIGHT") is None


# ---------------------------------------------------------------- 엔진: 평상시 자세별 위험
def _hold_after_standing(cfg, pose, secs, still=True):
    sim = sp.Sim(FallCoreEngine(cfg), jitter_px=1.0 if still else 0.0)
    sim.hold(sp.standing(), 3)
    sim.move(sp.standing(), pose, 3.0)              # 천천히 (낙상 아님)
    sim.hold(pose, secs)
    return sim


@pytest.mark.parametrize("pose,cls,after", [
    (sp.side_lying(), "LYING_SIDE_R", 5.0),          # 바닥에 누움: 보지 못한 낙상 가능
    (sp.lying_fetal(), "LYING_FETAL", 3.0),          # 태아 자세: 통증·위험 신호 후보
    (sp.quadruped(), "QUADRUPED", 3.0),              # 사지 착지
    (sp.chair_slumped(), "SIT_CHAIR_SLUMPED", 10.0),  # 체간 처짐: 의식저하 의심 후보
])
def test_caution_postures_without_fall(cfg, pose, cls, after):
    sim = _hold_after_standing(cfg, pose, after + 4)
    assert sim.event_times("FALL_EVENT") == []
    assert sim.last().posture_class == cls
    times = [t for t, r in sim.log if f"POSTURE_CAUTION:{cls}" in r.events]
    assert len(times) == 1
    assert sim.last().alert.name in ("POSTURE_CAUTION", "CHECK_POSTURE_IMMOBILE")


def test_chair_sitting_still_is_safe(cfg):
    sim = _hold_after_standing(cfg, sp.chair_upright(), 40)
    assert sim.last().posture_class == "SIT_CHAIR_UPRIGHT"
    assert {r.alert.name for t, r in sim.log if t > 8} == {"NONE"}     # 의자에 40초 가만히 앉아도 정상


def test_floor_sitting_still_30s_is_check(cfg):
    sim = _hold_after_standing(cfg, sp.sit_floor_long(), 36)
    assert sim.last().posture_class == "SIT_FLOOR_LONG"
    assert sim.last().alert.name == "CHECK_POSTURE_IMMOBILE"


def test_walking_is_recognized(cfg):
    eng = FallCoreEngine(cfg)
    r = None
    for i in range(60):                               # 4초 동안 오른쪽으로 0.5 몸통길이/초
        t = i / 15
        k = sp.standing(cx=200 + 75 * t)
        r = eng.update(t, [{"track_id": 1, "kpts": k, "box_conf": 0.9}])[0]
    assert r.posture_class == "WALKING" and r.pelvis_speed > 0.3


def test_person_first_seen_lying_uses_estimated_floor(cfg):
    sim = sp.Sim(FallCoreEngine(cfg))
    sim.hold(sp.side_lying(), 8)                      # 서 있는 모습을 본 적이 없음
    r = sim.last()
    assert r.floor_source == "estimated"
    assert r.posture_class == "LYING_SIDE_R"
    assert r.alert.name == "POSTURE_CAUTION"          # 처음부터 바닥에 누운 사람도 주의


# ---------------------------------------------------------------- 엔진: 낙상 후 회복 경로
def test_recovery_path_progresses_and_recovers(cfg):
    sim = sp.Sim(FallCoreEngine(cfg))
    sim.hold(sp.standing(), 3)
    path = [sp.side_lying(), sp.side_lying_on_elbow(), sp.sit_floor_side(), sp.quadruped(),
            sp.kneel_half_left(), sp.standing()]
    sim.move(sp.standing(), path[0], 0.6)             # 낙상
    sim.hold(path[0], 5)
    for a, b in zip(path, path[1:]):
        sim.move(a, b, 1.5)
        sim.hold(b, 4)
    events = [e for _, r in sim.log for e in r.events]
    assert events.count("FALL_EVENT") == 1
    stages = [r.recovery_stage for _, r in sim.log if r.recovery_stage is not None]
    for s in (1, 2, 3, 4, 5):                         # 눕기 -> 팔꿈치 -> 바닥 앉기 -> 네발 -> 무릎
        assert s in stages
    assert "SELF_RECOVERABLE" in {r.alert.name for _, r in sim.log}
    assert "RECOVERED" in events and "TRANSITION:RECOVERY_PATH" in events
    assert "TRANSITION:SIDE_TO_SIT" in events and "TRANSITION:KNEEL_TO_STAND" in events
    assert sim.last().alert.name == "NONE" and sim.last().mode.name == "RECOVERED"


def test_landing_in_floor_sitting_is_not_self_recovering(cfg):
    """넘어져서 바로 바닥에 앉은 것은 '회복 중'이 아님: 처음 자리 잡은 자세보다 단계가 올라가야 함."""
    sim = sp.Sim(FallCoreEngine(cfg))
    sim.hold(sp.standing(), 3)
    sim.move(sp.standing(), sp.sitting_floor(), 0.6)
    sim.hold(sp.sitting_floor(), 10)
    assert sim.event_times("FALL_EVENT")
    assert "SELF_RECOVERABLE" not in {r.alert.name for _, r in sim.log}
    assert sim.last().alert.name in ("FALL_EVENT", "POST_FALL_MOVING")


def test_no_self_recovering_flash_right_after_fall(cfg):
    """낙상 직후 깜빡임 방지 시간 동안 '서 있던 자세'를 회복 단계로 읽으면 안 됨."""
    sim = sp.Sim(FallCoreEngine(cfg))
    sim.hold(sp.standing(), 3)
    sim.move(sp.standing(), sp.side_lying(), 0.6)
    sim.hold(sp.side_lying(), 3)
    t_fall = sim.event_times("FALL_EVENT")[0]
    after = [r.alert.name for t, r in sim.log if t >= t_fall]
    assert "SELF_RECOVERABLE" not in after and after[0] == "FALL_EVENT"


# ---------------------------------------------------------------- 화면 그리기: 모든 경보에서 죽지 않는지
def test_overlay_draws_every_alert(cfg):
    from fall_core.states import Alert
    from fall_core.viz import ALERT_COLOR, draw_tracks
    assert set(ALERT_COLOR) == set(Alert)                 # 새 경보를 추가하면 색도 반드시 추가
    sim = sp.Sim(FallCoreEngine(cfg))
    sim.hold(sp.standing(), 2)
    r = sim.last()
    img = np.zeros((480, 640, 3), np.uint8)
    for a in Alert:
        r.alert = a
        draw_tracks(img, [{"kpts": sp.standing(), "box": (200, 100, 400, 460)}], [r], 0.5, footer="x")


def test_caution_continues_between_caution_postures(cfg):
    """바닥에 누움(주의) -> 태아 자세(주의)로 바뀌어도 중간에 '안정'으로 떨어지지 않음."""
    sim = _hold_after_standing(cfg, sp.side_lying(), 8)
    assert sim.last().alert.name in ("POSTURE_CAUTION", "CHECK_POSTURE_IMMOBILE")
    n = len(sim.log)
    sim.move(sp.side_lying(), sp.lying_fetal(), 1.0)
    sim.hold(sp.lying_fetal(), 5)
    after = [r.alert.name for _, r in sim.log[n:]]
    assert "NONE" not in after
    assert sim.last().posture_class == "LYING_FETAL"
    assert "TRANSITION:ROLL" not in [e for _, r in sim.log[n:] for e in r.events]   # 태아 자세는 돌아눕기가 아님


def _walk_in_place(cfg, seconds=4.0, step_hz=1.0, stride_px=50.0, fps=15.0):
    """골반은 화면에 고정(카메라가 따라감), 양 발목·무릎만 번갈아 앞뒤로 움직이는 측면 보행."""
    import math
    eng, r = FallCoreEngine(cfg), None
    for i in range(int(seconds * fps)):
        t = i / fps
        ph = math.sin(2 * math.pi * step_hz * t)
        k = sp.standing()
        k[15, 0], k[16, 0] = 300 + stride_px * ph, 300 - stride_px * ph       # 발목이 엇갈림
        k[13, 0], k[14, 0] = 300 + stride_px / 2 * ph, 300 - stride_px / 2 * ph
        r = eng.update(t, [{"track_id": 1, "kpts": k, "box_conf": 0.9}])[0]
    return r


def test_walking_recognized_when_camera_follows_person(cfg):
    r = _walk_in_place(cfg)
    assert r.posture_class == "WALKING", r.posture_reason
    assert r.pelvis_speed < 0.05                          # 골반은 거의 안 움직였는데도 보행으로 인식
    assert "엇갈림" in r.posture_reason


def test_standing_still_is_not_walking(cfg):
    sim = sp.Sim(FallCoreEngine(cfg), jitter_px=2.0)
    sim.hold(sp.standing(), 6)
    assert sim.last().posture_class == "STAND_UPRIGHT"
    assert "WALKING" not in {r.posture_class for _, r in sim.log}


def test_walking_toward_camera_is_recognized(cfg):
    """카메라 쪽으로 걸어오면 양 발목이 위아래(화면 y)로 번갈아 엇갈림."""
    import math
    eng, r = FallCoreEngine(cfg), None
    for i in range(60):
        t = i / 15
        ph = math.sin(2 * math.pi * 1.0 * t)
        k = sp.standing()
        k[15, 1], k[16, 1] = 650 + 30 * ph, 650 - 30 * ph
        r = eng.update(t, [{"track_id": 1, "kpts": k, "box_conf": 0.9}])[0]
    assert r.posture_class == "WALKING", r.posture_reason
