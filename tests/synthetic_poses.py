"""가짜 17점 자세 생성기와 시간 시뮬레이터. 픽셀 좌표, 몸통 길이 L = 150px.

이미지 좌표계: x는 오른쪽, y는 아래로 증가. 바닥(floor)은 y = 650.
"""
import math

import numpy as np

L = 150.0
FLOOR_Y = 650.0


def _pose(pts, conf=0.9):
    k = np.zeros((17, 3))
    for i, (x, y) in pts.items():
        k[i] = [x, y, conf]
    return k


def standing(cx=300.0):
    return _pose({
        0: (cx, 140), 1: (cx - 8, 132), 2: (cx + 8, 132), 3: (cx - 18, 138), 4: (cx + 18, 138),
        5: (cx - 40, 200), 6: (cx + 40, 200), 7: (cx - 55, 265), 8: (cx + 55, 265),
        9: (cx - 60, 330), 10: (cx + 60, 330),
        11: (cx - 25, 350), 12: (cx + 25, 350), 13: (cx - 25, 500), 14: (cx + 25, 500),
        15: (cx - 25, 650), 16: (cx + 25, 650)})


def knee_flexion(deg, cx=300.0):
    """무릎을 deg만큼 굽힘 (측면 시점). 허벅지는 앞으로 deg/2, 정강이는 뒤로 deg/2 기울어짐."""
    k = standing(cx)
    h = math.radians(deg / 2)
    s, c = math.sin(h), math.cos(h)
    for hip, kne, ank in ((11, 13, 15), (12, 14, 16)):
        hx, hy = k[hip, :2]
        kx, ky = hx + L * s, hy + L * c
        k[kne, :2] = (kx, ky)
        k[ank, :2] = (kx - L * s, ky + L * c)
    return k


def trunk_flexion(deg, cx=300.0):
    """체간을 앞으로 deg만큼 숙임. 골반은 그대로, 어깨·머리·팔이 따라 이동."""
    k = standing(cx)
    phi = math.radians(deg)
    new_mid = np.array([cx + L * math.sin(phi), 350 - L * math.cos(phi)])
    delta = new_mid - np.array([cx, 200.0])
    for i in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10):
        k[i, :2] += delta
    return k


def side_lying():
    """몸이 수평으로 바닥에 누움 (옆으로 누운 자세)."""
    return _pose({
        0: (60, 640), 1: (65, 632), 2: (65, 648), 3: (75, 636), 4: (75, 644),
        5: (100, 625), 6: (100, 655), 7: (150, 660), 8: (150, 620), 9: (200, 665), 10: (200, 615),
        11: (250, 630), 12: (250, 650), 13: (400, 635), 14: (400, 645), 15: (550, 640), 16: (550, 640)})


def sitting_floor(cx=300.0):
    """바닥에 주저앉은 자세 (몸통은 세워져 있고 골반이 바닥 근처)."""
    return _pose({
        0: (cx, 410), 1: (cx - 8, 402), 2: (cx + 8, 402), 3: (cx - 18, 408), 4: (cx + 18, 408),
        5: (cx - 40, 470), 6: (cx + 40, 470), 7: (cx - 30, 540), 8: (cx + 30, 540),
        9: (cx + 60, 590), 10: (cx + 90, 590),
        11: (cx - 25, 620), 12: (cx + 25, 620), 13: (cx + 120, 560), 14: (cx + 120, 575),
        15: (cx + 170, 650), 16: (cx + 170, 650)})


def curled(cx=300.0):
    """웅크린 자세."""
    return _pose({
        0: (cx, 520), 1: (cx - 8, 512), 2: (cx + 8, 512), 3: (cx - 18, 518), 4: (cx + 18, 518),
        5: (cx - 40, 560), 6: (cx + 40, 560), 7: (cx - 50, 600), 8: (cx + 50, 600),
        9: (cx - 30, 590), 10: (cx + 30, 590),
        11: (cx - 25, 620), 12: (cx + 25, 620), 13: (cx - 25, 565), 14: (cx + 25, 565),
        15: (cx - 25, 650), 16: (cx + 25, 650)})


def blend(a, b, alpha):
    out = a.copy()
    out[:, :2] = a[:, :2] + (b[:, :2] - a[:, :2]) * alpha
    out[:, 2] = np.minimum(a[:, 2], b[:, 2])
    return out


def with_conf(k, idx, conf):
    out = k.copy()
    out[idx, 2] = conf
    return out


def shift(k, idxs, dx, dy=0.0):
    out = k.copy()
    for i in idxs:
        out[i, :2] += (dx, dy)
    return out


def jitter(k, rng, radius_px):
    """모든 점에 반경 radius_px 원판 안의 균일 잡음 (x, y 모두)."""
    if radius_px <= 0:
        return k
    out = k.copy()
    r = radius_px * np.sqrt(rng.uniform(0, 1, 17))
    th = rng.uniform(0, 2 * np.pi, 17)
    out[:, 0] += r * np.cos(th)
    out[:, 1] += r * np.sin(th)
    return out


