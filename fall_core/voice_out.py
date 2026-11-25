"""핑키(또는 PC) 스피커로 말하기. ROS 없이 쓰는 입출력 도우미.

target
  pinky : 핑키의 /say 주소로 문장을 보냄 (robot/pinky_stream.py 가 핑키 스피커로 말함).
          핑키가 말할 수 없거나 연결이 안 되면 자동으로 PC 스피커로 대신 말함.
  pc    : PC(노트북) 스피커로만 말함
  both  : 둘 다
  off   : 말하지 않음 (터미널 토픽에만 문장이 남음)

목소리 바꾸기 (config/thresholds.yaml 의 voice_style)
  voice_name : 목소리 종류 (예: "Korean+Alicia"). 목록은 python3 tools/voice_preview.py --list
  rate       : 빠르기 (-100 느림 ~ 100 빠름)
  pitch      : 높이 (-100 낮음 ~ 100 높음)
  volume     : 크기 (-100 ~ 100)
  audio_dir  : 녹음 파일 폴더. <문구 이름>.wav (ask.wav, announce.wav ...)가 있으면 기계음 대신 그 녹음을 재생
               녹음은 python3 tools/voice_preview.py --record ask

말하는 중에도 판정이 멈추지 않도록 별도 스레드에서 한 문장씩 차례로 말한다 (문장이 겹치지 않음).
"""
import json
import os
import queue
import shutil
import subprocess
import threading
import urllib.request

DEFAULT_STYLE = {"voice_name": "", "rate": -20, "pitch": 0, "volume": 0, "audio_dir": ""}


def build_tts_command(text, style=None, which=shutil.which):
    """설치된 한국어 음성 합성 도구로 말하는 명령. 없으면 None. (spd-say > espeak-ng > espeak 순서)"""
    st = {**DEFAULT_STYLE, **(style or {})}
    rate, pitch, vol, name = int(st["rate"]), int(st["pitch"]), int(st["volume"]), st["voice_name"] or ""
    if which("spd-say"):
        cmd = ["spd-say", "-o", "espeak-ng", "-l", "ko", "-r", str(rate), "-p", str(pitch), "-i", str(vol)]
        if name:
            cmd += ["-y", name]
        return cmd + ["-w", text]
    for exe in ("espeak-ng", "espeak"):
        if which(exe):
            speed = int(175 * (1 + rate / 200))                       # espeak: 분당 단어 수
            p = max(0, min(99, 50 + pitch // 2))
            amp = max(0, min(200, 100 + vol))
            variant = name.split("+", 1)[1] if "+" in name else ""     # "Korean+Alicia" -> "ko+Alicia"
            return [exe, "-v", "ko" + (f"+{variant}" if variant else ""), "-s", str(speed),
                    "-p", str(p), "-a", str(amp), text]
    return None


def choose_tts(which=shutil.which):
    """사용할 음성 합성 명령의 기본형 (도구가 없으면 None)."""
    return build_tts_command("", None, which)


def find_audio(audio_dir, key):
    """녹음 파일 <audio_dir>/<key>.wav 가 있으면 그 경로."""
    if not audio_dir or not key:
        return None
    path = os.path.join(os.path.expanduser(audio_dir), f"{key}.wav")
    return path if os.path.isfile(path) else None


def local_say(text, style=None, key=None, which=shutil.which, run=subprocess.run, dry_run=False):
    """이 컴퓨터 스피커로 말함. 녹음 파일이 있으면 재생. 쓴 방법을 돌려주고, 방법이 없으면 None."""
    audio = find_audio((style or {}).get("audio_dir", ""), key)
    if audio:
        player = next((p for p in ("paplay", "aplay") if which(p)), None)
        if player:
            if dry_run:
                return f"dry-run:audio:{os.path.basename(audio)}"
            run([player, audio], timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"audio:{os.path.basename(audio)}"
    cmd = build_tts_command(text, style, which)
    if cmd is None:
        return None
    if dry_run:
        return f"dry-run:{cmd[0]}"
    run(cmd, timeout=60, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return cmd[0]


class VoiceOut:
    def __init__(self, target="pinky", robot_url="http://192.168.4.1:8000/say", log=print, style=None,
                 poster=None, pc_sayer=None, sync=False, timeout=3.0):
        assert target in ("pinky", "pc", "both", "off"), target
        self.target, self.robot_url, self.log, self.timeout = target, robot_url, log, timeout
        self.style = {**DEFAULT_STYLE, **(style or {})}
        self.poster = poster or self._post
        self.pc_sayer = pc_sayer or (lambda text, key=None: local_say(text, self.style, key))
        self.sync = sync
        if not sync and target != "off":
            self.q = queue.Queue()
            threading.Thread(target=self._worker, daemon=True).start()

    def say(self, text, key=None):
        """문장을 말하도록 요청 (기본은 기다리지 않음). key = 문구 이름 (녹음 파일 ask.wav 등을 찾을 때 씀).
        sync=True면 바로 말하고 쓴 출력 목록을 돌려줌."""
        if self.target == "off" or not text:
            return []
        if self.sync:
            return self._do(text, key)
        self.q.put((text, key))
        return None

    def _worker(self):
        while True:
            self._do(*self.q.get())

    def _do(self, text, key=None):
        used, pinky_ok = [], False
        if self.target in ("pinky", "both"):
            pinky_ok = self.poster(text, key)
            if pinky_ok:
                used.append("pinky")
        if self.target in ("pc", "both") or (self.target == "pinky" and not pinky_ok):
            if self.pc_sayer(text, key):
                used.append("pc")
        where = {"pinky": "핑키 스피커", "pc": "PC 스피커"}
        self.log(f"음성 출력: {', '.join(where[u] for u in used) or '실패 (스피커·음성 도구 없음)'} — {text}")
        return used

    def _post(self, text, key=None):
        body = {"text": text, "key": key, "style": {k: v for k, v in self.style.items() if k != "audio_dir"}}
        try:
            req = urllib.request.Request(self.robot_url, data=json.dumps(body).encode("utf-8"),
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status == 200
        except Exception:
            return False
