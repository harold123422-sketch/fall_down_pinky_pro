"""/fall_status 를 구독해서 터미널에 상황을 말해 주는 모니터 노드.

  ros2 run fall_detection fall_monitor                                  # 상태 한 줄 + 변화 알림 (기본)
  ros2 run fall_detection fall_monitor --ros-args -p mode:=summary      # 20초마다 요약
  ros2 run fall_detection fall_monitor --ros-args -p mode:=live         # 실시간 대시보드 (화면을 계속 갱신)

mode:=status (기본)
  - 안정 상태가 이어지면 새 줄을 찍지 않고 '● 안정 상태 진행 중...' 한 줄만 그 자리에서 갱신한다.
  - 상태가 바뀔 때만 멘트를 새 줄로 남긴다. 위험=빨강(🚨 낙상 위험 감지! ... 상태를 파악 중입니다...),
    주의=노랑, 회복=초록.
  - plain:=true 이면 같은 자리 갱신 대신 summary_s초마다 상태 한 줄을 새로 남긴다 (파일 저장용).
mode:=summary
  - 화면을 지우지 않고 summary_s초마다 '그동안의 판단'을 한 블록으로 출력한다 (위로 스크롤하면 기록이 남음).
  - 안전을 위해 단계가 올라가는 순간(비위험->주의, ->위험)은 20초를 기다리지 않고 한 줄로 즉시 알린다.
    끄려면 -p alert_now:=false
mode:=live
  - 4Hz로 화면 전체를 다시 그리는 실시간 대시보드.

plain:=true 면 색과 화면 지우기를 쓰지 않는다 (파일로 저장할 때).
fall_core_node 와 같은 ROS 도메인에서 실행해야 한다 (같은 PC의 다른 터미널이면 그대로 됨).
"""
import json
import time

import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_msgs.msg import String

import shutil

from fall_core.monitor_view import StatusNarrator, WindowSummary, escalations, events_from, fit_width, render


class FallMonitor(Node):
    def __init__(self):
        super().__init__("fall_monitor")
        self.declare_parameter("mode", "status")         # status | summary | live
        self.declare_parameter("summary_s", 20.0)
        self.declare_parameter("alert_now", True)
        self.declare_parameter("plain", False)
        self.declare_parameter("interval_s", 0.25)       # live 모드 갱신 간격
        p = self.get_parameter
        self.mode = p("mode").value
        self.summary_s = p("summary_s").value
        self.alert_now = p("alert_now").value
        self.plain = p("plain").value

        self.msg, self.last_rx = None, None
        self.prev_events, self.prev_rank, self.events = {}, {}, []
        self.summary = WindowSummary(self.summary_s)
        self.sub = self.create_subscription(String, "/fall_status", self.on_msg, 10)
        if self.mode == "live":
            self.timer = self.create_timer(p("interval_s").value, self.draw_live)
        elif self.mode == "status":
            self.narrator = StatusNarrator(color=not self.plain)
            self.pending = []                            # 새 줄로 남길 멘트 (콜백에서 모았다가 타이머에서 출력)
            self.last_heartbeat = time.monotonic()
            self.stale_reported = False
            self.timer = self.create_timer(0.5, self.tick_status)
            print(self.narrator.start_line(), flush=True)
        else:
            self.timer = self.create_timer(0.5, self.tick_summary)
            print(f"{self.summary_s:.0f}초마다 상황을 요약해서 말씀드립니다. "
                  + ("단계가 올라가면 바로 알립니다." if self.alert_now else "") + "  (종료: Ctrl+C)", flush=True)

    def _now_text(self):  # (주의: Node 내부의 _clock 과 이름이 겹치면 안 됨)
        return time.strftime("%H:%M:%S")

    def on_msg(self, m):
        try:
            self.msg = json.loads(m.data)
        except json.JSONDecodeError:
            return
        self.last_rx = time.monotonic()
        if self.mode == "status":
            self.pending += self.narrator.update(self.msg, self.last_rx, self._now_text())
            self.stale_reported = False
            return
        if self.mode == "live":
            self.events += events_from(self.prev_events, self.msg, self._now_text())
            return
        self.summary.add(self.last_rx, self.msg, self._now_text())
        if self.alert_now:
            for line in escalations(self.prev_rank, self.msg, self._now_text(), color=not self.plain):
                print(line, flush=True)

    def tick_status(self):
        now = time.monotonic()
        stale = (now - self.last_rx) if self.last_rx else 0.0
        if stale > 2.0 and not self.stale_reported:
            self.pending.append(self.narrator._c(
                f"{self._now_text()}  📡 신호가 끊겼습니다. fall_core_node 와 카메라 연결을 확인하는 중입니다...",
                "\x1b[33m"))
            self.stale_reported = True
        line = self.narrator.status_line(self.msg, now, stale)
        if self.plain:
            for ln in self.pending:
                print(ln, flush=True)
            if self.pending or now - self.last_heartbeat >= self.summary_s:
                print(f"{self._now_text()}  {line}", flush=True)
                self.last_heartbeat = now
        else:
            cols = shutil.get_terminal_size((100, 20)).columns
            for ln in self.pending:
                print("\r\x1b[K" + ln, flush=True)          # 상태 줄을 지우고 멘트를 새 줄로 남김
            # 상태 줄은 터미널 폭을 넘지 않게 잘라서 같은 자리에 다시 씀 (색 코드는 자르기 전에 떼어 냄)
            raw = line.replace("\x1b[0m", "")
            code = raw[:raw.index("m") + 1] if raw.startswith("\x1b[") else ""
            text = raw[len(code):]
            print("\r\x1b[K" + code + fit_width(text, cols) + ("\x1b[0m" if code else ""), end="", flush=True)
        self.pending = []

    def tick_summary(self):
        now = time.monotonic()
        if self.last_rx is None:
            if not hasattr(self, "_warned") or now - self._warned > self.summary_s:
                print(f"{self._now_text()}  아직 /fall_status 를 받지 못했습니다 (fall_core_node가 켜져 있나요?)", flush=True)
                self._warned = now
            return
        if self.summary.due(now):
            print("\n" + self.summary.flush(self._now_text(), color=not self.plain) + "\n", flush=True)

    def draw_live(self):
        stale = (time.monotonic() - self.last_rx) if self.last_rx else 0.0
        text = render(self.msg, self.events, self._now_text(), color=not self.plain, stale_s=stale)
        if self.plain:
            print(text + "\n" + "=" * 60, flush=True)
        else:
            print("\x1b[H\x1b[J" + text, flush=True)


def main():
    rclpy.init()
    node = FallMonitor()
    live_tty = node.mode in ("live", "status") and not node.plain
    if live_tty:
        print("\x1b[?25l", end="")                       # 커서 숨김
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if live_tty:
            print("\x1b[?25h")                           # 커서 복원 (status 모드는 줄바꿈으로 상태 줄을 남김)
        elif node.mode == "summary" and node.summary.n:
            print("\n" + node.summary.flush(node._now_text(), color=not node.plain) + "\n(종료 시점까지의 요약)")
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
