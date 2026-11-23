"""터미널 모니터 화면 만들기 (순수 Python, ROS 없음). 입력은 /fall_status JSON을 dict로 푼 것.

- 위험 단계: 비위험(초록) / 주의(노랑) / 위험(빨강)
- 상황 설명: 판정 근거, 몸 상태(몸통 기울기, 무릎, 골반 높이), 움직임 여부를 한국어 문장으로
- 관절 위치: COCO 17점의 픽셀 좌표 (신뢰도가 낮으면 '가려짐')

세부 자세(앉음, 누움, 무릎 꿇음 등)는 아직 구현되지 않았으므로 '서 있음 / 서 있지 않음 / 판단 불가'만 말한다.
"""
from collections import Counter

from fall_core.risk import LEVEL_KO, Level

JOINT_GROUPS = [
    ("머리  ", [("코", 0), ("왼눈", 1), ("오른눈", 2), ("왼귀", 3), ("오른귀", 4)]),
    ("어깨  ", [("왼", 5), ("오른", 6)]),
    ("팔꿈치", [("왼", 7), ("오른", 8)]),
    ("손목  ", [("왼", 9), ("오른", 10)]),
    ("고관절", [("왼", 11), ("오른", 12)]),
    ("무릎  ", [("왼", 13), ("오른", 14)]),
    ("발목  ", [("왼", 15), ("오른", 16)]),
]
STANDING_REQUIRED = (5, 6, 11, 12, 13, 14, 15, 16)
JOINT_KO = {0: "코", 1: "왼쪽 눈", 2: "오른쪽 눈", 3: "왼쪽 귀", 4: "오른쪽 귀", 5: "왼쪽 어깨", 6: "오른쪽 어깨",
            7: "왼쪽 팔꿈치", 8: "오른쪽 팔꿈치", 9: "왼쪽 손목", 10: "오른쪽 손목", 11: "왼쪽 고관절",
            12: "오른쪽 고관절", 13: "왼쪽 무릎", 14: "오른쪽 무릎", 15: "왼쪽 발목", 16: "오른쪽 발목"}

_RESET = "\x1b[0m"
_TEXT = {"SAFE": "\x1b[32m", "CAUTION": "\x1b[33m", "DANGER": "\x1b[1;31m"}
_BANNER = {"SAFE": "\x1b[30;42m", "CAUTION": "\x1b[30;43m", "DANGER": "\x1b[97;41m"}


def _paint(s, code, color):
    return f"{code}{s}{_RESET}" if color else s


def _t(tr, key):
    v = tr.get(key)
    return None if v is None else float(v)


def _tilt_text(tilt):
    if tilt is None:
        return "몸통 기울기를 알 수 없음"
    if tilt < 10:
        return f"몸통이 거의 곧게 서 있음({tilt:.0f}°)"
    if tilt < 30:
        return f"몸통이 약간 기울어 있음({tilt:.0f}°)"
    if tilt < 60:
        return f"몸통이 많이 기울어 있음({tilt:.0f}°)"
    return f"몸통이 거의 누워 있음({tilt:.0f}°)"


def _knee_text(kl, kr):
    vals = [v for v in (kl, kr) if v is not None]
    if not vals:
        return "무릎 각도를 알 수 없음"
    lo = min(vals)
    state = "펴져 있음" if lo >= 160 else ("약간 굽어 있음" if lo >= 120 else "많이 굽어 있음")
    parts = [f"{n}{v:.0f}°" for n, v in (("왼", kl), ("오른", kr)) if v is not None]
    return f"무릎 {state}({' / '.join(parts)})"


def _height_text(h, floor_max):
    if h is None:
        return "골반 높이를 알 수 없음"
    if h <= floor_max:
        return f"골반이 바닥 가까이 있음({h:.1f})"
    if h < 1.5:
        return f"골반이 중간 높이({h:.1f})"
    return f"골반이 높음({h:.1f})"


def missing_joints(tr, conf_min):
    """STANDING 판정에 필요한데 신뢰도가 낮아 안 보이는 관절 이름."""
    kp = tr.get("kpts")
    if not kp:
        return []
    return [JOINT_KO[i] for i in STANDING_REQUIRED if kp[i][2] < conf_min]


