"""지시서 6절 테스트 1~5: STANDING / NOT_STANDING / UNKNOWN."""
import synthetic_poses as sp
from fall_core.posture import classify_posture
from fall_core.states import Posture


def test_01_normal_standing_is_standing(cfg):
    r = classify_posture(sp.standing(), cfg)
    assert r.posture == Posture.STANDING
    assert all(r.conditions.values())          # S1~S6 전부 통과


def test_02_knee_flexion_40_is_not_standing(cfg):
    r = classify_posture(sp.knee_flexion(40), cfg)
    assert r.posture == Posture.NOT_STANDING
    assert not r.conditions["S1"]              # knee extension 실패
    assert r.features["knee_angle_L"] < 150    # 내각 약 140도


def test_03_trunk_flexion_45_is_not_standing(cfg):
    r = classify_posture(sp.trunk_flexion(45), cfg)
    assert r.posture == Posture.NOT_STANDING
    assert not r.conditions["S5"]              # trunk 직립 실패
    assert abs(r.features["trunk_tilt_deg"] - 45) < 1.0


def test_04_side_lying_is_not_standing(cfg):
    r = classify_posture(sp.side_lying(), cfg)
    assert r.posture == Posture.NOT_STANDING
    assert not r.conditions["S4"]              # cranial -> caudal 순서 실패
    assert r.features["trunk_tilt_deg"] > 80


def test_05_low_confidence_ankle_is_unknown(cfg):
    r = classify_posture(sp.with_conf(sp.standing(), 15, 0.2), cfg)
    assert r.posture == Posture.UNKNOWN        # STANDING도 NOT_STANDING도 아님


def test_thresholds_come_from_yaml_not_code(cfg):
    """임계값을 바꾸면 판정이 바뀐다 (하드코딩이 아님을 확인)."""
    # 무릎 15도 굽힘 = 내각 165도: 기준 160도에서는 STANDING, 170도로 올리면 NOT_STANDING
    assert classify_posture(sp.knee_flexion(15), cfg).posture == Posture.STANDING
    cfg["standing"]["knee_extension_min_deg"] = 170
    assert classify_posture(sp.knee_flexion(15), cfg).posture == Posture.NOT_STANDING
