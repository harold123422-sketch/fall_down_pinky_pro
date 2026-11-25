"""오버레이 그리기 (OpenCV). 코어 판정 로직과 분리: 이 모듈만 cv2를 쓴다.
OpenCV 기본 글꼴은 한글을 못 그리므로 화면 글자는 영어로 표시한다."""
import cv2

from fall_core.states import Alert

SKELETON = [(5, 6), (5, 7), (7, 9), (6, 8), (8, 10), (5, 11), (6, 12), (11, 12),
            (11, 13), (13, 15), (12, 14), (14, 16), (0, 1), (0, 2), (1, 3), (2, 4)]

# BGR
ALERT_COLOR = {
    Alert.NONE: (0, 200, 0),
    Alert.CHECK_STANDING_IMMOBILE: (0, 220, 255),
    Alert.POSTURE_CAUTION: (0, 220, 255),
    Alert.CHECK_POSTURE_IMMOBILE: (0, 220, 255),
    Alert.SELF_RECOVERABLE: (0, 200, 255),
    Alert.FALL_EVENT: (0, 140, 255),
    Alert.POST_FALL_MOVING: (0, 140, 255),
    Alert.EMERGENCY_POST_FALL_IMMOBILE: (0, 0, 255),
}


def _text(img, s, org, color=(255, 255, 255), scale=0.5, thick=1):
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thick + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)


def draw_skeleton(img, k, color, conf_min):
    for a, b in SKELETON:
        if k[a, 2] >= conf_min and k[b, 2] >= conf_min:
            cv2.line(img, (int(k[a, 0]), int(k[a, 1])), (int(k[b, 0]), int(k[b, 1])), color, 2)
    for i in range(17):
        if k[i, 2] >= conf_min:
            cv2.circle(img, (int(k[i, 0]), int(k[i, 1])), 3, (255, 255, 255), -1)
            cv2.circle(img, (int(k[i, 0]), int(k[i, 1])), 3, color, 1)


def _f(x, fmt="{:.0f}"):
    return fmt.format(x) if x == x else "-"


def draw_tracks(img, dets, results, conf_min, footer=None):
    """dets(검출)와 results(엔진 결과)를 같은 순서로 받아 한 장에 그린다. img를 직접 수정해서 돌려준다."""
    top = Alert.NONE
    for d, r in zip(dets, results):
        color = ALERT_COLOR[r.alert]
        if r.alert.value > top.value:
            top = r.alert
        draw_skeleton(img, d["kpts"], color, conf_min)
        box = d.get("box")
        if box is not None:
            x1, y1 = int(box[0]), int(box[1])
            cv2.rectangle(img, (x1, y1), (int(box[2]), int(box[3])), color, 1)
        else:
            x1, y1 = 10, 60
        y0 = max(18, y1 - 48)
        f = r.features
        stage = f" stage {r.recovery_stage}/6" if getattr(r, "recovery_stage", None) else ""
        low = "?" if getattr(r, "posture_certainty", "HIGH") == "LOW" else ""      # ? = 2D에서 구분이 어려운 자세
        _text(img, f"ID{r.track_id} {getattr(r, 'posture_class', r.posture.name)}{low} | {r.mode.name}{stage}",
              (x1, y0), color, 0.5)
        _text(img, f"tilt {_f(f['trunk_tilt_deg'])}  knee L{_f(f['knee_angle_L'])}/R{_f(f['knee_angle_R'])}"
                   f"  still {r.immobile_elapsed_s:.1f}s", (x1, y0 + 16), (255, 255, 255), 0.45)
        if r.alert != Alert.NONE:
            _text(img, r.alert.name, (x1, y0 + 34), color, 0.55, 2)
    if top != Alert.NONE:                       # 경보가 있으면 화면 테두리를 같은 색으로
        h, w = img.shape[:2]
        cv2.rectangle(img, (0, 0), (w - 1, h - 1), ALERT_COLOR[top], 6)
    if footer:
        h = img.shape[0]
        _text(img, footer, (8, h - 10), (200, 255, 200), 0.5)
    return img