def describe(tr, msg):
    """한 사람의 상태를 문장으로. 반환: dict(posture, movement, reason, body, headline)."""
    limits = msg.get("limits", {})
    E, C = limits.get("emergency_s", 30.0), limits.get("check_s", 30.0)
    conf_min = msg.get("keypoint_conf_min", 0.5)
    posture, mode, alert = tr["posture"], tr["mode"], tr["alert"]
    sec = tr.get("immobile_elapsed_s", 0.0)

    if posture == "STANDING":
        posture_t = "서 있는 자세"
    elif posture == "NOT_STANDING":
        posture_t = "서 있지 않은 자세 (앉음·누움 등 세부 구분은 아직 하지 않음)"
    else:
        miss = missing_joints(tr, conf_min)
        posture_t = "자세를 판단할 수 없음 (필요한 관절이 안 보임" + (f": {', '.join(miss)})" if miss else ")")
    move_t = {"MOVING": "움직이는 중", "IMMOBILE": f"가만히 있음 ({sec:.0f}초째)",
              "INDETERMINATE": "움직임 판단 중"}.get(tr.get("window"), "움직임 판단 중")

    if alert == "EMERGENCY_POST_FALL_IMMOBILE":
        reason = f"낙상 후 {sec:.0f}초째 움직임이 없습니다 (기준 {E:.0f}초). 즉시 확인이 필요합니다"
    elif alert == "FALL_EVENT":
        reason = f"낙상이 감지되었습니다. 움직임 여부를 확인하는 중입니다 ({sec:.0f}/{E:.0f}초)"
    elif alert == "POST_FALL_MOVING":
        reason = "낙상 후 움직임이 보입니다. 스스로 일어나는지 확인이 필요합니다"
    elif alert == "CHECK_STANDING_IMMOBILE":
        reason = f"서 있는 채 {sec:.0f}초 동안 움직임이 없습니다 (기준 {C:.0f}초). 영상 확인을 요청합니다"
    elif mode == "RECOVERED":
        reason = "낙상 후 회복했습니다 (다시 서 있음)"
    elif posture == "STANDING" and tr.get("window") == "IMMOBILE":
        reason = f"정상입니다. 서 있는 채 {sec:.0f}초째 정지 중 ({C:.0f}초가 되면 확인을 요청합니다)"
    elif posture == "UNKNOWN":
        reason = "판단 보류: 관절이 충분히 보일 때까지 이전 상태를 유지합니다"
    else:
        reason = "특이사항이 없습니다"

    body = [_tilt_text(_t(tr, "trunk_tilt_deg")),
            _knee_text(_t(tr, "knee_angle_L"), _t(tr, "knee_angle_R")),
            _height_text(_t(tr, "pelvis_height"), limits.get("pelvis_floor_max", 0.6))]
    level = LEVEL_KO[Level[tr["level"]]]
    return {"posture": posture_t, "movement": move_t, "reason": reason, "body": body,
            "headline": f"[{level}] 사람 #{tr['track_id']}: {reason}"}


def _pt(kp, conf_min):
    if kp[2] < conf_min:
        return "가려짐"
    return f"({kp[0]:.0f},{kp[1]:.0f})"


def joint_lines(tr, conf_min):
    kp = tr.get("kpts")
    if not kp:
        return ["(관절 좌표가 없습니다: fall_core_node 를 -p publish_keypoints:=true 로 실행하세요)"]
    lines = []
    for title, items in JOINT_GROUPS:
        lines.append(f"{title} " + "  ".join(f"{n} {_pt(kp[i], conf_min)}" for n, i in items))
    return lines


def events_from(prev, msg, clock):
    """직전 메시지와 비교해서 단계/경보가 바뀐 사람의 변화 기록을 만든다. prev: {track_id: (level, alert)}"""
    out = []
    for tr in msg.get("tracks", []):
        key = (tr["level"], tr["alert"])
        if prev.get(tr["track_id"]) != key:
            if prev.get(tr["track_id"]) is not None or tr["level"] != "SAFE":
                out.append(f"{clock}  {describe(tr, msg)['headline']}")
            prev[tr["track_id"]] = key
    return out


