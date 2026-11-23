import math

from fall_core.geometry import joint_angle_deg, normalize, trunk_length, trunk_tilt_deg


def test_joint_angle_straight_is_180():
    assert math.isclose(joint_angle_deg((0, 0), (0, 1), (0, 2)), 180.0, abs_tol=1e-6)


def test_joint_angle_right_angle_is_90():
    assert math.isclose(joint_angle_deg((1, 0), (0, 0), (0, 1)), 90.0, abs_tol=1e-6)


def test_joint_angle_zero_length_is_nan():
    assert math.isnan(joint_angle_deg((0, 0), (0, 0), (1, 1)))


def test_trunk_tilt_upright_horizontal_diagonal():
    assert math.isclose(trunk_tilt_deg((300, 200), (300, 350)), 0.0, abs_tol=1e-6)
    assert math.isclose(trunk_tilt_deg((100, 640), (250, 640)), 90.0, abs_tol=1e-6)
    assert math.isclose(trunk_tilt_deg((350, 200), (300, 250)), 45.0, abs_tol=1e-6)


def test_trunk_tilt_ignores_up_down_direction():
    assert math.isclose(trunk_tilt_deg((300, 350), (300, 200)), 0.0, abs_tol=1e-6)


def test_trunk_length_and_normalize():
    assert math.isclose(trunk_length((300, 200), (300, 350)), 150.0)
    assert math.isclose(normalize(30.0, 150.0), 0.2)
    assert math.isnan(normalize(30.0, 0.0))
