# Applio vocal restoration patch

Adds vocal restoration to [Applio](https://github.com/IAHispano/Applio) so garbled or rasped input vocals are rebuilt before voice conversion, and the voice model does not copy and amplify the damage. Everything is controlled from the Applio GUI.

Built for **Applio 3.6.4** on Windows. A patch for a newer Applio base commit is kept in `patches/applio-vocal-restoration.patch`.

## Install (Windows, no command line needed)

1. Download this repository (green Code button, then Download ZIP) and extract it.
2. Close Applio.
3. Double-click `installer\install.bat`. It looks for `D:\Applio-3.6.4`. If that folder is not there, it asks for the path.
4. Start Applio with `run-applio.bat`.

The installer checks every file before changing anything, backs up the originals to `_vocal_patch_backup` inside the Applio folder, then copies the patched files in. If a file was edited by something else it asks before overwriting. To undo, double-click `installer\uninstall.bat`.

Files changed: `core.py`, `rvc\infer\infer.py`, `rvc\infer\pipeline.py`, `rvc\lib\utils.py`, `tabs\inference\inference.py`. Files added: `rvc\lib\tools\audio_restore.py`, `rvc\lib\tools\audio_restore_worker.py`.

## Use

In the **Inference** tab (Single and Batch), open **Advanced Settings** and find the **Vocal restoration** panel:

- **Restoration method**: Off, VoiceFixer (fast, general repair), or Resemble Enhance (slower, stronger rebuild).
- **Restoration strength**: 1.0 uses only the restored audio. Lower values mix some original back in, loudness matched. Changing it is instant after the first run.
- **Resemble Enhance tuning**: quality steps (NFE), solver, denoising strength, prior temperature.
- **Pitch smoothing**: median filter on the pitch contour to remove jitter that often comes with rasp. Try 5.
- **Preview restoration only** (Single tab): restores the selected audio and plays it back, without converting, so you can tune settings quickly.

Suggested workflow: pick the input, choose a method, click Preview, listen, adjust, then Convert.

## First use

The first time you use each restorer, Applio builds a separate environment under `assets\audio-restore` and downloads model weights. This needs internet, several GB of disk per restorer (about 6 GB measured on Linux, and the CUDA version of Applio's own PyTorch is matched so the GPU is used), and can take a long time. Progress prints in the console window that run-applio.bat opened. Later runs reuse it, and identical repeat runs are served from a cache of the last 24 results. Delete `assets\audio-restore` to remove everything.

The environments are isolated so their dependencies cannot conflict with Applio's.

## Built-in safeguards

- The installer refuses folders with an exclamation mark in the path and ZIPs run without extracting, verifies every copied file, and backs up the originals.
- Before a restorer installs, it checks for 10 GB of free disk space and warns if GitHub, PyPI or the model hosts cannot be reached.
- Failures are explained in plain words (disk full, path too long, access denied, blocked download, git missing, out of memory) at the top of the error shown in the GUI.
- Resemble Enhance installs from a GitHub zip and falls back to git, so git is not required.
- If the GPU runs out of memory, restoration retries on the CPU. If the restorer environment has no CUDA support, it runs on the CPU instead of crashing.
- Deeply nested Applio folders on Windows use a short folder at the drive root for the environment, to stay under the 260 character path limit.
- The GUI warns before a first-use install starts, since it can take a long time.

## What was verified

Run in the authoring sandbox (Linux, CPU):

- The 3.6.4 port compiles, and the GUI builds with the new panel on both tabs. The Single and Batch convert buttons pass exactly as many inputs as the `core.py` functions take (66 each), and the preview handler registers.
- Blend and cache logic: restoration off is an exact bypass, blend changes do not recompute, tuning changes do, and the subprocess helper streams output and reports the error tail.
- Earlier testing of the original patch (on its newer base): pitch smoothing, cache pruning and corruption handling, and end to end runs of both restorers with stand-in weights, plus fixes for NumPy 2.4, Windows `pathlib` tags in the Resemble Enhance config, and restricted `torch.load`.
- The installer `.bat` files were reviewed by reading only.

## What could not be verified

- **Output quality.** Hugging Face and Zenodo are blocked in the sandbox, so no real vocal has been restored with real weights. Whether it improves your conversions is untested. Use the preview button to judge it on your own audio.
- **The installer on real Windows.** The `.bat` files were never executed. Test on a copy of your Applio folder first if you are cautious. The backup and uninstall are there for this.
- **The automatic GPU setup.** The sidecar tries CUDA wheels through uv's automatic backend and falls back to default wheels if that fails. The PyTorch download site was unreachable in the sandbox, so this was not exercised. A CPU-only result would be slow.
- **Windows file endings.** The installer compares file hashes with stock 3.6.4 (LF endings). If your copy was checked out with CRLF, it will warn that the files differ and ask before overwriting.

## Known limitations

- Restorer weights are trusted downloads from the official Resemble AI Hugging Face repo and the VoiceFixer Zenodo record, and are not hash-pinned.
- Each file launches the restorer and reloads the model.
- Applio updates overwrite the patched files. Run `install.bat` again afterward.
- Very long vocals may still need a lot of memory. This is untested.
- Restoration changes the input signal. Compare against the original before converting at scale.
- Preset files do not save restoration settings yet. The command line options from the earlier patch are not included in the 3.6.4 version.

## Ideas for next steps

- Run real restorations once weights are reachable, and tune defaults on actual damaged vocals.
- Hash-pin the two checkpoints.
- Detect damaged frames and restore only those, blending the original elsewhere.
- Preset support and command line options.
