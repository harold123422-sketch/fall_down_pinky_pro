"""낙상 모양 계산 (보고서용). 순수 Python.

낙상 사건이 감지된 순간, 최근 골반 중점 궤적으로 다음을 계산한다.
  - 하강 시작 시점 : 골반이 가장 높던 곳에서 몸통 길이 × descent_start_drop 이상 내려가기 시작한 마지막 시점
  - 걸린 시간      : 하강 시작 → 지금(바닥 도달)
  - 수직 하강      : 골반이 내려간 거리 (몸통 길이 단위)
  - 수평 이동      : 그동안 골반이 옆으로 움직인 거리 (몸통 길이 단위)
  - 하강 속도      : 평균, 최고 (몸통 길이/초 -> subject.trunk_length_m 을 곱해 m/s)
  - 모양           : 수평 ÷ 수직 ≤ vertical_ratio_max 이면 '수직 낙하', 아니면 '옆으로 이동하며 넘어짐'
  - 방향           : 화면 기준 왼쪽/오른쪽 (2D라 앞·뒤는 알 수 없음)

m/s 값은 2D 화면 투영과 몸통 길이 임시값에 기대는 근사치다. IMU(Sacrum S2) 측정으로 확인 예정.
"""
import math


def describe_descent(history, t, l_ref, cfg, lookback_s, peak_speed=None, fall_type="FALL"):
    """반환: dict. 계산할 수 없으면 None."""
    ft = cfg["fall_type"]
    m_per_trunk = cfg["subject"]["trunk_length_m"]
    if l_ref is None or not (l_ref > 1e-6):
        return None
    pts = [(s.t, s.features.get("pelvis_x"), s.features.get("pelvis_y")) for s in history.window(t, lookback_s)]
    pts = [p for p in pts if p[1] is not None and p[2] is not None and p[1] == p[1] and p[2] == p[2]]
    if len(pts) < 2:
        return None
    t_now, x_now, y_now = pts[-1]
    i_top = min(range(len(pts)), key=lambda i: pts[i][2])            # 화면 y가 가장 작은 곳 = 골반이 가장 높던 곳
    y_top = pts[i_top][2]
    i_start = i_top
    for i in range(i_top, len(pts)):                                 # 가장 높던 곳 이후, 아직 거의 안 내려간 마지막 시점
        if (pts[i][2] - y_top) / l_ref <= ft["descent_start_drop"]:
            i_start = i
        else:
            break
    t0, x0, y0 = pts[i_start]
    duration = max(t_now - t0, 1e-6)
    drop = (y_now - y0) / l_ref
    horiz = abs(x_now - x0) / l_ref
    ratio = horiz / drop if drop > 1e-6 else math.inf
    vertical = ratio <= ft["vertical_ratio_max"]
    direction = "" if horiz < 0.2 else ("화면 오른쪽" if x_now > x0 else "화면 왼쪽")
    mean_speed = drop / duration
    peak = peak_speed if peak_speed is not None and peak_speed == peak_speed else mean_speed

    if fall_type == "SLIP_DOWN":
        shape_ko = "미끄러져 내려앉음(슬립다운)"
    elif vertical:
        shape_ko = "수직 낙하(제자리에서 주저앉듯 넘어짐)"
    else:
        shape_ko = f"{direction or '옆'}으로 이동하며 넘어짐(걸림·미끄러짐 의심)"
    return {
        "fall_type": fall_type,
        "shape": "SLIP_DOWN" if fall_type == "SLIP_DOWN" else ("VERTICAL" if vertical else "LATERAL"),
        "shape_ko": shape_ko,
        "direction": direction,
        "duration_s": round(duration, 2),
        "drop_trunk": round(drop, 2),
        "horizontal_trunk": round(horiz, 2),
        "horizontal_vertical_ratio": round(ratio, 2) if ratio != math.inf else None,
        "mean_speed_trunk_s": round(mean_speed, 2),
        "peak_speed_trunk_s": round(peak, 2),
        "mean_speed_mps": round(mean_speed * m_per_trunk, 2),
        "peak_speed_mps": round(peak * m_per_trunk, 2),
        "drop_m": round(drop * m_per_trunk, 2),
    }
