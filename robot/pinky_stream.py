#!/usr/bin/env python3
"""핑키(로봇) 안에서 실행하는 카메라 스트리밍 서버 (MJPEG over HTTP).

로봇 카메라(pinkylib)의 영상을 JPEG로 압축해서 HTTP로 내보낸다.
PC에서는 이 주소를 그대로 영상 소스로 쓰면 된다.

  http://<로봇IP>:8000/video      연속 영상 (MJPEG)
  http://<로봇IP>:8000/snapshot   한 장 (확인용)
  http://<로봇IP>:8000/say        핑키 스피커로 말하기 (POST {"text": "..."}, 브라우저 시험은 /say?text=안녕하세요)

실행 (로봇 터미널):   python3 pinky_stream.py
종료:                 Ctrl+C   (카메라를 반드시 닫고 끝난다)

주의
  - 실행하는 동안 이 프로그램이 카메라를 점유한다. Jupyter 노트북 커널이
    카메라를 쓰고 있으면 'Device or resource busy'가 나므로 먼저 모두 종료할 것.
  - 인증이 없어서 같은 와이파이에 접속한 사람은 누구나 영상을 볼 수 있다.
  - PC에서 시험할 때는 --webcam 번호 로 pinkylib 대신 USB 웹캠을 쓸 수 있다.
  - 음성: 핑키에 스피커와 한국어 음성 합성 도구(spd-say/espeak-ng/espeak 중 하나) 또는 녹음 파일이 있어야 한다.
    녹음 파일: ~/fall_voice/ask.wav 처럼 문구 이름으로 넣으면 기계음 대신 재생 (--voice-dir 로 폴더 변경).
    없으면 /say 가 501로 답하고, PC(fall_core_node)가 노트북 스피커로 대신 말한다.
    설치 예 (인터넷 연결 필요): sudo apt install espeak-ng
    소리 없이 시험: --voice-dry-run (말할 문장을 터미널에만 출력), 음성 끄기: --no-voice
"""
import argparse
import json
import os
import queue
import shutil
import subprocess
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2


class Grabber(threading.Thread):
    """카메라에서 계속 프레임을 읽어 JPEG로 만들어 두는 스레드. 가장 최근 한 장만 보관한다."""

    def __init__(self, args):
        super().__init__(daemon=True)
        self.args = args
        self.cond = threading.Condition()
        self.idx = 0
        self.jpg = None
        self.running = True

        if args.webcam is not None:                       # PC 시험용
            self.cap = cv2.VideoCapture(args.webcam, cv2.CAP_V4L2)
            if not self.cap.isOpened():
                raise RuntimeError(f"웹캠 {args.webcam}번을 열 수 없습니다")
            self.read = lambda: self.cap.read()[1]
            self.close = self.cap.release
        else:                                             # 실제 핑키
            from pinkylib import Camera
            self.cam = Camera()
            self.cam.start()
            self.read = self.cam.get_frame                # 180도 회전은 라이브러리가 이미 처리함
            self.close = self.cam.close

    def run(self):
        interval = 1.0 / self.args.fps
        quality = [cv2.IMWRITE_JPEG_QUALITY, self.args.quality]
        while self.running:
            t0 = time.time()
            frame = self.read()
            if frame is not None:
                if self.args.swap_rb:                     # 색이 푸르게 보일 때만 사용
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                ok, buf = cv2.imencode(".jpg", frame, quality)
                if ok:
                    with self.cond:
                        self.jpg = buf.tobytes()
                        self.idx += 1
                        self.cond.notify_all()
            wait = interval - (time.time() - t0)
            if wait > 0:
                time.sleep(wait)

    def wait_new(self, last_idx, timeout=3.0):
        with self.cond:
            self.cond.wait_for(lambda: self.idx != last_idx, timeout)
            return self.idx, self.jpg

    def stop(self):
        self.running = False
        self.join(timeout=2)
        self.close()


