#!/usr/bin/env python3
"""ChessOS TTS benchmark for the R36S (Python 3.7, no extra installs).

Engines (in this order, heaviest last so a crash keeps earlier results):
  espeak-ng (system), Piper (3 voices), Supertonic (2/4/8 steps)
For each: load time, synthesis time, real-time factor (RTF = synth time /
audio length; < 1.0 is faster than speech), peak memory.
Writes results.txt + out/*.wav next to this file and plays one sample per
engine through the speaker.
"""
import json
import os
import platform
import resource
import shutil
import subprocess
import sys
import time
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
RESULTS = os.path.join(HERE, "results.txt")
TTY = "/dev/tty1" if os.path.exists("/dev/tty1") and os.access("/dev/tty1", os.W_OK) else None
PLAY = os.environ.get("BENCH_PLAY", "1") == "1"

SENTENCES = [
    ("move", "Knight takes e5, check."),
    ("feedback", "Excellent! That fork wins the queen."),
    ("coach", "White is pushing on the kingside, but the bishop on b7 is watching the long diagonal. "
              "Careful with that pawn on g4."),
]
SAMPLE = "feedback"  # the one played through the speaker


def say(msg):
    line = msg + "\n"
    sys.stdout.write(line)
    sys.stdout.flush()
    if TTY:
        try:
            with open(TTY, "w") as t:
                t.write(line)
        except OSError:
            pass


def log(msg):
    with open(RESULTS, "a") as f:
        f.write(msg + "\n")
    try:
        os.sync()
    except AttributeError:
        pass
    say(msg)


