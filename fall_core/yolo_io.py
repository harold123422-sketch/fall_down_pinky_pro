"""ultralytics 결과 -> fall_core 입력 형식 변환. (ultralytics를 import하지 않는다: 결과 객체의 속성만 읽는다)"""
import numpy as np


def parse_result(result):
    """YOLO-pose Results 1개 -> (boxes (N,4) xyxy, box_conf (N,), kpts (N,17,3)). 검출이 없으면 빈 배열."""
    if result.boxes is None or result.keypoints is None or len(result.boxes) == 0:
        return np.zeros((0, 4)), np.zeros(0), np.zeros((0, 17, 3))
    return (result.boxes.xyxy.cpu().numpy(),
            result.boxes.conf.cpu().numpy(),
            result.keypoints.data.cpu().numpy())


def build_detections(track_ids, boxes, confs, kpts):
    """FallCoreEngine.update()에 넣는 형식으로 묶는다."""
    return [{"track_id": int(i), "kpts": k, "box_conf": float(c), "box": b}
            for i, b, c, k in zip(track_ids, boxes, confs, kpts)]
