#!/usr/bin/env python3
"""run_video.py가 만든 features.csv -> 특징값 시계열 그래프 (FALL_EVENT 시점에 세로선).

예)  python3 tools/plot_features.py out/clip/features.csv            # out/clip/features.png
"""
import argparse
import csv
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def _f(s):
    try:
        return float(s)
    except ValueError:
        return math.nan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--track", type=int, default=None, help="track_id (기본: 가장 많이 나온 사람)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    with open(a.csv, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit("CSV에 데이터가 없습니다 (사람이 검출되지 않았을 수 있습니다)")
    ids = [int(r["track_id"]) for r in rows]
    tid = a.track if a.track is not None else max(set(ids), key=ids.count)
    rows = [r for r in rows if int(r["track_id"]) == tid]

    t = [_f(r["t_s"]) for r in rows]
    series = [
        ("trunk_tilt_deg (deg)", [("trunk_tilt_deg", "trunk tilt")]),
        ("knee angle (deg)", [("knee_angle_L", "L"), ("knee_angle_R", "R")]),
        ("descent_speed (trunk/s)", [("descent_speed", "descent speed")]),
        ("immobile_elapsed_s (s)", [("immobile_elapsed_s", "immobile")]),
    ]
    fall_ts = sorted({_f(r["fall_event_t_s"]) for r in rows if r["fall_event_t_s"] != ""})

    fig, axes = plt.subplots(len(series), 1, figsize=(11, 9), sharex=True)
    for ax, (title, cols) in zip(axes, series):
        for col, label in cols:
            ax.plot(t, [_f(r[col]) for r in rows], label=label, lw=1.2)
        for ft in fall_ts:
            ax.axvline(ft, color="red", ls="--", lw=1.2)
        ax.set_ylabel(title, fontsize=8)
        ax.grid(alpha=0.3)
        if len(cols) > 1:
            ax.legend(loc="upper right", fontsize=8)
    axes[0].set_title(f"track {tid}   (red dashed = FALL_EVENT: {', '.join(f'{x:.1f}s' for x in fall_ts) or 'none'})")
    axes[-1].set_xlabel("time (s)")
    fig.tight_layout()
    out = Path(a.out) if a.out else Path(a.csv).with_suffix(".png")
    fig.savefig(out, dpi=110)
    print(f"그래프 저장: {out}")


if __name__ == "__main__":
    main()
