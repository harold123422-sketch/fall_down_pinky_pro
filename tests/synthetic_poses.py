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
