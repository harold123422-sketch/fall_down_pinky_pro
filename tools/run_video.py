#!/usr/bin/env python3
"""영상 파일(또는 카메라 번호, http 스트림 주소) -> 프레임별 CSV + 오버레이 영상.

예)  python3 tools/run_video.py --source clip.mp4 --out-dir out/clip
     python3 tools/run_video.py --source 0 --max-seconds 10 --save-raw out/raw.mp4 --out-dir out/webcam

ROS가 필요 없다. ROS 노드(ros/fall_node_adapter.py)와 같은 fall_core 코드를 쓴다.
"""
import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
from ultralytics import YOLO  # noqa: E402

from fall_core import FallCoreEngine, load_thresholds  # noqa: E402
from fall_core.iou_tracker import IoUTracker  # noqa: E402
from fall_core.viz import draw_tracks  # noqa: E402
from fall_core.yolo_io import build_detections, parse_result  # noqa: E402

FEATURE_COLS = ["L_trunk", "knee_angle_L", "knee_angle_R", "hip_angle_L", "hip_angle_R",
                "knee_hip_dx_L", "knee_hip_dx_R", "trunk_tilt_deg"]
HEADER = (["frame_idx", "t_s", "track_id", "box_conf"]
          + [f"kp{i}_{c}" for i in range(17) for c in "xyc"]
          + FEATURE_COLS
          + ["L_trunk_ref", "pelvis_y_norm", "descent_speed",
             "posture", "mode", "immobile_elapsed_s", "alert", "fall_event_t_s"])


def frame_time_s(cap, idx, fps, is_live, t_start):
    """프레임 타임스탬프(초). 나중에 ffprobe로 뽑은 값으로 바꿔 끼울 수 있게 함수로 분리했다.

    파일: OpenCV CAP_PROP_POS_MSEC (0이면 idx/fps로 대체) / 실시간: 읽은 시각(monotonic)
    """
    if is_live:
        return time.monotonic() - t_start
    ms = cap.get(cv2.CAP_PROP_POS_MSEC)
    return ms / 1000.0 if ms and ms > 0 else idx / fps


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", required=True, help="영상 파일 경로, 카메라 번호(0, 2 ...), 또는 http 주소")
    ap.add_argument("--out-dir", default="out_run_video")
    ap.add_argument("--model", default="yolo11n-pose.pt")
    ap.add_argument("--thresholds", default=None, help="기본: config/thresholds.yaml")
    ap.add_argument("--imgsz", type=int, default=480)
    ap.add_argument("--conf", type=float, default=0.4)
    ap.add_argument("--max-frames", type=int, default=0)
    ap.add_argument("--max-seconds", type=float, default=0, help="실시간 입력일 때 이 시간 후 종료")
    ap.add_argument("--out-fps", type=float, default=15.0, help="실시간 입력일 때 오버레이 영상 fps")
    ap.add_argument("--save-raw", default=None, help="실시간 입력일 때 원본 영상도 저장 (나중에 다시 분석용)")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()

    cfg = load_thresholds(a.thresholds)
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    src = int(a.source) if a.source.isdigit() else a.source
    is_live = isinstance(src, int) or str(src).startswith(("http://", "https://", "rtsp://"))
    cap = cv2.VideoCapture(src, cv2.CAP_V4L2) if isinstance(src, int) else cv2.VideoCapture(src)
    if not cap.isOpened():
        sys.exit(f"영상을 열 수 없습니다: {a.source}")
    fps = cap.get(cv2.CAP_PROP_FPS) or a.out_fps
    out_fps = a.out_fps if is_live else fps

    model = YOLO(a.model)
    engine = FallCoreEngine(cfg)
    tracker = IoUTracker()
    writer = raw_writer = None
    t_start = time.monotonic()

    csv_path = out / "features.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fcsv:
        w = csv.writer(fcsv)
        w.writerow(HEADER)
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = frame_time_s(cap, idx, fps, is_live, t_start)
            if a.max_seconds and t > a.max_seconds:
                break
            if a.save_raw and raw_writer is None:
                Path(a.save_raw).parent.mkdir(parents=True, exist_ok=True)
                raw_writer = cv2.VideoWriter(a.save_raw, cv2.VideoWriter_fourcc(*"mp4v"), out_fps,
                                             (frame.shape[1], frame.shape[0]))
            if raw_writer is not None:
                raw_writer.write(frame)

            res = model(frame, imgsz=a.imgsz, conf=a.conf, verbose=False)[0]
            boxes, confs, kpts = parse_result(res)
            ids = tracker.update(boxes, t)
            dets = build_detections(ids, boxes, confs, kpts)
            results = engine.update(t, dets)

            for d, r in zip(dets, results):
                row = [idx, f"{t:.4f}", r.track_id, f"{d['box_conf']:.3f}"]
                row += [f"{v:.2f}" for k in d["kpts"] for v in k]
                row += [f"{r.features[c]:.3f}" for c in FEATURE_COLS]
                row += [f"{r.l_trunk_ref:.2f}", f"{r.pelvis_y_norm:.3f}", f"{r.descent_speed:.3f}",
                        r.posture.name, r.mode.name, f"{r.immobile_elapsed_s:.2f}", r.alert.name,
                        "" if r.fall_event_t_s != r.fall_event_t_s else f"{r.fall_event_t_s:.3f}"]
                w.writerow(row)
                for e in r.events:
                    print(f"[{t:7.2f}s] ID{r.track_id} {e}")

            overlay = draw_tracks(frame.copy(), dets, results, cfg["keypoint_conf_min"],
                                  footer=f"t={t:.1f}s  frame {idx}")
            if writer is None:
                writer = cv2.VideoWriter(str(out / "overlay.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), out_fps,
                                         (overlay.shape[1], overlay.shape[0]))
            writer.write(overlay)
            if a.show:
                cv2.imshow("run_video", overlay)
                if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                    break
            idx += 1
            if a.max_frames and idx >= a.max_frames:
                break

    cap.release()
    for obj in (writer, raw_writer):
        if obj is not None:
            obj.release()
    cv2.destroyAllWindows()
    print(f"완료: {idx}프레임 -> {csv_path}, {out / 'overlay.mp4'}")


if __name__ == "__main__":
    main()
