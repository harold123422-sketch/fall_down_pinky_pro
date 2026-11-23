"""관절 내각, 체간 경사각, 정규화 함수. 이미지 좌표계(y는 아래로 증가)."""
import math

import numpy as np


def joint_angle_deg(a, b, c):
    """점 b에서 a-b-c가 이루는 내각 (0~180도). 180 = 일직선(완전 신전).

    길이가 0인 벡터가 있으면 nan.
    """
    a, b, c = (np.asarray(p, dtype=float) for p in (a, b, c))
    v1, v2 = a - b, c - b
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-9 or n2 < 1e-9:
        return float("nan")
    cos = float(np.dot(v1, v2) / (n1 * n2))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def trunk_length(shoulder_mid, pelvis_mid):
    """shoulder midpoint - pelvis midpoint 거리(px). 모든 길이·변위의 정규화 기준 (L_trunk)."""
    return float(np.linalg.norm(np.asarray(shoulder_mid, float) - np.asarray(pelvis_mid, float)))


def trunk_tilt_deg(shoulder_mid, pelvis_mid):
    """체간선이 '수직선'과 이루는 경사각 (0~90도). 0 = 직립, 90 = 수평.

    선의 방향만 보므로 앞뒤(위아래) 방향은 구분하지 않는다.
    """
    dx = float(shoulder_mid[0] - pelvis_mid[0])
    dy = float(shoulder_mid[1] - pelvis_mid[1])
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return float("nan")
    return math.degrees(math.atan2(abs(dx), abs(dy)))


def normalize(value, length):
    """길이/변위를 기준 길이로 나눈다. 기준이 0 이하이면 nan."""
    if length is None or length <= 1e-9:
        return float("nan")
    return value / length
