"""가벼운 사람 추적기 (IoU + 중심 거리). ultralytics 내장 추적(ByteTrack)은 lap 라이브러리가 필요하고
인터넷 없이는 설치할 수 없어서, 외부 의존성 없이 쓰도록 직접 만들었다.

넘어지는 동안 박스가 세로로 긴 모양에서 가로로 긴 모양으로 바뀌어 IoU가 급락할 수 있으므로,
IoU가 낮아도 중심이 가까우면 같은 사람으로 이어 붙인다.
"""
import numpy as np


def _iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / area if area > 0 else 0.0


def _center(b):
    return np.array([(b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0])


class IoUTracker:
    def __init__(self, iou_min=0.2, dist_frac=0.6, max_age_s=1.0):
        self.iou_min = iou_min
        self.dist_frac = dist_frac        # 중심 거리 허용 = 이전 박스 대각선 x dist_frac
        self.max_age_s = max_age_s
        self.tracks = {}                  # id -> {"box":..., "t":...}
        self._next = 1

    def update(self, boxes, t):
        """boxes: (N,4) xyxy. 각 박스의 track_id 리스트를 돌려준다."""
        boxes = [np.asarray(b, float) for b in boxes]
        for tid in [i for i, tr in self.tracks.items() if t - tr["t"] > self.max_age_s]:
            del self.tracks[tid]

        pairs = []
        for tid, tr in self.tracks.items():
            diag = float(np.hypot(tr["box"][2] - tr["box"][0], tr["box"][3] - tr["box"][1]))
            for j, b in enumerate(boxes):
                iou = _iou(tr["box"], b)
                dist = float(np.linalg.norm(_center(tr["box"]) - _center(b)))
                near = dist <= self.dist_frac * diag
                if iou >= self.iou_min or near:
                    pairs.append((iou + 0.5 * max(0.0, 1 - dist / max(self.dist_frac * diag, 1e-6)), tid, j))
        pairs.sort(reverse=True)

        ids = [None] * len(boxes)
        used = set()
        for _, tid, j in pairs:
            if ids[j] is None and tid not in used:
                ids[j] = tid
                used.add(tid)
        for j, b in enumerate(boxes):
            if ids[j] is None:
                ids[j] = self._next
                self._next += 1
            self.tracks[ids[j]] = {"box": b, "t": t}
        return ids
