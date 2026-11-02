"""Sidecar entry point for audio restoration.

Runs inside the isolated restoration environment, never inside Applio's own
interpreter, so the restoration packages cannot disturb Applio's pinned
dependencies. Imports nothing from the rvc package.

Usage (launched by audio_restore.py with the sidecar's python -I):
    worker.py --backend {voicefixer,resemble-enhance} --input in.wav \
        --output out.wav --device {cpu,cuda} [--nfe N] [--solver S] \
        [--lambd F] [--tau F]
"""

import argparse
import importlib.util
import os
import pathlib
import re
import sys
import types


def _stand_in_for_deepspeed():
    """Provide inert deepspeed modules when the real package is absent.

    resemble_enhance imports deepspeed at module level for its training code.
    Inference never calls into it, and the real package is large and does not
    install on Windows, so a stand-in satisfies the imports.
    """
    if importlib.util.find_spec("deepspeed") is not None:
        return

    def module(name, **members):
        mod = types.ModuleType(name)
        mod.__dict__.update(members)
        sys.modules[name] = mod
        return mod

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("deepspeed is not installed; training is unsupported")

    root = module("deepspeed", DeepSpeedConfig=type("DeepSpeedConfig", (), {}))
    accelerator = module("deepspeed.accelerator", get_accelerator=unavailable)
    runtime = module("deepspeed.runtime")
    engine = module(
        "deepspeed.runtime.engine", DeepSpeedEngine=type("DeepSpeedEngine", (), {})
    )
    utils = module("deepspeed.runtime.utils", clip_grad_norm_=unavailable)
    root.accelerator, root.runtime = accelerator, runtime
    runtime.engine, runtime.utils = engine, utils


_PATH_TAG = re.compile(
    r"!!python/object/apply:pathlib\.PosixPath\r?\n((?:- [^\r\n]*\r?\n?)+)"
)


def _normalize_hparams(path):
    """Rewrite pathlib tags in Resemble Enhance's hparams.yaml as plain strings.

    The published file stores paths as pathlib.PosixPath objects, which Python
    refuses to create on Windows. The three paths are training-data folders
    that inference never reads, so plain strings carry everything needed.
    """
    path = pathlib.Path(path)
    text = path.read_text(encoding="utf-8")

    def plain(match):
        parts = [line[2:].strip() for line in match.group(1).splitlines()]
        return "/".join(parts) + "\n"

    fixed = _PATH_TAG.sub(plain, text)
    if fixed != text:
        path.write_text(fixed, encoding="utf-8")
    return fixed != text


def _checkpoint_roots():
    roots = [pathlib.Path(os.path.expanduser("~")) / ".cache" / "voicefixer"]
    spec = importlib.util.find_spec("resemble_enhance")
    if spec and spec.origin:
        roots.append(pathlib.Path(spec.origin).parent / "model_repo")
    return [root.resolve() for root in roots]


def _trust_own_checkpoints(roots=None):
    """Allow full unpickling only for checkpoints the packages downloaded.

    Recent PyTorch defaults torch.load to a restricted unpickler, and both
    restorers call it without arguments on DeepSpeed or Lightning checkpoints
    that may hold non-tensor objects. Files inside the sidecar's own model
    folders are loaded unrestricted; every other path keeps the safe default.
    """
    import torch

    allowed = _checkpoint_roots() if roots is None else [pathlib.Path(r).resolve() for r in roots]
    original = torch.load

    def load(f, *args, **kwargs):
        if kwargs.get("weights_only") is None and isinstance(f, (str, os.PathLike)):
            path = pathlib.Path(f).resolve()
            if any(root in path.parents for root in allowed):
                kwargs["weights_only"] = False
        return original(f, *args, **kwargs)

    torch.load = load
    return original


def run_voicefixer(args):
    _trust_own_checkpoints()
    from voicefixer import VoiceFixer

    # mode 0 is the default general-purpose restoration path.
    restorer = VoiceFixer()
    restorer.restore(
        input=args.input,
        output=args.output,
        cuda=args.device == "cuda",
        mode=0,
    )


def run_resemble_enhance(args):
    import numpy as np
    import soundfile as sf
    import torch

    _stand_in_for_deepspeed()
    _trust_own_checkpoints()
    from resemble_enhance.enhancer.download import download
    from resemble_enhance.enhancer.inference import enhance

    # Fetch the model files first so hparams.yaml can be made Windows-safe
    # before the package parses it.
    _normalize_hparams(download() / "hparams.yaml")

    # soundfile instead of torchaudio.load/save: recent torchaudio builds
    # route file I/O through TorchCodec, which is not pinned here.
    data, sr = sf.read(args.input, dtype="float32", always_2d=True)
    dwav = torch.from_numpy(np.ascontiguousarray(data.mean(axis=1)))
    hwav, out_sr = enhance(
        dwav,
        sr,
        args.device,
        nfe=args.nfe,
        solver=args.solver,
        lambd=args.lambd,
        tau=args.tau,
    )
    out = hwav.detach().cpu().float().numpy().reshape(-1)
    sf.write(args.output, out, int(out_sr), subtype="FLOAT")


BACKENDS = {
    "voicefixer": run_voicefixer,
    "resemble-enhance": run_resemble_enhance,
}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=sorted(BACKENDS), required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--nfe", type=int, default=32)
    parser.add_argument(
        "--solver", choices=("midpoint", "rk4", "euler"), default="midpoint"
    )
    parser.add_argument("--lambd", type=float, default=0.5)
    parser.add_argument("--tau", type=float, default=0.5)
    args = parser.parse_args(argv)
    if args.device == "cuda":
        # The caller picks the device from Applio's own PyTorch, but this
        # environment has its own, which may be a CPU-only build.
        import torch

        if not torch.cuda.is_available():
            print("CUDA is not available in this environment, using the CPU.")
            args.device = "cpu"
    BACKENDS[args.backend](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