def render(msg, events, clock, color=True, stale_s=0.0):
    """화면 한 장(문자열). msg가 None이면 대기 화면."""
    L = []
    L.append(_paint(f"═══ 핑키 낙상 모니터 ═══  {clock}", "\x1b[1m", color)
             + (f"   카메라 {msg['camera_id']}" if msg else ""))
    if msg is None:
        L += ["", "수신 대기 중... fall_core_node(또는 demo)가 켜져 있는지 확인하세요."]
        return "\n".join(L)
    if stale_s > 2.0:
        L.append(_paint(f"⚠ {stale_s:.0f}초째 새 데이터가 없습니다 (노드가 멈췄거나 연결이 끊김)", _TEXT["CAUTION"], color))

    tracks = msg.get("tracks", [])
    top = Level[msg["level"]]
    summary = "사람이 보이지 않습니다" if not tracks else None
    if tracks:
        best = max(tracks, key=lambda t: (Level[t["level"]].value, t["immobile_elapsed_s"]))
        summary = describe(best, msg)["reason"]
    L.append("")
    L.append(_paint(f"  위험 단계:  {LEVEL_KO[top]}  ", _BANNER[top.name], color)
             + "  " + _paint(summary, _TEXT[top.name], color))
    L.append("  (비위험 → 주의 → 위험)")

    conf_min = msg.get("keypoint_conf_min", 0.5)
    for tr in tracks:
        d = describe(tr, msg)
        lvl = tr["level"]
        L.append("")
        L.append(_paint(f"── 사람 #{tr['track_id']}  [{LEVEL_KO[Level[lvl]]}] ──", _TEXT[lvl], color))
        L.append(f"  동작 상태 : {d['posture']}, {d['movement']}")
        L.append(f"  판단 근거 : {d['reason']}")
        L.append("  몸 상태   : " + " · ".join(d["body"]))
        L.append(f"  내부 상태 : 모드 {tr['mode']} / 경보 {tr['alert']} / 검출 신뢰도 {tr['box_conf']:.2f}")
        L.append("  관절 위치 (픽셀, 신뢰도가 낮은 관절은 '가려짐'):")
        L += ["    " + s for s in joint_lines(tr, conf_min)]
    L.append("")
    L.append("최근 변화:")
    L += ["  " + e for e in events[-6:]] or ["  (아직 없음)"]
    L.append(_paint("종료: Ctrl+C", "\x1b[2m", color))
    return "\n".join(L)


# ---------------------------------------------------------------------------------------------
# 20초 단위 요약
# ---------------------------------------------------------------------------------------------
_RANK = {"SAFE": 0, "CAUTION": 1, "DANGER": 2}
_POSTURE_KO = {"STANDING": "서 있음", "NOT_STANDING": "서 있지 않음", "UNKNOWN": "판단 불가"}
_ALERT_KO = {
    "NONE": "특이사항 없음", "CHECK_STANDING_IMMOBILE": "서서 정지(확인 요청)",
    "POST_FALL_MOVING": "낙상 후 움직임", "FALL_EVENT": "낙상 감지",
    "EMERGENCY_POST_FALL_IMMOBILE": "낙상 후 정지(긴급)",
}


def escalations(prev, msg, clock, color=True):
    """단계가 '올라간' 순간만 한 줄로 알린다 (비위험->주의, 주의->위험, 비위험->위험). prev: {track_id: 단계 순위}"""
    out = []
    for tr in msg.get("tracks", []):
        rank = _RANK[tr["level"]]
        if rank > prev.get(tr["track_id"], 0):
            line = f"{clock}  ⚠ {describe(tr, msg)['headline']}"
            out.append(_paint(line, _TEXT[tr["level"]], color))
        prev[tr["track_id"]] = rank
    return out


