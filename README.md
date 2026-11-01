# Applio vocal restoration patch

Patch for [IAHispano/Applio](https://github.com/IAHispano/Applio) that rebuilds garbled or rasped input vocals before voice conversion, so the voice model does not reproduce and amplify the damage.

## What it adds

- **VoiceFixer** and **Resemble Enhance** as restoration options (`--restore-mode`, and a "Vocal restoration" panel in the single-file tab).
- Each restorer runs in its own sidecar virtual environment under the Applio config directory. The environment is created on first use from exact version pins, so their dependencies cannot conflict with Applio's stack.
- Restoration runs at the file's native sample rate, before resampling to 16 kHz.
- **Pitch smoothing** (`--f0-smooth N`): median filter over the voiced pitch contour to reduce jitter that often accompanies rasp.
- Resemble Enhance tuning: `--restore-nfe`, `--restore-solver`, `--restore-lambd`, `--restore-tau`.

## Apply

```bash
git clone https://github.com/IAHispano/Applio.git
cd Applio
git checkout 59c1131   # base commit this patch was made against
git apply /path/to/patches/applio-vocal-restoration.patch
```

Or with `git am` to keep the commit message and author:

```bash
git am /path/to/patches/applio-vocal-restoration.patch
```

## Use

```bash
python core.py infer --input-path in.wav --output-path out.wav \
  --pth-path model.pth --index-path model.index \
  --restore-mode resemble-enhance --f0-smooth 5
```

Restorer weights are downloaded by the packages on first run (VoiceFixer from Zenodo, Resemble Enhance from Hugging Face).

## Files

- `rvc/lib/tools/audio_restore.py`: sidecar management and orchestration (new)
- `rvc/lib/tools/audio_restore_worker.py`: entry point that runs inside the sidecar (new)
- `rvc/lib/utils.py`: restoration hook in `load_audio_infer`
- `rvc/infer/pipeline.py`: `f0_smooth` and `_smooth_f0`
- `rvc/infer/infer.py`: passes `f0_smooth` to the pipeline
- `core.py`: CLI options and kwargs plumbing
- `tabs/inference/inference.py`: single-file tab controls

## What was verified

Run in the authoring environment (Linux, CPU, Python 3.11), against the real published Resemble Enhance configuration and random-weight stand-ins for both restorers' checkpoints:

- The patch applies to base commit `59c1131` on a clean checkout and every modified file compiles.
- `infer --help` lists the new options. `off` is an exact bypass and invalid modes are rejected.
- `--f0-smooth` filters each voiced run on its own. Voicing is unchanged, spikes inside a run are removed, and dtype, empty and all-unvoiced input are handled.
- The restoration cache hits on identical input, misses when audio or tuning changes, prunes to a fixed size, and recomputes corrupt or wrong-length entries.
- Applio's audio loader, the sidecar subprocess, the worker, checkpoint loading, restoration, resampling back to the input rate, and the cache all run end to end for both VoiceFixer and Resemble Enhance.
- Resemble Enhance runs with the real published `hparams.yaml` for the midpoint, rk4 and euler solvers and the extreme tuning values.

Problems this testing found and fixed:

- NumPy 2.4 crashes Resemble Enhance. It converts a one-element array with `float()`, which NumPy 2.4 rejects, and this only appears with the real hyperparameters. Both sidecars pin NumPy 2.3.5.
- The published `hparams.yaml` stores paths as `pathlib.PosixPath`, which Python cannot create on Windows (reproduced in simulation). The worker rewrites those entries as plain strings.
- Current PyTorch restricts what `torch.load` may unpickle, and DeepSpeed-style checkpoints can contain other objects (reproduced with a stand-in). The worker allows unrestricted loading only for files inside the sidecar's own model folders. Every other path keeps the safe default.
- Resemble Enhance needs `tabulate` at model construction.

## What could not be verified

- Output quality. The real model weights could not be downloaded in the authoring sandbox (Hugging Face and Zenodo are blocked), so no real vocal has been restored. Whether restoration improves your conversions is untested.
- The real checkpoints' contents. Loading was tested with stand-ins, and the loading policy is designed to work whether or not they hold non-tensor objects.
- Windows and macOS. The Windows config problem was reproduced and fixed in simulation only. Pins were resolved on Linux.
- GPU execution. No GPU was available. On Windows, PyPI installs a CPU-only PyTorch, so the sidecars may run on the CPU there and be slow.

## Known limitations

- Each sidecar environment is large, about 6 GB measured on Linux, because of PyTorch and its CUDA libraries. Using both restorers costs roughly 12 GB.
- Restorer weights are stored inside the sidecar environment. Deleting `audio-restore/` under the Applio config directory removes them.
- The checkpoints are trusted: they come from the official Resemble AI Hugging Face repo and the VoiceFixer Zenodo record, and are not hash-pinned.
- Batch tab and preset files have no restoration controls yet. Use the CLI for batch work.
- Each file launches the sidecar and reloads the model. Identical repeat runs are served from an on-disk cache of the last 24 results.
- Restoration changes the input signal. Compare the output with the original before converting at scale.

## Ideas for next steps

- Run a real restoration once the weights are reachable, and tune `--restore-lambd`, `--restore-tau` and `--f0-smooth` on actual Suno output.
- Hash-pin the two checkpoints.
- CUDA PyTorch wheels for the sidecars on Windows.
- Detect damaged frames and restore only those, blending the original elsewhere.
- Batch tab controls and preset support.
- Fine-tune voice models on augmented, degraded copies of the training set.
