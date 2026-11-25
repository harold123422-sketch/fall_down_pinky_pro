#!/usr/bin/env python3
"""핑키 목소리 미리 듣기·바꾸기·녹음 (PC에서 실행).

  python3 tools/voice_preview.py --list                         한국어 목소리 종류 목록
  python3 tools/voice_preview.py --all                          설정된 문구(thresholds.yaml 의 voice)를 차례로 들어 보기
  python3 tools/voice_preview.py --say "안녕하세요"              아무 문장이나 들어 보기
  python3 tools/voice_preview.py --all --voice-name "Korean+Alicia" --rate 0 --pitch 30
                                                                설정을 바꾸기 전에 다른 목소리로 들어 보기
  python3 tools/voice_preview.py --record ask                   'ask' 문구를 내 목소리로 녹음 (~/fall_voice/ask.wav)
  python3 tools/voice_preview.py --record-all                   모든 문구를 차례로 녹음
  python3 tools/voice_preview.py --all --to pinky               핑키 스피커로 들어 보기 (pinky_stream.py가 켜져 있어야 함)

마음에 드는 목소리를 찾으면 config/thresholds.yaml 의 voice_style 에 적으면 됩니다.
녹음 파일이 있으면 기계음 대신 녹음이 재생됩니다. 핑키에서도 쓰려면: scp -r ~/fall_voice pinky@192.168.4.1:~/
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fall_core import load_thresholds  # noqa: E402
from fall_core.voice_out import VoiceOut  # noqa: E402


def list_voices():
    try:
        out = subprocess.run(["spd-say", "-o", "espeak-ng", "-L"], capture_output=True, text=True, timeout=10).stdout
    except FileNotFoundError:
        print("spd-say가 없습니다. espeak-ng 기본 한국어 목소리만 쓸 수 있습니다.")
        return
    names = [ln.split()[0] for ln in out.splitlines() if " ko " in f" {ln} " and ln.strip()]
    print("한국어 목소리 (voice_style.voice_name 에 그대로 적으세요):")
    for n in names:
        print("  ", n)
    print(f"총 {len(names)}개. 예: --say \"응급상황으로 판단됩니다\" --voice-name \"{names[1] if len(names) > 1 else 'Korean'}\"")


def record(key, text, audio_dir, seconds):
    folder = Path(os.path.expanduser(audio_dir))
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{key}.wav"
    print(f"\n[{key}] 아래 문장을 읽어 주세요 ({seconds}초 녹음):\n    \"{text}\"")
    for n in (3, 2, 1):
        print(f"  {n}...", flush=True)
        time.sleep(1)
    print("  ● 녹음 중", flush=True)
    subprocess.run(["arecord", "-q", "-f", "cd", "-d", str(seconds), str(path)], check=True)
    print(f"  저장: {path}  (다시 들어 보는 중)")
    subprocess.run(["aplay", "-q", str(path)])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true", help="한국어 목소리 종류 목록")
    ap.add_argument("--all", action="store_true", help="설정된 문구를 차례로 들어 보기")
    ap.add_argument("--say", help="이 문장을 들어 보기")
    ap.add_argument("--record", metavar="KEY", help="이 문구를 내 목소리로 녹음 (ask, announce, responded, reported, recovered)")
    ap.add_argument("--record-all", action="store_true", help="모든 문구를 차례로 녹음")
    ap.add_argument("--seconds", type=int, default=6, help="녹음 길이(초)")
    ap.add_argument("--voice-name", help="목소리 종류 (예: Korean+Alicia)")
    ap.add_argument("--rate", type=int, help="빠르기 -100~100")
    ap.add_argument("--pitch", type=int, help="높이 -100~100")
    ap.add_argument("--volume", type=int, help="크기 -100~100")
    ap.add_argument("--no-audio-files", action="store_true", help="녹음 파일이 있어도 기계음으로 들어 보기")
    ap.add_argument("--to", default="pc", choices=["pc", "pinky", "both"], help="어디로 말할지 (기본 pc)")
    ap.add_argument("--robot-say-url", default="http://192.168.4.1:8000/say")
    a = ap.parse_args()

    cfg = load_thresholds()
    style = dict(cfg.get("voice_style", {}))
    for k in ("voice_name", "rate", "pitch", "volume"):
        if getattr(a, k) is not None:
            style[k] = getattr(a, k)
    if a.no_audio_files:
        style["audio_dir"] = ""
    phrases = {k: v.format(delay=int(cfg["response"]["report_delay_s"])) for k, v in cfg["voice"].items() if v}

    if a.list:
        list_voices()
    if a.record or a.record_all:
        audio_dir = cfg.get("voice_style", {}).get("audio_dir") or "~/fall_voice"
        keys = list(phrases) if a.record_all else [a.record]
        for k in keys:
            if k not in phrases:
                sys.exit(f"'{k}' 문구가 없습니다. 가능한 이름: {', '.join(phrases)}")
            record(k, phrases[k], audio_dir, a.seconds)
        print(f"\n완료. 핑키에서도 쓰려면: scp -r {audio_dir} pinky@192.168.4.1:~/")
    if a.say or a.all:
        print(f"목소리 설정: {style}")
        vo = VoiceOut(a.to, a.robot_say_url, log=print, style=style, sync=True)
        if a.say:
            vo.say(a.say)
        if a.all:
            for k, text in phrases.items():
                print(f"[{k}]")
                vo.say(text, key=k)
    if not (a.list or a.say or a.all or a.record or a.record_all):
        ap.print_help()


if __name__ == "__main__":
    main()