class WindowSummary:
    """일정 시간(기본 20초) 동안의 /fall_status 를 모아서 한 번에 말해 주는 요약기. 시간은 호출하는 쪽의 초 단위."""

    def __init__(self, interval_s=20.0):
        self.interval = interval_s
        self.reset()

    def reset(self):
        self.t0 = None
        self.clock0 = ""
        self.n = 0
        self.no_person = 0
        self.last_msg = None
        self.level_seq = []          # [(clock, level)] 단계가 바뀐 시점
        self.level_max = "SAFE"
        self.tracks = {}

    def add(self, t, msg, clock):
        if self.t0 is None:
            self.t0, self.clock0 = t, clock
        self.n += 1
        self.last_msg = msg
        if not self.level_seq or self.level_seq[-1][1] != msg["level"]:
            self.level_seq.append((clock, msg["level"]))
        if _RANK[msg["level"]] > _RANK[self.level_max]:
            self.level_max = msg["level"]
        if not msg.get("tracks"):
            self.no_person += 1
        for tr in msg.get("tracks", []):
            st = self.tracks.setdefault(tr["track_id"], {
                "n": 0, "posture": Counter(), "window": Counter(), "max_still": 0.0,
                "alerts": [], "last_alert": None, "level_max": "SAFE", "last": None})
            st["n"] += 1
            st["posture"][tr["posture"]] += 1
            st["window"][tr.get("window", "INDETERMINATE")] += 1
            st["max_still"] = max(st["max_still"], tr.get("immobile_elapsed_s", 0.0))
            st["last"] = tr
            if _RANK[tr["level"]] > _RANK[st["level_max"]]:
                st["level_max"] = tr["level"]
            if tr["alert"] != st["last_alert"]:
                st["alerts"].append((clock, tr["alert"]))
                st["last_alert"] = tr["alert"]

    def due(self, t):
        return self.t0 is not None and t - self.t0 >= self.interval

    # ---- 문장 만들기
    def _overall(self):
        if self.n == 0:
            return "이 구간에는 신호가 없었습니다 (fall_core_node가 켜져 있는지 확인하세요)."
        if not self.tracks:
            return "사람이 보이지 않았습니다. 특이사항 없음."
        msg = self.last_msg
        now = msg["level"]
        # 지금 보이는 사람 중 가장 높은 단계 (마지막에 사람이 사라졌다면 구간 안에서 마지막으로 본 모습)
        candidates = msg["tracks"] or [t["last"] for t in self.tracks.values()]
        top = max(candidates, key=lambda t: _RANK[t["level"]])
        reason = describe(top, msg)["reason"]
        mx = self.level_max
        if mx == "DANGER":
            if now == "DANGER":
                return f"위험한 상태입니다. {reason}"
            return f"이 구간에서 위험 단계가 있었지만 지금은 {LEVEL_KO[Level[now]]}입니다 ({reason})."
        if mx == "CAUTION":
            if now == "CAUTION":
                return f"주의가 필요합니다. {reason}"
            return f"이 구간에서 주의 단계가 있었고 지금은 해소되었습니다 ({reason})."
        unknown = sum(st["posture"]["UNKNOWN"] for st in self.tracks.values())
        total = sum(st["n"] for st in self.tracks.values())
        if total and unknown / total >= 0.5:
            return (f"관절이 잘 보이지 않아 판단하지 못한 시간이 많았습니다 ({unknown / total:.0%}). "
                    "카메라 각도와 거리를 확인하세요. 그동안 위험 신호는 없었습니다.")
        return "특이사항 없음. 정상 범위입니다."

    def _track_lines(self, tid, st, color):
        total = max(1, self.n)
        shown = st["n"] / total
        pc = st["posture"]
        posture = " / ".join(f"{_POSTURE_KO[k]} {v / st['n']:.0%}" for k, v in pc.most_common())
        win = st["window"]
        moved, still = win["MOVING"] / st["n"], win["IMMOBILE"] / st["n"]
        move = f"움직인 시간 {moved:.0%}, 가만히 있던 시간 {still:.0%}"
        if st["max_still"] >= 3:
            move += f" (정지가 최대 {st['max_still']:.0f}초 이어짐)"
        lines = [f"  ▸ 사람 #{tid}  (구간의 {shown:.0%} 동안 보임, 최고 단계 {LEVEL_KO[Level[st['level_max']]]})",
                 f"      자세   : {posture}", f"      움직임 : {move}"]
        alerts = [f"{c} {_ALERT_KO.get(a, a)}" for c, a in st["alerts"] if a != "NONE"]
        if alerts:
            lines.append("      경보   : " + " → ".join(alerts))
        last = st["last"]
        d = describe(last, self.last_msg)
        lines.append("      몸 상태: " + " · ".join(d["body"]))
        conf_min = self.last_msg.get("keypoint_conf_min", 0.5)
        lines.append("      관절 위치 (구간 마지막 시점, 픽셀):")
        lines += ["        " + s for s in joint_lines(last, conf_min)]
        return lines

    def flush(self, clock_end, color=True, max_people=3):
        """요약 문자열을 만들고 다음 구간을 위해 초기화한다."""
        level_now = self.last_msg["level"] if self.last_msg else "SAFE"
        head = f"━━━━ {self.interval:.0f}초 요약  {self.clock0} ~ {clock_end} ━━━━"
        L = [_paint(head, "\x1b[1m", color)]
        banner = f"  종합 판단: [{LEVEL_KO[Level[level_now]]}] "
        L.append(_paint(banner, _BANNER[level_now], color) + " " + self._overall())
        if len(self.level_seq) > 1:
            L.append("  단계 변화: " + " → ".join(f"{LEVEL_KO[Level[lv]]}({c})" for c, lv in self.level_seq))
        ranked = sorted(self.tracks.items(), key=lambda kv: (-_RANK[kv[1]["level_max"]], -kv[1]["n"]))
        for tid, st in ranked[:max_people]:
            L += self._track_lines(tid, st, color)
        if len(ranked) > max_people:
            L.append(f"  (그 밖에 {len(ranked) - max_people}명은 생략)")
        text = "\n".join(L)
        self.reset()
        return text


