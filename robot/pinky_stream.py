#!/usr/bin/env python3
"""핑키(로봇) 안에서 실행하는 카메라 스트리밍 서버 (MJPEG over HTTP).

로봇 카메라(pinkylib)의 영상을 JPEG로 압축해서 HTTP로 내보낸다.
PC에서는 이 주소를 그대로 영상 소스로 쓰면 된다.

  http://<로봇IP>:8000/video      연속 영상 (MJPEG)
  http://<로봇IP>:8000/snapshot   한 장 (확인용)

실행 (로봇 터미널):   python3 pinky_stream.py
종료:                 Ctrl+C   (카메라를 반드시 닫고 끝난다)

주의
  - 실행하는 동안 이 프로그램이 카메라를 점유한다. Jupyter 노트북 커널이
    카메라를 쓰고 있으면 'Device or resource busy'가 나므로 먼저 모두 종료할 것.
  - 인증이 없어서 같은 와이파이에 접속한 사람은 누구나 영상을 볼 수 있다.
  - PC에서 시험할 때는 --webcam 번호 로 pinkylib 대신 USB 웹캠을 쓸 수 있다.
"""
import argparse
import threading
import time
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


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):          # 요청마다 로그를 찍지 않음
        pass

    def do_GET(self):
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
    args = p.parse_args()

    grabber = Grabber(args)
    grabber.start()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.grabber = grabber
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
