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

Run in the authoring environment (Linux, CPU, Python 3.11):

- The patch applies to base commit `59c1131` on a fresh checkout and every modified file compiles.
- `infer --help` lists the new options. `off` is an exact bypass and invalid modes are rejected.
- `--f0-smooth` filters each voiced run on its own. Voicing is unchanged, spikes inside a run are removed, and dtype, empty and all-unvoiced input are handled.
- The restoration cache hits on identical input, misses when audio or tuning changes, prunes to a fixed size, and recomputes corrupt or wrong-length entries.
- Resemble Enhance's real inference code runs end to end in the sidecar environment, with no `deepspeed`, `gradio` or `ptflops` installed. This used default hyperparameters and random weights, because the real weights were not downloadable there.

## What was not verified

- Output quality. No real restorer weights were run, and no real garbled vocal was converted. Whether restoration actually improves your conversions is untested.
- VoiceFixer beyond installation. Importing it downloads its weights, which the authoring sandbox blocked.
- Windows and macOS. The pins were resolved on Linux. The `deepspeed` stand-in exists so Resemble Enhance can install on Windows, but that has not been run there.
- GPU execution.

## Known limitations

- Each sidecar environment is large, about 6 GB measured on Linux, because of PyTorch and its CUDA libraries. Dropping `deepspeed` and `gradio` did not shrink it meaningfully; the benefit is that Resemble Enhance installs without them. Using both restorers costs roughly 12 GB.
- Restorer weights are stored inside the sidecar environment. Deleting `audio-restore/` under the Applio config directory removes them.
- Batch tab and preset files have no restoration controls yet. Use the CLI for batch work.
- Each file launches the sidecar and reloads the model. Identical repeat runs are served from an on-disk cache of the last 24 results.
- Restoration changes the input signal. Compare the output with the original before converting at scale.

## Ideas for next steps

- CPU-only PyTorch wheels for the sidecar on machines without a GPU.
- Detect damaged frames and restore only those, blending the original elsewhere.
- Batch tab controls and preset support.
- Fine-tune voice models on augmented, degraded copies of the training set.