def wav_seconds(path):
    try:
        with wave.open(path, "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 0.0


def peak_mb_self():
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmHWM"):
                return int(line.split()[1]) / 1024.0
    return 0.0


def peak_mb_children():
    return resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024.0


def play(path):
    if PLAY and shutil.which("aplay") and os.path.exists(path):
        subprocess.call(["aplay", "-q", path])


def row(engine, sid, load, synth, audio, mem):
    rtf = synth / audio if audio > 0 else 0
    log("%-26s %-9s load %6.2fs  synth %6.2fs  audio %5.2fs  RTF %5.2f  mem %5.0f MB"
        % (engine, sid, load, synth, audio, rtf, mem))


def system_info():
    log("=== ChessOS TTS benchmark  %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    log("machine %s, python %s" % (platform.machine(), platform.python_version()))
    try:
        gov = open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor").read().strip()
        cur = int(open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq").read()) // 1000
        mx = int(open("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq").read()) // 1000
        log("cpu governor %s, %d/%d MHz, %d cores" % (gov, cur, mx, os.cpu_count() or 0))
    except Exception:
        pass
    try:
        mem = dict(l.split(":", 1) for l in open("/proc/meminfo"))
        log("memory total %s, available %s" % (mem["MemTotal"].strip(), mem["MemAvailable"].strip()))
    except Exception:
        pass


# ---- espeak-ng -------------------------------------------------------------------
def bench_espeak():
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        log("espeak-ng                  not installed")
        return
    for sid, text in SENTENCES:
        out = os.path.join(OUT, "espeak_%s.wav" % sid)
        t0 = time.time()
        subprocess.call([exe, "-s", "160", "-w", out, text])
        dt = time.time() - t0
        row("espeak-ng", sid, 0, dt, wav_seconds(out), peak_mb_children())
    play(os.path.join(OUT, "espeak_%s.wav" % SAMPLE))


# ---- Piper -------------------------------------------------------------------------
def bench_piper(voice):
    pdir = os.path.join(HERE, "piper")
    exe = os.path.join(pdir, "piper")
    model = os.path.join(HERE, "voices", voice + ".onnx")
    if not (os.path.exists(exe) and os.path.exists(model)):
        log("piper %-20s missing files" % voice)
        return
    env = dict(os.environ, LD_LIBRARY_PATH=pdir + ":" + os.environ.get("LD_LIBRARY_PATH", ""))
    data = os.path.join(pdir, "espeak-ng-data")
    # 1) one process per sentence (includes model load every time)
    for sid, text in SENTENCES:
        out = os.path.join(OUT, "piper_%s_%s.wav" % (voice, sid))
        t0 = time.time()
        p = subprocess.Popen([exe, "--model", model, "--espeak_data", data, "--output_file", out, "-q"],
                             stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
        _, err = p.communicate((text + "\n").encode("utf-8"), timeout=600)
        dt = time.time() - t0
        if p.returncode != 0:
            log("piper %s failed: %s" % (voice, err.decode("utf-8", "replace")[-300:]))
            return
        row("piper " + voice, sid + "*", 0, dt, wav_seconds(out), peak_mb_children())
    # 2) one long-running process, all sentences: load time vs per-sentence time
    odir = os.path.join(OUT, "piper_batch_" + voice)
    os.makedirs(odir, exist_ok=True)
    text = "\n".join(t for _, t in SENTENCES) + "\n"
    t0 = time.time()
    p = subprocess.Popen([exe, "--model", model, "--espeak_data", data, "--output_dir", odir, "-q"],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
    p.communicate(text.encode("utf-8"), timeout=900)
    total = time.time() - t0
    audio = sum(wav_seconds(os.path.join(odir, f)) for f in os.listdir(odir) if f.endswith(".wav"))
    log("%-26s %-9s total %6.2fs for %5.2fs of audio  RTF %5.2f (model loaded once)"
        % ("piper " + voice, "all3", total, audio, total / audio if audio else 0))
    play(os.path.join(OUT, "piper_%s_%s.wav" % (voice, SAMPLE)))


# ---- Supertonic --------------------------------------------------------------------
def bench_supertonic(steps_list=(2, 4, 8), max_synth=120.0):
    sdir = os.path.join(HERE, "supertonic")
    sys.path.insert(0, os.path.join(HERE, "pylib"))
    sys.path.insert(0, os.path.join(sdir, "py"))
    t0 = time.time()
    try:
        import numpy as np
        import onnxruntime as ort
        import helper
    except Exception as e:
        log("supertonic import failed: %r" % e)
        return
    t_import = time.time() - t0
    log("supertonic: onnxruntime %s, numpy %s, import %.2fs" % (ort.__version__, np.__version__, t_import))

    opts = ort.SessionOptions()
    opts.intra_op_num_threads = int(os.environ.get("BENCH_THREADS", str(os.cpu_count() or 4)))
    opts.inter_op_num_threads = 1
    onnx_dir = os.path.join(sdir, "onnx")
    t0 = time.time()
    try:
        sessions = helper.load_onnx_all(onnx_dir, opts, ["CPUExecutionProvider"])
        tts = helper.TextToSpeech(helper.load_cfgs(onnx_dir), helper.load_text_processor(onnx_dir), *sessions)
        style = helper.load_voice_style([os.path.join(sdir, "voice_styles", "M1.json")])
    except Exception as e:
        log("supertonic load failed: %r" % e)
        return
    load = time.time() - t0
    log("supertonic load %.2fs, memory after load %.0f MB" % (load, peak_mb_self()))
    sr = tts.sample_rate
    for steps in steps_list:
        slow = False
        for sid, text in SENTENCES:
            out = os.path.join(OUT, "supertonic_s%d_%s.wav" % (steps, sid))
            t0 = time.time()
            try:
                wav, dur = tts(text, "en", style, steps)
            except TypeError:
                wav, dur = tts(text, style, steps)  # older helper signature
            dt = time.time() - t0
            audio = wav[0, :int(sr * float(dur[0]))]
            pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
            with wave.open(out, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(sr)
                w.writeframes(pcm)
            row("supertonic %d steps" % steps, sid, load if (steps == steps_list[0] and sid == "move") else 0,
                dt, wav_seconds(out), peak_mb_self())
            if dt > max_synth:
                slow = True
                break
        play(os.path.join(OUT, "supertonic_s%d_%s.wav" % (steps, SAMPLE)))
        if slow:
            log("supertonic: stopping, %d steps took over %ds" % (steps, max_synth))
            break


def main():
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[1:] or ["espeak", "piper", "supertonic"]
    say("\033c")
    say("  ChessOS TTS benchmark - this takes a few minutes. You will hear samples.")
    system_info()
    if "espeak" in only:
        bench_espeak()
    if "piper" in only:
        for v in ("en_US-lessac-low", "en_US-amy-low", "en_US-lessac-medium"):
            bench_piper(v)
    if "supertonic" in only:
        bench_supertonic()
    log("=== done")
    say("  Done. Results saved in ports/ttsbench/results.txt")


if __name__ == "__main__":
    main()
