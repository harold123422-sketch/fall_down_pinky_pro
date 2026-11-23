"""track_id별 시계열 버퍼 (타임스탬프 기반, 프레임 수가 아니라 초 단위로 관리)."""
from collections import deque
from dataclasses import dataclass, field


@dataclass
class Sample:
    t: float                 # 프레임 타임스탬프(초)
    kpts: object             # (17, 3) 배열
    features: dict = field(default_factory=dict)   # L_trunk, pelvis_y 등
    posture: object = None


class TrackHistory:
    """최근 keep_s초 동안의 샘플만 보관한다."""

    def __init__(self, keep_s=5.0):
        self.keep_s = keep_s
        self.samples = deque()

    def add(self, sample):
        self.samples.append(sample)
        while self.samples and sample.t - self.samples[0].t > self.keep_s:
            self.samples.popleft()

    def window(self, t, span_s):
        """[t - span_s, t] 구간의 샘플 목록 (오래된 것부터)."""
        return [s for s in self.samples if t - s.t <= span_s]

    def __len__(self):
        return len(self.samples)
