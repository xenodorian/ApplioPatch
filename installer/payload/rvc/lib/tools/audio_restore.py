"""Optional vocal restoration before conversion (VoiceFixer, Resemble Enhance).

Both restorers depend on packages that conflict with Applio's pinned stack
(different numpy/torch/deepspeed requirements), so each one runs in its own
sidecar virtual environment under <Applio>/assets/audio-restore. The sidecar
is created on first use from exact version pins and reused afterwards.
Restoration runs only on the local machine; no audio is uploaded.

Model weights are fetched by the packages themselves on first run:
VoiceFixer from Zenodo, Resemble Enhance from Hugging Face.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import shutil
from collections import deque
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

SIDECAR_VERSION = "2"
WORKER = Path(__file__).with_name("audio_restore_worker.py")
APPLIO_ROOT = Path(__file__).resolve().parents[3]
TIMEOUT_SECONDS = 60 * 60
INSTALL_TIMEOUT_SECONDS = 2 * 60 * 60
UV_VERSION = "0.9.5"

# Exact pins taken from a working resolve on Python 3.11. NumPy stays below
# 2.4 because Resemble Enhance converts one-element arrays with float(), which
# NumPy 2.4 rejects. Transitive dependencies are frozen to a date with uv's
# --exclude-newer so a fresh install months later resolves to the same
# versions.
RESOLVE_DATE = "2026-11-01"
CACHE_LIMIT = 24

SPECS = {
    "voicefixer": {
        "python": "3.11",
        "packages": [
            "voicefixer==0.1.3",
            "torch==2.15.0",
            "numpy==2.3.5",
            "scipy==1.17.1",
            "librosa==0.11.0",
            "soundfile==0.14.0",
        ],
        "nodeps": [],
    },
    "resemble-enhance": {
        "python": "3.11",
        # The package declares deepspeed, gradio and other training or demo
        # dependencies that inference never uses. It is installed with
        # --no-deps and only the runtime packages are listed here; the worker
        # supplies a stand-in for the unused deepspeed import.
        "packages": [
            "torch==2.15.0",
            "torchaudio==2.11.1",
            "numpy==2.3.5",
            "librosa==0.11.0",
            "soundfile==0.14.0",
            "omegaconf==2.4.0",
            "scipy",
            "tqdm",
            "rich",
            "resampy",
            "pandas",
            "tabulate",
            "matplotlib",
        ],
        "nodeps": [
            "resemble-enhance @ git+https://github.com/resemble-ai/resemble-enhance.git@8e978149bfe8abab3eb77d965d579a111afdb0ff",
        ],
    },
}

MODES = ("off", "voicefixer", "resemble-enhance")


def _root():
    return APPLIO_ROOT / "assets" / "audio-restore"


def _env_dir(backend):
    return _root() / f"{backend}-v{SIDECAR_VERSION}"


def _venv_python(env):
    if os.name == "nt":
        return env / "Scripts" / "python.exe"
    return env / "bin" / "python"


def _run(command, env=None, timeout=TIMEOUT_SECONDS, label="Audio restoration"):
    """Run a command, echo its output to the console, keep the tail for errors."""
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        env=env,
    )
    timer = threading.Timer(timeout, process.kill)
    timer.start()
    tail = deque(maxlen=15)
    try:
        for line in process.stdout:
            line = line.rstrip()
            if line:
                tail.append(line)
                print(f"[{label}] {line}", flush=True)
        process.wait()
    finally:
        timer.cancel()
    if process.returncode != 0:
        raise RuntimeError(f"{label} failed:\n" + "\n".join(tail))


def _uv():
    """Find uv, or install it once into a small private environment."""
    found = shutil.which("uv")
    if found:
        return found
    tool_env = _root() / "uv-tool"
    python = _venv_python(tool_env)
    uv = python.parent / ("uv.exe" if os.name == "nt" else "uv")
    if uv.exists():
        return str(uv)
    _root().mkdir(parents=True, exist_ok=True)
    print("Preparing the installer tool (first use only)...", flush=True)
    if tool_env.exists():
        shutil.rmtree(tool_env)
    _run([sys.executable, "-m", "venv", str(tool_env)], label="Setup")
    _run(
        [str(python), "-m", "pip", "install", "--no-input", f"uv=={UV_VERSION}"],
        timeout=INSTALL_TIMEOUT_SECONDS,
        label="Setup",
    )
    if not uv.exists():
        raise RuntimeError(f"uv was installed but not found at {uv}")
    return str(uv)


def ensure_sidecar(backend):
    """Create or reuse the isolated environment for one restorer."""
    spec = SPECS[backend]
    env = _env_dir(backend)
    python = _venv_python(env)
    marker = env / "applio-spec.json"
    wanted = json.dumps(spec, sort_keys=True)
    if python.exists() and marker.exists() and marker.read_text() == wanted:
        return python

    uv = _uv()
    label = f"Setup {backend}"
    print(
        f"Preparing the {backend} environment (first use only, large download)...",
        flush=True,
    )
    env.parent.mkdir(parents=True, exist_ok=True)
    if env.exists():
        shutil.rmtree(env)
    _run(
        [uv, "venv", "--python", spec["python"], str(env)],
        timeout=INSTALL_TIMEOUT_SECONDS,
        label=label,
    )
    base = [uv, "pip", "install", "--python", str(python)]
    # Try the CUDA wheels that match Applio's own PyTorch first, then uv's
    # automatic choice, then the default wheels (CPU only on Windows). The
    # first one that installs wins.
    install = ["--exclude-newer", RESOLVE_DATE, *spec["packages"]]
    attempts = []
    applio_backend = _applio_torch_backend()
    if applio_backend:
        attempts.append(["--torch-backend", applio_backend])
    attempts += [["--torch-backend", "auto"], []]
    for index, extra in enumerate(attempts):
        try:
            _run(
                base + extra + install,
                timeout=INSTALL_TIMEOUT_SECONDS,
                label=label,
            )
            break
        except RuntimeError as error:
            if index == len(attempts) - 1:
                raise
            print(f"Install attempt failed, trying the next option:\n{error}", flush=True)
    if spec["nodeps"]:
        _run(
            base + ["--no-deps", *spec["nodeps"]],
            timeout=INSTALL_TIMEOUT_SECONDS,
            label=label,
        )
    marker.write_text(wanted)
    _remove_old_sidecars(backend, env)
    _report_gpu(python)
    return python


def _applio_torch_backend():
    """The uv torch backend matching Applio's own CUDA build, or None."""
    try:
        import torch

        version = torch.version.cuda
        return "cu" + version.replace(".", "") if version else None
    except Exception:
        return None


