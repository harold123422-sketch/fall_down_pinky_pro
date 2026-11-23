"""위험 단계(비위험/주의/위험), 상황 설명, 관절 위치 표시, 변화 기록."""
import synthetic_poses as sp
from fall_core import FallCoreEngine
from fall_core.monitor_view import describe, events_from, joint_lines, render
from fall_core.risk import Level, level_for
from fall_core.status import build_status


def _msg(sim, pose, cfg):
    det = {"track_id": 1, "kpts": pose, "box_conf": 0.9}
    return build_status("cam0", 123.0, [det], [sim.last()], cfg)


def _sim(cfg, **kw):
    return sp.Sim(FallCoreEngine(cfg), **kw)


def test_level_mapping_follows_yaml(cfg):
    assert level_for("NONE", cfg) == Level.SAFE
    assert level_for("CHECK_STANDING_IMMOBILE", cfg) == Level.CAUTION
    assert level_for("POST_FALL_MOVING", cfg) == Level.CAUTION
    assert level_for("FALL_EVENT", cfg) == Level.DANGER
    assert level_for("EMERGENCY_POST_FALL_IMMOBILE", cfg) == Level.DANGER
    cfg["risk_levels"]["FALL_EVENT"] = "CAUTION"            # 매핑은 yaml에서 바꿀 수 있다
    assert level_for("FALL_EVENT", cfg) == Level.CAUTION


def test_standing_is_safe_and_described(cfg):
    sim = _sim(cfg)
    sim.hold(sp.standing(), 5)
    msg = _msg(sim, sp.standing(), cfg)
    assert msg["level"] == "SAFE" and msg["state"] == "NONE"
    d = describe(msg["tracks"][0], msg)
    assert "서 있는" in d["posture"]
    assert any("곧게" in b for b in d["body"])


def test_standing_still_30s_is_caution(cfg):
    sim = _sim(cfg)
    sim.hold(sp.standing(), 33)
    msg = _msg(sim, sp.standing(), cfg)
    assert msg["level"] == "CAUTION"
    assert "확인을 요청" in describe(msg["tracks"][0], msg)["reason"]


def test_fall_then_still_is_danger_with_seconds(cfg):
    sim = _sim(cfg)
    sim.hold(sp.standing(), 3)
    sim.move(sp.standing(), sp.side_lying(), 0.6)
    sim.hold(sp.side_lying(), 36)
    msg = _msg(sim, sp.side_lying(), cfg)
    assert msg["level"] == "DANGER" and msg["state"] == "EMERGENCY_POST_FALL_IMMOBILE"
    d = describe(msg["tracks"][0], msg)
    assert "움직임이 없습니다" in d["reason"] and "즉시" in d["reason"]
    assert any("누워" in b for b in d["body"])


def test_unknown_names_the_missing_joints(cfg):
    pose = sp.with_conf(sp.with_conf(sp.standing(), 15, 0.1), 16, 0.1)      # 양 발목 안 보임
    sim = _sim(cfg)
    sim.hold(pose, 1)
    msg = _msg(sim, pose, cfg)
    d = describe(msg["tracks"][0], msg)
    assert "판단할 수 없음" in d["posture"]
    assert "왼쪽 발목" in d["posture"] and "오른쪽 발목" in d["posture"]


def test_joint_lines_show_positions_and_hidden(cfg):
    pose = sp.with_conf(sp.standing(), 15, 0.1)
    sim = _sim(cfg)
    sim.hold(pose, 1)
    msg = _msg(sim, pose, cfg)
    lines = "\n".join(joint_lines(msg["tracks"][0], msg["keypoint_conf_min"]))
    assert "코 (300," in lines                  # 코 좌표 (300, 140)
    ankle_line = [ln for ln in lines.split("\n") if ln.startswith("발목")][0]
    assert "왼 가려짐" in ankle_line and "오른 (325,650)" in ankle_line   # 신뢰도 낮은 왼쪽 발목만 가려짐
    assert len([ln for ln in joint_lines(msg["tracks"][0], 0.5)]) == 7


def test_render_banner_and_no_ansi_when_plain(cfg):
    sim = _sim(cfg)
    sim.hold(sp.standing(), 3)
    msg = _msg(sim, sp.standing(), cfg)
    text = render(msg, [], "12:00:00", color=False)
    assert "위험 단계" in text and "비위험" in text and "관절 위치" in text
    assert "\x1b[" not in text
    assert "\x1b[" in render(msg, [], "12:00:00", color=True)
    assert "수신 대기" in render(None, [], "12:00:00", color=False)


def test_render_without_people(cfg):
    msg = {"camera_id": "cam0", "stamp": 1.0, "state": "NO_PERSON", "level": "SAFE",
           "keypoint_conf_min": 0.5, "limits": {}, "tracks": []}
    text = render(msg, [], "12:00:00", color=False)
    assert "사람이 보이지 않습니다" in text


def test_events_only_when_level_or_alert_changes(cfg):
    sim = _sim(cfg)
    prev, out = {}, []
    sim.hold(sp.standing(), 3)
    out += events_from(prev, _msg(sim, sp.standing(), cfg), "t1")
    out += events_from(prev, _msg(sim, sp.standing(), cfg), "t2")          # 같은 상태: 기록 없음
    assert out == []                                                       # 처음부터 비위험이면 기록하지 않음
    sim.move(sp.standing(), sp.side_lying(), 0.6)
    sim.hold(sp.side_lying(), 2)
    out += events_from(prev, _msg(sim, sp.side_lying(), cfg), "t3")        # 비위험 -> 위험
    assert len(out) == 1 and "[위험]" in out[0]
