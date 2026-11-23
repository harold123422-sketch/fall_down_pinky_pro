"""COCO 17 keypoints 인덱스, 신뢰도 게이팅, 결측 처리.

COCO에는 patella, calcaneus, metatarsal head, palm, toe가 없다. 그래서 근사를 쓴다:
  - hip(11,12)   ~ hip joint center (ASIS/PSIS 아님)
  - knee(13,14)  ~ tibiofemoral joint 중심. patella 근사로 사용
  - ankle(15,16) ~ talocrural joint(malleoli 부근). calcaneus 근사로 사용
  - wrist(9,10)  ~ radiocarpal joint. palm 근사
이 근사 때문에 발바닥 지지면, 손바닥 체중지지 등은 정확히 판단할 수 없다.
"""
import numpy as np

NOSE = 0
L_SHOULDER, R_SHOULDER = 5, 6
L_ELBOW, R_ELBOW = 7, 8
L_WRIST, R_WRIST = 9, 10
L_HIP, R_HIP = 11, 12
L_KNEE, R_KNEE = 13, 14
L_ANKLE, R_ANKLE = 15, 16

# STANDING 판정에 필요한 관절 (하나라도 신뢰도가 낮으면 UNKNOWN)
STANDING_REQUIRED = (L_SHOULDER, R_SHOULDER, L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE)


def as_kpts(a):
    """(17, 3) float 배열 [x, y, confidence] 로 맞춘다."""
    return np.asarray(a, dtype=float).reshape(17, 3)


def is_valid(k, idx, conf_min):
    return bool(k[idx, 2] >= conf_min)


def all_valid(k, idxs, conf_min):
    return all(k[i, 2] >= conf_min for i in idxs)


def midpoint(k, a, b, conf_min):
    """관절 a, b의 중점. 둘 중 하나라도 신뢰도가 낮으면 None."""
    if k[a, 2] < conf_min or k[b, 2] < conf_min:
        return None
    return (k[a, :2] + k[b, :2]) / 2.0
