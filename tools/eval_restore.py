"""Compare an original vocal with a restored version and report what changed.

Usage:
    python tools/eval_restore.py original.wav restored.wav [--json]

Metrics are chosen for what voice conversion (RVC) actually uses: its encoders
see 16 kHz mono audio, so level and pitch fidelity matter more than anything
above 8 kHz.

  gap_drop_db        median level change in quiet passages (breaths, tails).
                     Large negative values mean the restorer erased content.
  loud_drop_db       median level change in loud passages.
  pitch_off_frac     share of voiced frames whose pitch moved by > 50 cents.
  pitch_median_cents median absolute pitch change in voiced frames.
  hf_change_db       change of the 8-16 kHz band relative to 0.3-3 kHz.
  peak / clipped     peak level and number of samples at full scale.

Needs: numpy, soundfile, librosa, scipy. Run on a copy, never on your only file.
"""
import argparse
import json

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import correlate


def load_mono(path):
    audio, rate = sf.read(path, dtype="float32", always_2d=True)
    return audio.mean(axis=1), rate


def match_length(a, b):
    n = min(len(a), len(b))
    return a[:n], b[:n]


def frame_db(x, frame=2205):
    n = len(x) // frame * frame
    rms = np.sqrt((x[:n].reshape(-1, frame) ** 2).mean(axis=1))
    return 20 * np.log10(rms + 1e-9)


def band_ratio_db(x, rate):
    spec = np.abs(librosa.stft(x, n_fft=2048, hop_length=512)) ** 2
    freqs = librosa.fft_frequencies(sr=rate, n_fft=2048)
    mid = spec[(freqs > 300) & (freqs < 3000)].sum(axis=0)
    high = spec[(freqs > 8000) & (freqs < 16000)].sum(axis=0)
    ratio = 10 * np.log10(high / (mid + 1e-12) + 1e-12)
    level = 10 * np.log10(mid + 1e-12)
    return ratio, level


def pitch_stats(orig, rest, rate):
    seg = slice(0, len(orig))
    kw = dict(fmin=70, fmax=1100, sr=rate, frame_length=4096, hop_length=512)
    f_o = librosa.yin(orig[seg], **kw)
    f_r = librosa.yin(rest[seg], **kw)
    rms = librosa.feature.rms(y=orig[seg], frame_length=2048, hop_length=512)[0]
    n = min(len(f_o), len(f_r), len(rms))
    voiced = rms[:n] > np.percentile(rms[:n], 60)
    cents = np.abs(1200 * np.log2(f_r[:n] / f_o[:n]))[voiced]
    return float(np.median(cents)), float(np.mean(cents > 50))


def evaluate(orig, rest, rate):
    orig, rest = match_length(orig, rest)
    db_o, db_r = frame_db(orig), frame_db(rest)
    gap = (db_o < -50) & (db_o > -80)
    loud = db_o > -30
    ratio_o, level_o = band_ratio_db(orig, rate)
    ratio_r, _ = band_ratio_db(rest, rate)
    loud_bins = level_o > np.percentile(level_o, 50)
    med, off = pitch_stats(orig, rest, rate)
    return {
        "gap_frames": int(gap.sum()),
        "gap_drop_db": float(np.median(db_r[gap] - db_o[gap])) if gap.any() else None,
        "loud_drop_db": float(np.median(db_r[loud] - db_o[loud])) if loud.any() else None,
        "pitch_median_cents": med,
        "pitch_off_frac": off,
        "hf_change_db": float(np.median(ratio_r[loud_bins]) - np.median(ratio_o[loud_bins])),
        "peak": float(np.abs(rest).max()),
        "clipped": int((np.abs(rest) >= 0.999).sum()),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("original")
    parser.add_argument("restored")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    orig, rate_o = load_mono(args.original)
    rest, rate_r = load_mono(args.restored)
    if rate_o != rate_r:
        rest = librosa.resample(rest, orig_sr=rate_r, target_sr=rate_o)
    result = evaluate(orig, rest, rate_o)
    if args.json:
        print(json.dumps(result, indent=2))
        return
    for key, value in result.items():
        print(f"{key:20s} {value if not isinstance(value, float) else round(value, 3)}")


if __name__ == "__main__":
    main()