def _remove_old_sidecars(backend, current):
    """Delete environments from older sidecar versions to free disk space."""
    for old in _root().glob(f"{backend}-v*"):
        if old != current and old.is_dir():
            shutil.rmtree(old, ignore_errors=True)


def _report_gpu(python):
    """Say whether the new environment can use the GPU."""
    try:
        result = subprocess.run(
            [str(python), "-I", "-c", "import torch;print(torch.cuda.is_available())"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        usable = result.stdout.strip() == "True"
    except Exception:
        usable = False
    print(
        "Restoration environment can use the GPU."
        if usable
        else "Restoration environment is CPU only, so restoration will be slow.",
        flush=True,
    )


def _device():
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def _cache_key(data, sample_rate, mode, options):
    digest = hashlib.sha256()
    digest.update(np.ascontiguousarray(data).tobytes())
    digest.update(
        json.dumps(
            [int(sample_rate), mode, SIDECAR_VERSION, SPECS[mode], options],
            sort_keys=True,
            default=str,
        ).encode()
    )
    return digest.hexdigest()


def _cache_get(path, length):
    try:
        cached = np.load(path)
    except (OSError, ValueError):
        return None
    return cached if cached.ndim == 1 and len(cached) == length else None


def _cache_put(folder, path, restored):
    folder.mkdir(parents=True, exist_ok=True)
    # Write then rename so an interrupted job never leaves a truncated entry.
    temporary = path.with_suffix(".tmp.npy")
    np.save(temporary, restored)
    temporary.replace(path)
    entries = sorted(folder.glob("*.npy"), key=lambda entry: entry.stat().st_mtime)
    for stale in entries[:-CACHE_LIMIT]:
        stale.unlink(missing_ok=True)


def blend_restored(original, restored, blend):
    """Mix restored audio with the original.

    The restored signal is first matched to the original's RMS so the mix
    changes the character of the voice, not its loudness. Blend 1.0 returns
    the restored audio untouched and 0.0 returns the original.
    """
    blend = float(min(max(blend, 0.0), 1.0))
    if blend >= 1.0:
        return restored
    if blend <= 0.0:
        return original
    rms_original = float(np.sqrt(np.mean(np.square(original, dtype=np.float64))))
    rms_restored = float(np.sqrt(np.mean(np.square(restored, dtype=np.float64))))
    gain = rms_original / rms_restored if rms_restored > 1e-8 else 1.0
    mixed = blend * restored * gain + (1.0 - blend) * original
    return mixed.astype(np.float32)


def restore_audio(audio, sample_rate, mode="off", **options):
    """Return restored mono float32 audio at the original rate and length.

    Off is an exact bypass. The sidecar receives a 32-bit float WAV and
    returns one; the result is resampled back to the input rate, trimmed or
    padded to the input length, and mixed with the original by `blend`.
    """
    if mode not in MODES:
        raise ValueError(f"Unknown restoration mode: {mode}")
    if mode == "off":
        return audio

    data = np.asarray(audio, dtype=np.float32)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if not np.isfinite(data).all():
        raise ValueError("Restoration input contains non-finite samples")
    if not data.size or not data.any():
        return data

    tuning = {
        key: options.get(key)
        for key in ("nfe", "solver", "lambd", "tau")
        if mode == "resemble-enhance"
    }
    cache_folder = _root() / "cache"
    cache_path = cache_folder / f"{_cache_key(data, sample_rate, mode, tuning)}.npy"
    restored = _cache_get(cache_path, len(data))
    if restored is not None:
        print(f"Audio restoration: {mode} (cached)", flush=True)
        os.utime(cache_path)
    else:
        restored = _restore_with_sidecar(data, sample_rate, mode, options)
        _cache_put(cache_folder, cache_path, restored)

    # The blend is applied after the cache, so changing it is instant.
    return blend_restored(data, restored, options.get("blend", 1.0))


def _restore_with_sidecar(data, sample_rate, mode, options):
    python = ensure_sidecar(mode)
    device = options.get("device") or _device()
    print(f"Audio restoration: {mode} on {device}", flush=True)

    with tempfile.TemporaryDirectory(prefix="applio-restore-") as directory:
        source = Path(directory) / "input.wav"
        target = Path(directory) / "output.wav"
        sf.write(source, data, int(sample_rate), subtype="FLOAT")

        command = [
            str(python),
            "-I",
            str(WORKER),
            "--backend",
            mode,
            "--input",
            str(source),
            "--output",
            str(target),
            "--device",
            device,
        ]
        if mode == "resemble-enhance":
            command += [
                "--nfe",
                str(int(options.get("nfe", 32))),
                "--solver",
                str(options.get("solver", "midpoint")),
                "--lambd",
                str(float(options.get("lambd", 0.5))),
                "--tau",
                str(float(options.get("tau", 0.5))),
            ]
        env = dict(os.environ)
        # VoiceFixer caches under ~/.cache; keep it inside the sidecar root.
        home = _env_dir(mode) / "home"
        home.mkdir(parents=True, exist_ok=True)
        env["HOME"] = env["USERPROFILE"] = str(home)
        _run(command, env=env, label=f"Restore {mode}")

        restored, out_rate = sf.read(target, dtype="float32", always_2d=False)
        if restored.ndim > 1:
            restored = restored.mean(axis=1)
        if out_rate != sample_rate:
            restored = soxr.resample(restored, out_rate, int(sample_rate))

    length = len(data)
    if len(restored) >= length:
        restored = restored[:length]
    else:
        restored = np.pad(restored, (0, length - len(restored)))
    return restored.astype(np.float32)


def restore_file(input_path, mode, **options):
    """Restore one audio file and return the path of the restored WAV.

    Used by the GUI preview button so the result can be auditioned before a
    voice conversion is run.
    """
    path = str(input_path).strip().strip('"')
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")
    audio, rate = sf.read(path, dtype="float32", always_2d=True)
    mono = audio.mean(axis=1)
    restored = restore_audio(mono, rate, mode, **options)
    folder = Path(tempfile.gettempdir()) / "applio-restore-preview"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{Path(path).stem}_restored_{mode}.wav"
    sf.write(out, restored, int(rate), subtype="PCM_24")
    return str(out)
