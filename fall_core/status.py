"""엔진 결과 -> /fall_status JSON용 dict. ROS 없이 시험할 수 있게 코어에 둔다.

{
  "camera_id", "stamp", "state"(가장 높은 경보 이름 / NO_PERSON), "level"(SAFE|CAUTION|DANGER),
  "keypoint_conf_min", "limits": {...},
  "tracks": [{track_id, posture, mode, alert, level, window, immobile_elapsed_s, trunk_tilt_deg,
              knee_angle_L/R, hip_angle_L/R, descent_speed, pelvis_height, box_conf, kpts(선택)}]
}
"""
from fall_core.risk import Level, level_for


def _num(x, nd=3):
    """JSON에는 NaN이 없으므로 None으로 바꾼다."""
    return None if x is None or x != x else round(float(x), nd)


def build_status(camera_id, stamp, dets, results, cfg, publish_keypoints=True, incidents=None):
    tracks = []
    for d, r in zip(dets, results):
        f = r.features
        item = {
            "track_id": r.track_id,
            "posture": r.posture.name, "mode": r.mode.name, "alert": r.alert.name,
            "level": level_for(r.alert.name, cfg).name,
            "window": r.window_status.name,                       # MOVING / IMMOBILE / INDETERMINATE
            "immobile_elapsed_s": round(float(r.immobile_elapsed_s), 2),
            "trunk_tilt_deg": _num(f["trunk_tilt_deg"], 1),
            "knee_angle_L": _num(f["knee_angle_L"], 1), "knee_angle_R": _num(f["knee_angle_R"], 1),
            "hip_angle_L": _num(f["hip_angle_L"], 1), "hip_angle_R": _num(f["hip_angle_R"], 1),
            "descent_speed": _num(r.descent_speed, 2),
            "pelvis_height": _num(r.pelvis_y_norm, 2),           # 바닥 위 높이 (몸통길이 단위)
            "box_conf": round(float(d["box_conf"]), 3),
            # 세부 자세 (posture_framework)
            "posture_class": r.posture_class, "posture_family": r.posture_family, "posture_ko": r.posture_ko,
            "posture_certainty": r.posture_certainty, "posture_reason": r.posture_reason,
            "posture_note": r.posture_note, "posture_held_s": round(float(r.posture_held_s), 1),
            "recovery_stage": r.recovery_stage, "floor_source": r.floor_source,
            "pelvis_speed": _num(r.pelvis_speed, 2),
            "events": list(r.events),                              # 이 프레임에 생긴 변화 (자세 전이, 경보 등)
            # 낙상 보고서용 (낙상 후에만 값이 있음)
            "fall_type": r.fall_type, "fall": r.fall_metrics,
            "pre_fall_posture": r.pre_fall_posture, "landing_posture": r.landing_posture,
        }
        if publish_keypoints:
            item["kpts"] = [[round(float(v), 2) for v in kp] for kp in d["kpts"]]
        tracks.append(item)

    top = None
    for tr, r in zip(tracks, results):
        key = (Level[tr["level"]].value, r.alert.value)
        if top is None or key > top[0]:
            top = (key, tr, r)
    a = cfg["alerts"]
    return {
        "camera_id": camera_id, "stamp": round(float(stamp), 3),
        "state": top[2].alert.name if top else "NO_PERSON",
        "level": top[1]["level"] if top else Level.SAFE.name,
        "keypoint_conf_min": cfg["keypoint_conf_min"],
        "limits": {"emergency_s": a["post_fall_immobile_emergency_s"],
                   "check_s": a["standing_immobile_check_s"],
                   "pelvis_floor_max": cfg["fall_event"]["pelvis_floor_max"]},
        "tracks": tracks,
        "incidents": incidents or [],                          # 진행 중인 응급 대응 (IncidentManager.summaries)
    }
