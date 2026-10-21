"""Pre-render ChessOS speech + sound effects into WAV files.

Speech uses the Windows SAPI voice (default: Zira) because the R36S has no
TTS engine. Each line from app.content.spoken_lines() becomes one clip and is
listed in assets/voice/index.json  ({"text": "file.wav"}).
"""
import array
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "device", "chessos"))
from app.content import spoken_lines  # noqa: E402

VOICE_DIR = os.path.join(ROOT, "device", "chessos", "assets", "voice")
SFX_DIR = os.path.join(ROOT, "device", "chessos", "assets", "sfx")
RATE = 22050
VOICE = os.environ.get("CHESSOS_VOICE", "Microsoft Zira Desktop")

PS = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try { $s.SelectVoice('%VOICE%') } catch { }
$s.Rate = 0
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(22050, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
Get-Content -Encoding UTF8 '%LIST%' | ForEach-Object {
  $p = $_.Split("`t", 2)
  $s.SetOutputToWaveFile($p[0], $fmt)
  $s.Speak($p[1])
}
$s.SetOutputToNull()
"""


def say_text(line):
    """How a line should be pronounced (squares like 'e4' read as letters)."""
    if len(line) == 2 and line[0] in "abcdefgh" and line[1] in "12345678":
        return line[0].upper() + " " + line[1]
    return line.replace("ChessOS", "Chess O S")


def trim(path):
    with wave.open(path, "rb") as w:
        n = w.getnframes()
        data = array.array("h", w.readframes(n))
    th = 300
    start = next((i for i, v in enumerate(data) if abs(v) > th), 0)
    end = len(data) - next((i for i, v in enumerate(reversed(data)) if abs(v) > th), 0)
    start = max(0, start - int(RATE * 0.02))
    end = min(len(data), end + int(RATE * 0.06))
    data = data[start:end]
    peak = max(1, max(abs(v) for v in data)) if data else 1
    g = min(3.0, 26000.0 / peak)
    data = array.array("h", (int(max(-32767, min(32767, v * g))) for v in data))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())


def build_voice():
    os.makedirs(VOICE_DIR, exist_ok=True)
    index = {}
    todo = []
    for line in spoken_lines():
        name = hashlib.md5(line.encode("utf-8")).hexdigest()[:10] + ".wav"
        index[line] = name
        path = os.path.join(VOICE_DIR, name)
        if not os.path.exists(path):
            todo.append((path, say_text(line)))
    if todo:
        lst = os.path.join(ROOT, "build", "voice_list.txt")
        with open(lst, "w", encoding="utf-8") as f:
            for path, text in todo:
                f.write(path + "\t" + text + "\n")
        ps1 = os.path.join(ROOT, "build", "voice.ps1")
        with open(ps1, "w", encoding="utf-8-sig") as f:
            f.write(PS.replace("%VOICE%", VOICE).replace("%LIST%", lst))
        subprocess.check_call(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1])
        for path, _ in todo:
            trim(path)
    # drop stale clips
    keep = set(index.values())
    for f in os.listdir(VOICE_DIR):
        if f.endswith(".wav") and f not in keep:
            os.remove(os.path.join(VOICE_DIR, f))
    with open(os.path.join(VOICE_DIR, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, indent=0, ensure_ascii=False)
    print("voice clips:", len(index), "new:", len(todo))


# ---- sound effects -----------------------------------------------------------
def env(i, n, a=0.005, r=0.25):
    t = i / float(RATE)
    dur = n / float(RATE)
    if t < a:
        return t / a
    return max(0.0, 1.0 - (t - a) / max(1e-6, dur - a)) ** (1.0 / max(r, 1e-3) * 0.25 + 1)


def tone(freq, dur, vol=0.5, shape="sine", decay=6.0):
    n = int(RATE * dur)
    out = []
    for i in range(n):
        t = i / float(RATE)
        ph = 2 * math.pi * freq * t
        if shape == "sine":
            v = math.sin(ph) + 0.25 * math.sin(2 * ph)
        elif shape == "tri":
            v = 2 * abs(2 * ((freq * t) % 1) - 1) - 1
        else:
            v = 1.0 if math.sin(ph) > 0 else -1.0
        a = min(1.0, t / 0.004) * math.exp(-decay * t)
        out.append(v * a * vol)
    return out


def mix(*parts):
    """parts: (offset_seconds, samples)"""
    n = max(int(o * RATE) + len(s) for o, s in parts)
    buf = [0.0] * n
    for o, s in parts:
        k = int(o * RATE)
        for i, v in enumerate(s):
            buf[k + i] += v
    return buf


def noise(dur, vol=0.4, decay=40.0, lp=0.5):
    rnd = random.Random(7)
    n = int(RATE * dur)
    out, last = [], 0.0
    for i in range(n):
        t = i / float(RATE)
        last = last + lp * (rnd.uniform(-1, 1) - last)
        out.append(last * vol * math.exp(-decay * t))
    return out


def write_wav(name, samples):
    os.makedirs(SFX_DIR, exist_ok=True)
    peak = max(1e-6, max(abs(v) for v in samples))
    g = 0.8 / peak if peak > 0.8 else 1.0
    data = array.array("h", (int(max(-1, min(1, v * g)) * 32000) for v in samples))
    with wave.open(os.path.join(SFX_DIR, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(data.tobytes())


def build_sfx():
    write_wav("move", mix((0, noise(0.07, 0.9, 60, 0.35)), (0, tone(180, 0.07, 0.4, decay=50))))
    write_wav("capture", mix((0, noise(0.12, 1.0, 35, 0.5)), (0, tone(140, 0.12, 0.5, decay=30)),
                             (0.035, noise(0.08, 0.6, 50, 0.4))))
    write_wav("select", tone(880, 0.06, 0.35, "tri", decay=45))
    write_wav("nav", tone(620, 0.04, 0.25, "tri", decay=70))
    write_wav("correct", mix((0, tone(784, 0.25, 0.4, decay=9)), (0.09, tone(1175, 0.35, 0.4, decay=8))))
    write_wav("wrong", mix((0, tone(220, 0.22, 0.35, "tri", decay=10)), (0.1, tone(185, 0.3, 0.35, "tri", decay=9))))
    write_wav("star", mix((0, tone(1319, 0.2, 0.3, decay=14)), (0.05, tone(1760, 0.25, 0.3, decay=12)),
                          (0.1, tone(2637, 0.3, 0.2, decay=12))))
    notes = [523, 659, 784, 1047]
    write_wav("complete", mix(*[(i * 0.11, tone(f, 0.5, 0.35, decay=5)) for i, f in enumerate(notes)] +
                              [(0.44, tone(1319, 0.8, 0.3, decay=3)), (0.44, tone(784, 0.8, 0.25, decay=3))]))
    write_wav("streak", mix(*[(i * 0.05, tone(400 + i * 90, 0.15, 0.25, "tri", decay=14)) for i in range(8)]))
    write_wav("heart", mix((0, tone(330, 0.15, 0.4, "tri", decay=18)), (0.12, tone(247, 0.25, 0.4, "tri", decay=10))))
    print("sfx built")


if __name__ == "__main__":
    build_sfx()
    build_voice()