# ---------------------------------------------------------------------------------------------
# 상태 한 줄 + 변화 알림 (기본 모드)
#   안정 상태가 이어지면 새 줄을 찍지 않고 한 줄만 그 자리에서 갱신한다.
#   상태가 바뀔 때만 멘트를 새 줄로 남긴다 (위험=빨강, 주의=노랑, 회복=초록).
# ---------------------------------------------------------------------------------------------
import unicodedata  # noqa: E402

_RED_BOLD = "\x1b[1;31m"
_EMERG = "\x1b[1;97;41m"
_YELLOW = "\x1b[33m"
_GREEN = "\x1b[32m"
_DIM = "\x1b[2m"


def display_width(s):
    """터미널에서 차지하는 칸 수 (한글·이모지는 2칸)."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def fit_width(s, cols):
    """한 줄이 터미널 폭을 넘으면 잘라낸다 (줄바꿈되면 같은 자리 갱신이 깨지므로)."""
    out, w = [], 0
    for ch in s:
        cw = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if w + cw > cols - 1:
            return "".join(out) + "…"
        out.append(ch)
        w += cw
    return s


def _fmt_dur(sec):
    sec = int(sec)
    if sec < 60:
        return f"{sec}초"
    if sec < 3600:
        return f"{sec // 60}분 {sec % 60}초"
    return f"{sec // 3600}시간 {sec % 3600 // 60}분"


class StatusNarrator:
    """/fall_status 를 받아 (새로 남길 멘트 줄들, 지금 상태 한 줄)을 만든다."""

    def __init__(self, color=True):
        self.color = color
        self.key = None            # (사람 있음, 경보, 모드)
        self.since = None          # 지금 상태가 시작된 시각
        self.prev_alert = None
        self.tick = 0

    def _c(self, s, code):
        return _paint(s, code, self.color)

    @staticmethod
    def top_track(msg):
        tracks = msg.get("tracks", [])
        if not tracks:
            return None
        return max(tracks, key=lambda t: (_RANK[t["level"]], t.get("immobile_elapsed_s", 0.0)))

    def start_line(self):
        return self._c("모니터링을 시작합니다. 안정 상태는 한 줄로만 표시하고, 위험하면 바로 알려 드립니다.", _DIM)

    def update(self, msg, t, clock):
        """메시지 하나를 반영. 상태가 바뀌었으면 남길 멘트 줄을 돌려준다."""
        top = self.top_track(msg)
        key = (top is not None, top["alert"] if top else None, top["mode"] if top else None)
        if key == self.key:
            return []
        prev_key, self.key, self.since = self.key, key, t
        prev_alert, self.prev_alert = self.prev_alert, (top["alert"] if top else None)
        limits = msg.get("limits", {})
        E = limits.get("emergency_s", 30.0)
        C = limits.get("check_s", 30.0)

        if top is None:
            if prev_key is None or not prev_key[0]:
                return [self._c(f"{clock}  ○ 아직 사람이 보이지 않습니다. 지켜보고 있습니다...", _DIM)]
            if prev_alert in ("FALL_EVENT", "EMERGENCY_POST_FALL_IMMOBILE", "POST_FALL_MOVING"):
                return [self._c(f"{clock}  🚨 낙상 후 사람이 화면에서 사라졌습니다! 위치를 다시 확인하는 중입니다...",
                                _RED_BOLD)]
            return [self._c(f"{clock}  ○ 사람이 화면에서 사라졌습니다. 다시 나타날 때까지 지켜봅니다.", _DIM)]

        who = f"사람 #{top['track_id']}"
        alert, mode = top["alert"], top["mode"]
        body = " · ".join(describe(top, msg)["body"])
        if alert == "FALL_EVENT":
            return [self._c(f"{clock}  🚨 낙상 위험 감지! {who}이(가) 빠르게 바닥으로 내려갔습니다. 상태를 파악 중입니다...",
                            _RED_BOLD),
                    self._c(f"          몸 상태: {body}", _RED_BOLD)]
        if alert == "EMERGENCY_POST_FALL_IMMOBILE":
            return [self._c(f"{clock}  🚨🚨 긴급! {who}이(가) 낙상 후 {E:.0f}초 동안 움직이지 않습니다. 즉시 확인이 필요합니다!",
                            _EMERG)]
        if alert == "POST_FALL_MOVING":
            return [self._c(f"{clock}  ⚠ 낙상 후 {who}의 움직임이 보입니다. 스스로 일어나는지 지켜보고 있습니다...", _YELLOW)]
        if alert == "CHECK_STANDING_IMMOBILE":
            return [self._c(f"{clock}  ⚠ 주의: {who}이(가) 서 있는 채 {C:.0f}초 넘게 움직이지 않습니다. 상태를 살펴보고 있습니다...",
                            _YELLOW)]
        # 여기부터 경보 없음(NONE)
        if mode == "RECOVERED" and prev_alert in ("FALL_EVENT", "EMERGENCY_POST_FALL_IMMOBILE", "POST_FALL_MOVING"):
            return [self._c(f"{clock}  ✅ 회복 확인: {who}이(가) 스스로 일어나 서 있습니다. 안정 상태로 돌아갑니다.", _GREEN)]
        if prev_alert == "CHECK_STANDING_IMMOBILE":
            return [self._c(f"{clock}  ✅ 다시 움직임이 확인되었습니다. 안정 상태로 돌아갑니다.", _GREEN)]
        if prev_key is None or not prev_key[0]:
            return [self._c(f"{clock}  ● {who}을(를) 확인했습니다. 안정 상태입니다.", _GREEN)]
        return []

    def status_line(self, msg, t, stale_s=0.0):
        """그 자리에서 계속 갱신할 한 줄 (색 포함)."""
        self.tick += 1
        dots = "." * (self.tick % 3 + 1) + " " * (2 - self.tick % 3)
        if msg is None:
            return self._c(f"… /fall_status 를 기다리는 중{dots} (fall_core_node가 켜져 있나요?)", _DIM)
        if stale_s > 2.0:
            return self._c(f"📡 {stale_s:.0f}초째 신호가 없습니다. 연결을 확인하는 중{dots}", _YELLOW)
        dur = _fmt_dur(t - self.since) if self.since is not None else "0초"
        top = self.top_track(msg)
        n = len(msg.get("tracks", []))
        if top is None:
            return self._c(f"○ 사람이 보이지 않습니다 — 대기 중{dots} ({dur})", _DIM)
        sec = top.get("immobile_elapsed_s", 0.0)
        E = msg.get("limits", {}).get("emergency_s", 30.0)
        alert = top["alert"]
        if alert == "EMERGENCY_POST_FALL_IMMOBILE":
            return self._c(f"🚨 긴급 상황 지속 중 — 움직임 없음 {sec:.0f}초, 즉시 확인 필요{dots}", _EMERG)
        if alert == "FALL_EVENT":
            return self._c(f"🚨 낙상 후 움직임 확인 중{dots} ({sec:.0f}/{E:.0f}초)", _RED_BOLD)
        if alert == "POST_FALL_MOVING":
            return self._c(f"⚠ 낙상 후 움직임 관찰 중{dots} (일어나는지 확인 중, {dur})", _YELLOW)
        if alert == "CHECK_STANDING_IMMOBILE":
            return self._c(f"⚠ 서 있는 채 정지 {sec:.0f}초째 — 상태 확인 중{dots}", _YELLOW)
        posture = {"STANDING": "서 있음", "NOT_STANDING": "서 있지 않음", "UNKNOWN": "자세 판단 보류"}[top["posture"]]
        moving = {"MOVING": "움직이는 중", "IMMOBILE": f"정지 {sec:.0f}초째"}.get(top.get("window"), "확인 중")
        who = f"사람 {n}명" if n > 1 else f"사람 #{top['track_id']}"
        label = "회복 후 안정 상태 진행 중" if top["mode"] == "RECOVERED" else "안정 상태 진행 중"
        return self._c(f"● {label}{dots} ({who} · {posture} · {moving} · 안정 유지 {dur})", _GREEN)