class Speaker:
    """핑키 스피커로 말하기. 한 문장씩 차례로 말한다 (문장이 겹치지 않음).

    1) voice_dir 에 <문구 이름>.wav (예: ask.wav)가 있으면 그 녹음을 재생
    2) 없으면 설치된 한국어 음성 합성 도구로 말함 (spd-say > espeak-ng > espeak). PC가 보낸 목소리 설정 적용
    """

    def __init__(self, enabled=True, dry_run=False, voice_dir="~/fall_voice"):
        self.voice_dir = os.path.expanduser(voice_dir) if voice_dir else ""
        self.tts = next((exe for exe in ("spd-say", "espeak-ng", "espeak") if shutil.which(exe)), None)
        self.player = next((exe for exe in ("paplay", "aplay") if shutil.which(exe)), None)
        has_audio = bool(self.voice_dir and self.player and os.path.isdir(self.voice_dir))
        self.enabled = enabled and (self.tts is not None or has_audio or dry_run)
        self.dry_run = dry_run
        self.q = queue.Queue()
        threading.Thread(target=self._worker, daemon=True).start()

    def available(self):
        return self.enabled

    def describe(self):
        parts = []
        if self.tts:
            parts.append(self.tts)
        if self.voice_dir and os.path.isdir(self.voice_dir):
            parts.append(f"녹음 폴더 {self.voice_dir}")
        return ", ".join(parts) or "(dry-run)"

    def say(self, text, key=None, style=None):
        self.q.put((text, key, style or {}))

    def _command(self, text, key, style):
        if key and self.voice_dir and self.player:
            wav = os.path.join(self.voice_dir, f"{key}.wav")
            if os.path.isfile(wav):
                return [self.player, wav]
        if self.tts is None:
            return None
        rate, pitch, vol = int(style.get("rate", -20)), int(style.get("pitch", 0)), int(style.get("volume", 0))
        name = style.get("voice_name") or ""
        if self.tts == "spd-say":
            cmd = ["spd-say", "-o", "espeak-ng", "-l", "ko", "-r", str(rate), "-p", str(pitch), "-i", str(vol)]
            return cmd + (["-y", name] if name else []) + ["-w", text]
        variant = name.split("+", 1)[1] if "+" in name else ""
        return [self.tts, "-v", "ko" + (f"+{variant}" if variant else ""), "-s", str(int(175 * (1 + rate / 200))),
                "-p", str(max(0, min(99, 50 + pitch // 2))), "-a", str(max(0, min(200, 100 + vol))), text]

    def _worker(self):
        while True:
            text, key, style = self.q.get()
            cmd = self._command(text, key, style)
            how = "녹음 재생" if cmd and cmd[0] in ("paplay", "aplay") else "음성 합성"
            print(f"[음성{' dry-run' if self.dry_run else ''} · {how}] {text}", flush=True)
            if not self.dry_run and cmd:
                try:
                    subprocess.run(cmd, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception as e:
                    print(f"[음성 실패] {e}", flush=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):          # 요청마다 로그를 찍지 않음
        pass

    def _reply(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _say(self, text, key=None, style=None):
        sp = self.server.speaker
        if not text.strip():
            return self._reply(400, {"ok": False, "reason": "빈 문장"})
        if not sp.available():
            return self._reply(501, {"ok": False, "reason": "핑키에 음성 출력 도구가 없거나 음성이 꺼져 있음"})
        sp.say(text, key, style)
        return self._reply(200, {"ok": True, "engine": sp.describe()})

    def do_POST(self):
        if not self.path.startswith("/say"):
            return self._reply(404, {"ok": False})
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n).decode("utf-8", "replace")
        try:
            body = json.loads(raw)
            self._say(body.get("text", ""), body.get("key"), body.get("style"))
        except (json.JSONDecodeError, AttributeError):
            self._say(raw)

    def do_GET(self):
        if self.path.startswith("/say"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            return self._say(q.get("text", [""])[0])
        grabber = self.server.grabber
        if self.path.startswith("/video"):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            last = -1
            try:
                while True:
                    last, jpg = grabber.wait_new(last)
                    if jpg is None:
                        continue
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                     b"Content-Length: " + str(len(jpg)).encode() + b"\r\n\r\n")
                    self.wfile.write(jpg)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass                    # 보던 쪽이 연결을 끊음
        elif self.path.startswith("/snapshot"):
            _, jpg = grabber.wait_new(-1)
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(jpg)))
            self.end_headers()
            self.wfile.write(jpg)
        else:
            body = b"pinky_stream: /video (MJPEG), /snapshot (JPEG)\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="0.0.0.0",
                   help="접속을 받을 주소. 로봇에서는 기본값(모두 허용), PC 시험은 127.0.0.1(자기 자신만)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--fps", type=float, default=15.0, help="내보내는 초당 프레임 수 (WiFi 부담 조절)")
    p.add_argument("--quality", type=int, default=70, help="JPEG 품질 1~100 (낮을수록 가벼움)")
    p.add_argument("--swap-rb", action="store_true", help="색이 푸르게 보이면 켠다 (RGB<->BGR)")
    p.add_argument("--webcam", type=int, default=None, help="시험용: pinkylib 대신 USB 웹캠 번호")
    p.add_argument("--no-voice", action="store_true", help="음성(/say) 끄기")
    p.add_argument("--voice-dry-run", action="store_true", help="소리 없이 말할 문장만 터미널에 출력")
    p.add_argument("--voice-dir", default="~/fall_voice", help="녹음 파일 폴더 (ask.wav 등이 있으면 기계음 대신 재생)")
    args = p.parse_args()

    grabber = Grabber(args)
    grabber.start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.grabber = grabber
    server.speaker = Speaker(enabled=not args.no_voice, dry_run=args.voice_dry_run, voice_dir=args.voice_dir)
    print("음성(/say):", ("켜짐 - " + server.speaker.describe()) if server.speaker.available()
          else "사용할 수 없음 (음성 도구 없음 또는 --no-voice). PC 스피커가 대신 말합니다.")
    server.daemon_threads = True
    print(f"스트리밍 시작: http://{args.host}:{args.port}/video  ({args.fps} fps, JPEG {args.quality})")
    if args.host == "0.0.0.0":
        print("주의: 인증이 없어 같은 네트워크의 누구나 영상을 볼 수 있습니다.")
    print("종료: Ctrl+C")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        grabber.stop()                  # 카메라를 반드시 닫는다
        print("종료, 카메라 해제됨")


if __name__ == "__main__":
    main()
