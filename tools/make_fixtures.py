"""Make small, deterministic test audio for the restoration guard.

Writes into the folder given (default: tools/fixtures):
  sung_note_tail.wav  a vibrato note with a decaying reverb-like tail
  breath_gap.wav      a note, a quiet breath-noise gap, another note
  excerpt.wav         10 s cut from --source (optional)

Usage: python tools/make_fixtures.py [out_dir] [--source file.wav --start 60]
"""
import argparse
import pathlib

import numpy as np
import soundfile as sf

RATE = 44100


def note(freq, seconds, rng):
    t = np.arange(int(seconds * RATE)) / RATE
    vibrato = 1 + 0.006 * np.sin(2 * np.pi * 5.5 * t)
    phase = 2 * np.pi * np.cumsum(freq * vibrato) / RATE
    wave = sum(np.sin(k * phase) / k for k in range(1, 8))
    env = np.minimum(1, t / 0.05) * np.minimum(1, (seconds - t) / 0.08)
    return (0.3 * wave * env / 2).astype(np.float32)


def tail(seconds, rng, start_db=-35):
    n = int(seconds * RATE)
    decay = np.exp(-np.arange(n) / (0.5 * RATE))
    return (rng.standard_normal(n) * 10 ** (start_db / 20) * decay).astype(np.float32)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir", nargs="?", default="tools/fixtures")
    parser.add_argument("--source")
    parser.add_argument("--start", type=float, default=60.0)
    args = parser.parse_args()
    out = pathlib.Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    a = note(330, 2.0, rng)
    sf.write(out / "sung_note_tail.wav", np.concatenate([a, tail(1.5, rng)]), RATE, subtype="PCM_24")
    breath = (rng.standard_normal(int(0.8 * RATE)) * 10 ** (-52 / 20)).astype(np.float32)
    sf.write(out / "breath_gap.wav", np.concatenate([a, breath, note(294, 2.0, rng)]), RATE, subtype="PCM_24")
    if args.source:
        data, rate = sf.read(args.source, dtype="float32", always_2d=True)
        s = int(args.start * rate)
        sf.write(out / "excerpt.wav", data[s : s + 10 * rate], rate, subtype="PCM_24")
    print("wrote", sorted(p.name for p in out.iterdir()))


if __name__ == "__main__":
    main()