class Sim:
    """엔진에 프레임을 시간 순서로 넣고 결과를 모은다."""

    def __init__(self, engine, fps=15.0, irregular=False, seed=0, track_id=1, jitter_px=1.0):
        self.engine = engine
        self.dt = 1.0 / fps
        self.irregular = irregular          # True면 프레임 간격이 1/15~1/5초로 불규칙
        self.rng = np.random.default_rng(seed)
        self.track_id = track_id
        self.jitter_px = jitter_px
        self.t = 0.0
        self.log = []                       # (t, TrackResult)
        self.dets = []                      # 같은 순서의 검출 입력 (메시지 재생성용)

    def _tick(self):
        self.t += self.rng.uniform(1 / 15, 1 / 5) if self.irregular else self.dt
        return self.t

    def _feed(self, pose):
        det = {"track_id": self.track_id, "kpts": jitter(pose, self.rng, self.jitter_px), "box_conf": 0.9}
        res = self.engine.update(self.t, [det])
        for r in res:
            self.log.append((self.t, r))
            self.dets.append(det)
        return res

    def hold(self, pose, seconds):
        end = self.t + seconds
        while self.t < end:
            self._tick()
            self._feed(pose)

    def move(self, a, b, seconds):
        start = self.t
        while self.t < start + seconds:
            self._tick()
            alpha = min(1.0, (self.t - start) / seconds)
            self._feed(blend(a, b, alpha))

    def gap(self, seconds):
        """사람이 화면에서 사라진 구간 (검출 없음)."""
        end = self.t + seconds
        while self.t < end:
            self._tick()
            self.engine.update(self.t, [])

    # ---- 조회
    def event_times(self, name):
        return [t for t, r in self.log if name in r.events]

    def alerts(self):
        return {r.alert.name for _, r in self.log}

    def last(self):
        return self.log[-1][1]


# ----------------------------------------------------------------------------------------------
# 세부 자세 (프레임워크 A~E). 바닥 y = 650, 몸통 길이 L = 150px. 측면(sagittal) 또는 정면 시점.
# ----------------------------------------------------------------------------------------------
def _full(pts, conf=0.9):
    """눈·귀는 코 주변에 자동으로 채운다."""
    nx, ny = pts[0]
    pts = dict(pts)
    pts.setdefault(1, (nx - 6, ny - 6))
    pts.setdefault(2, (nx + 6, ny - 6))
    pts.setdefault(3, (nx - 14, ny - 2))
    pts.setdefault(4, (nx + 14, ny - 2))
    return _pose(pts, conf)


def stand_one_leg(cx=300.0):
    k = standing(cx)
    k[14, :2] = (cx + 45, 470)        # 오른 무릎 들어 올림
    k[16, :2] = (cx + 40, 540)        # 오른 발목 바닥에서 뜸 (높이 0.73 L)
    return k


def squat_partial():
    return _full({0: (330, 290), 5: (305, 340), 6: (315, 342), 7: (355, 380), 8: (365, 382),
                  9: (400, 420), 10: (410, 422), 11: (235, 470), 12: (240, 472),
                  13: (380, 500), 14: (385, 502), 15: (380, 650), 16: (385, 650)})


def squat_deep():
    return _full({0: (410, 420), 5: (396, 460), 6: (400, 462), 7: (410, 520), 8: (415, 522),
                  9: (420, 560), 10: (425, 562), 11: (300, 575), 12: (305, 577),
                  13: (380, 525), 14: (390, 530), 15: (310, 650), 16: (320, 650)})


def chair_upright():
    return _full({0: (305, 290), 5: (300, 350), 6: (305, 352), 7: (315, 420), 8: (320, 422),
                  9: (380, 480), 10: (385, 482), 11: (300, 500), 12: (305, 502),
                  13: (450, 500), 14: (455, 505), 15: (450, 650), 16: (455, 650)})


def chair_slumped():
    k = chair_upright()
    k[0, :2], k[5, :2], k[6, :2] = (420, 340), (360, 370), (400, 400)
    return k


def sit_floor_long():
    return _full({0: (305, 410), 5: (300, 470), 6: (305, 472), 7: (330, 540), 8: (335, 542),
                  9: (380, 600), 10: (385, 602), 11: (300, 620), 12: (305, 622),
                  13: (450, 628), 14: (455, 632), 15: (600, 640), 16: (605, 642)})


def sit_floor_side():
    return _full({0: (300, 410), 5: (290, 470), 6: (310, 472), 7: (340, 540), 8: (345, 545),
                  9: (380, 640), 10: (385, 642), 11: (295, 620), 12: (305, 622),
                  13: (180, 630), 14: (190, 635), 15: (250, 645), 16: (255, 646)})


def sit_floor_cross():
    return _full({0: (300, 410), 5: (260, 470), 6: (340, 470), 7: (240, 540), 8: (360, 540),
                  9: (260, 600), 10: (340, 600), 11: (275, 620), 12: (325, 620),
                  13: (190, 615), 14: (410, 615), 15: (290, 640), 16: (310, 640)})


