"""낙상 판정 규칙. ROS를 전혀 쓰지 않는 순수 파이썬 모듈.

ROS 없이도 import해서 시험할 수 있게 일부러 분리했다.
입력은 YOLO-pose가 준 COCO 17개 관절 [x, y, 신뢰도] 배열이다.
"""
import math
from collections import deque

import numpy as np

# COCO 17 관절 번호 (YOLO-pose 출력 순서)
L_SHOULDER, R_SHOULDER = 5, 6
L_HIP, R_HIP = 11, 12

# 상태 이름. 노드가 이 문자열을 그대로 발행한다.
NORMAL = "NORMAL"
SUSPECT = "SUSPECT"        # 누워 있음 (확인 필요)
FALL = "FALL"              # 급하강 + 누움
NEEDS_HELP = "NEEDS_HELP"  # 넘어진 뒤 정지


def midpoint(kpts, a, b, min_conf):
    """관절 a, b의 중점. 둘 중 하나라도 신뢰도가 낮으면 None."""
    if kpts[a, 2] < min_conf or kpts[b, 2] < min_conf:
        return None
    return (kpts[a, :2] + kpts[b, :2]) / 2


def torso_features(kpts, min_conf=0.4):
    """몸통 정보를 계산한다.

    반환: (angle_deg, torso_len, hip_y)
      angle_deg : 몸통이 수직에서 벌어진 각도. 0 = 서 있음, 90 = 가로로 누움
      torso_len : 어깨 중점~골반 중점 거리(px). 속도를 '몸통 길이' 단위로 바꿀 때 쓴다
      hip_y     : 골반 중점의 화면 세로 좌표(px). 클수록 화면 아래쪽
    관절이 안 보이면 None.
    """
    shoulder = midpoint(kpts, L_SHOULDER, R_SHOULDER, min_conf)
    hip = midpoint(kpts, L_HIP, R_HIP, min_conf)
    if shoulder is None or hip is None:
        return None
    dx, dy = shoulder[0] - hip[0], shoulder[1] - hip[1]
    torso_len = math.hypot(dx, dy)
    if torso_len < 1e-6:
        return None
    # 골반→어깨 벡터와 '위쪽 수직선'이 이루는 각도.
    # 화면은 y가 아래로 커지므로 어깨가 위에 있으면 dy < 0 이다.
    # 서 있음: 0도 / 옆으로 누움: 90도 / 거꾸로: 180도
    angle = math.degrees(math.atan2(abs(dx), -dy))
    return angle, torso_len, float(hip[1])


class FallJudge:
    """프레임이 들어올 때마다 상태를 갱신하는 판정기.

    history에 (시각, 몸통 각도, 정규화된 골반 높이)를 쌓아서 '시간에 따른 변화'를 본다.
    """

    def __init__(self, lying_angle=60.0, window_sec=1.5):
        self.lying_angle = lying_angle   # 이 각도를 넘으면 '누움'으로 본다
        self.window_sec = window_sec     # 최근 몇 초를 볼지
        self.history = deque()           # (t, angle, hip_y, torso_len)
        self.state = NORMAL

    def update(self, t, kpts):
        """한 프레임을 넣고 현재 상태 문자열을 돌려준다."""
        feat = torso_features(kpts)
        if feat is None:
            return self.state            # 관절이 안 보이면 이전 상태 유지
        angle, torso_len, hip_y = feat
        self.history.append((t, angle, hip_y, torso_len))
        while self.history and t - self.history[0][0] > self.window_sec:
            self.history.popleft()
        self.state = self.decide(angle)
        return self.state

    # ------------------------------------------------------------------
    # TODO (직접 채워 보기): 여기가 이 프로젝트의 '기준'이 들어가는 곳이다.
    #
    # 지금은 '누웠는가'만 보고 SUSPECT를 낸다. FALL과 NEEDS_HELP를 직접 만들어 보자.
    #
    # 쓸 수 있는 재료:
    #   self.history : 최근 window_sec초의 (t, angle, hip_y, torso_len) 목록
    #   angle        : 지금 몸통 각도 (0=서있음, 90=누움)
    #
    # 생각해 볼 순서:
    #   1) history에서 '골반이 내려간 속도'를 구한다.
    #      속도 = (마지막 hip_y - 처음 hip_y) / 시간 / torso_len   (단위: 몸통길이/초)
    #   2) 속도가 임계값(처음엔 2.0 정도로 시도)을 넘고, 지금 누워 있으면 FALL
    #   3) 누워 있지만 속도가 느리면 SUSPECT (천천히 눕기, 원래 누워 있던 사람)
    #   4) FALL 뒤 N초 동안 안 움직이면 NEEDS_HELP  (이건 self에 변수를 하나 더 둬야 한다)
    #
    # 임계값은 정답이 없다. 영상 몇 개를 찍어서 값을 바꿔 가며 정하는 게 이 단계의 공부다.
    # ------------------------------------------------------------------
    def decide(self, angle):
        if angle >= self.lying_angle:
            return SUSPECT
        return NORMAL