def sit_heel():
    return _full({0: (300, 365), 5: (300, 425), 6: (305, 427), 7: (320, 500), 8: (325, 502),
                  9: (360, 560), 10: (365, 562), 11: (300, 575), 12: (305, 577),
                  13: (420, 640), 14: (425, 642), 15: (300, 646), 16: (305, 646)})


def kneel_bilateral():
    return _full({0: (300, 280), 5: (260, 340), 6: (340, 340), 7: (245, 410), 8: (355, 410),
                  9: (240, 480), 10: (360, 480), 11: (275, 490), 12: (325, 490),
                  13: (275, 640), 14: (325, 640), 15: (275, 646), 16: (325, 646)})


def kneel_half_left():
    k = kneel_bilateral()
    k[14, :2] = (330, 500)            # 오른 무릎 세움
    k[16, :2] = (330, 648)            # 오른 발 바닥
    return k


def quadruped():
    return _full({0: (200, 470), 5: (250, 495), 6: (255, 500), 7: (250, 570), 8: (255, 572),
                  9: (250, 645), 10: (255, 646), 11: (400, 495), 12: (405, 500),
                  13: (400, 640), 14: (405, 642), 15: (520, 645), 16: (525, 646)})


def bear_pose():
    return _full({0: (200, 450), 5: (250, 470), 6: (255, 475), 7: (245, 560), 8: (250, 562),
                  9: (240, 646), 10: (245, 646), 11: (400, 430), 12: (405, 432),
                  13: (440, 560), 14: (445, 562), 15: (480, 648), 16: (485, 648)})


def lying_flat():
    """머리(또는 발) 쪽에서 본 앙와위: 몸통이 짧게 보이고 양 어깨가 나란함."""
    return _full({0: (300, 632), 5: (250, 640), 6: (350, 640), 7: (230, 642), 8: (370, 642),
                  9: (225, 645), 10: (375, 645), 11: (275, 645), 12: (325, 645),
                  13: (275, 630), 14: (325, 630), 15: (275, 620), 16: (325, 620)})


def lying_fetal():
    return _full({0: (70, 630), 5: (100, 625), 6: (100, 655), 7: (150, 630), 8: (150, 640),
                  9: (170, 620), 10: (175, 625), 11: (250, 630), 12: (250, 650),
                  13: (190, 600), 14: (190, 615), 15: (290, 640), 16: (290, 645)})


def prone_on_elbows():
    return _full({0: (150, 520), 5: (200, 560), 6: (205, 562), 7: (200, 640), 8: (205, 642),
                  9: (140, 645), 10: (145, 646), 11: (330, 635), 12: (335, 637),
                  13: (470, 640), 14: (475, 642), 15: (600, 645), 16: (605, 646)})


def side_lying_on_elbow():
    return _full({0: (150, 525), 5: (190, 560), 6: (195, 575), 7: (190, 640), 8: (260, 560),
                  9: (130, 645), 10: (300, 600), 11: (300, 640), 12: (300, 645),
                  13: (440, 638), 14: (445, 642), 15: (580, 645), 16: (585, 646)})


def reclined():
    return _full({0: (140, 400), 5: (180, 420), 6: (185, 425), 7: (230, 470), 8: (235, 472),
                  9: (250, 480), 10: (255, 482), 11: (300, 500), 12: (303, 503),
                  13: (420, 480), 14: (425, 485), 15: (540, 490), 16: (545, 492)})


def lean_support(cx=300.0):
    return trunk_flexion(30, cx)


def forward_flexion(cx=300.0):
    return trunk_flexion(70, cx)


ALL_POSTURES = {
    # 기대 분류 이름: 생성 함수
    "STAND_UPRIGHT": standing, "STAND_ONE_LEG": stand_one_leg, "STAND_LEAN_SUPPORT": lean_support,
    "FORWARD_FLEXION": forward_flexion, "SQUAT_PARTIAL": squat_partial, "SQUAT_DEEP": squat_deep,
    "SIT_CHAIR_UPRIGHT": chair_upright, "SIT_CHAIR_SLUMPED": chair_slumped,
    "SIT_FLOOR_LONG": sit_floor_long, "SIT_FLOOR_CROSS": sit_floor_cross, "SIT_FLOOR_SIDE": sit_floor_side,
    "SIT_FLOOR_KNEES_UP": sitting_floor, "SIT_HEEL": sit_heel,
    "KNEEL_BILATERAL": kneel_bilateral, "KNEEL_HALF_L": kneel_half_left,
    "QUADRUPED": quadruped, "BEAR_POSE": bear_pose,
    "LYING_FLAT": lying_flat, "LYING_SIDE_R": side_lying, "LYING_FETAL": lying_fetal,
    "PRONE_ON_ELBOWS": prone_on_elbows, "SIDE_LYING_ON_ELBOW": side_lying_on_elbow,
    "RECLINED_SUPPORTED": reclined,
}
