# Applio vocal restoration patch

Adds optional vocal restoration to [Applio](https://github.com/IAHispano/Applio), plus a guard that protects against the restorer damaging the audio. Everything is controlled from the Applio GUI.

Built for **Applio 3.6.4** on Windows. `patches/applio-3.6.4-vocal-restoration.patch` is the same change as a patch against stock 3.6.4 (it applies cleanly with `git apply`). `patches/applio-vocal-restoration.patch` targets a newer Applio base commit and is an older version: it does not include the guard, the new defaults or the new warnings.

## Read this first: singing

Both restorers (VoiceFixer and Resemble Enhance) are trained on **speech**, not singing. On a real separated singing vocal (a 4.5 minute stem from a 320 kbps source, restored by Resemble Enhance with real weights) the measured result was:

- quiet passages (breaths, note tails) were cut by about 25 dB at the median, and 28% of loud frames lost more than 4 dB, so the restorer acted like a noise gate
- 19% of voiced frames moved in pitch by more than 50 cents (3% to 46% depending on the section)
- the 8-16 kHz band fell by about 5 dB relative to the midrange
- most loud passages were left nearly unchanged (median -0.5 dB), apart from the dropouts above

This matches a report in Resemble Enhance's own issue tracker (clean singing partly eliminated by the model, issue #34) and the research literature on generative enhancement (spurious or missing content, pitch and timbre drift). Voice conversion in Applio also resamples its input to 16 kHz before extracting content and pitch, so the bandwidth extension these restorers advertise has no effect on the result; only level and pitch fidelity below 8 kHz matter.

What the patch does about it:

- **A guard is on by default.** After restoration, the audio is compared with the original at 16 kHz. Wherever the restorer removed more than 4 dB of level or moved the pitch by more than 50 cents, the original is put back (short crossfades). On the stem above the guard kept the original for 42% of the audio and brought the pitch-moved frames from 19% to 2% and the quiet-passage loss from about 25 dB to 0. The console prints how much of the original was kept. Set `APPLIO_RESTORE_GUARD=0` to turn it off.
- **Safer default for Resemble Enhance denoising strength:** 0.1 instead of 0.5, matching the setting the official demo uses with denoising off. Higher values erase more.
- **Warnings in the GUI** that the restorers are experimental on singing.

For separated vocals, a de-noise or de-reverb pass in UVR (for example the Mel-Roformer denoise or de-reverb models) is usually the safer first step, because those models are trained on music. This patch does not include them.

The guard limits damage. It does not prove the part of the audio it keeps from the restorer sounds better than the original. Judge that by listening, using Preview.

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
- **Restoration strength**: 1.0 uses only the restored audio (after the guard). Lower values mix some original back in, loudness matched. Changing it is instant after the first run.
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

## Measuring a restoration

`tools/eval_restore.py original.wav restored.wav` prints the numbers above for any pair of files: quiet-passage level change, loud-passage level change, share of frames whose pitch moved, change in the 8-16 kHz band, and clipping. `tools/make_fixtures.py` writes small synthetic test files. Both need `numpy`, `soundfile`, `librosa` and `scipy`.

## What was verified

Run in the authoring sandbox (Linux, CPU):

- The 3.6.4 port compiles, and the GUI builds with the new panel on both tabs. The Single and Batch convert buttons pass exactly as many inputs as the `core.py` functions take (66 each), and the preview handler registers.
- Blend and cache logic: restoration off is an exact bypass, blend changes do not recompute, tuning changes do, and the subprocess helper streams output and reports the error tail.
- Earlier testing of the original patch (on its newer base): pitch smoothing, cache pruning and corruption handling, and end to end runs of both restorers with stand-in weights, plus fixes for NumPy 2.4, Windows `pathlib` tags in the Resemble Enhance config, and restricted `torch.load`.
- The installer `.bat` files were reviewed by reading only.
- The guard: unit tests on synthetic audio (identical input is returned unchanged; erased tails and gaps are restored; a pitch-shifted section is replaced by the original), the delay estimator on real audio (injected delays of 40, 110 and 300 samples were recovered as 44, 110 and 297), and one real restored vocal (see above). The restored file in that test was not offset from the original at all.

## What could not be verified

- **Whether restoration helps at all.** Hugging Face and Zenodo are blocked in the authoring sandbox, so the restorers were never run there with real weights. The one real run is a user's, on the singing stem described at the top, and it degraded the audio. Nothing here shows a case where restoration improves a conversion. Use the preview button to judge it on your own audio.
- **The guard's thresholds.** 4 dB and 50 cents were chosen from one file and from a challenge system that uses a similar level rule. They are not tuned. On that file a looser setting (8 dB, 100 cents) kept the original for 36% of the audio and a tighter one (2 dB, 30 cents) for 48%, so the result is not very sensitive to them. The guard does not repair the duller highs: the parts it keeps from the restorer still show the 8-16 kHz loss.
- **The new Resemble Enhance default (denoising strength 0.1).** It comes from the official demo's setting, not from a test with real weights.
- **Listening.** All measurements are numbers. No one has listened to the guarded output.
- **The installer on real Windows.** The `.bat` files were never executed. Test on a copy of your Applio folder first if you are cautious. The backup and uninstall are there for this.
- **The automatic GPU setup.** The sidecar tries CUDA wheels through uv's automatic backend and falls back to default wheels if that fails. The PyTorch download site was unreachable in the sandbox, so this was not exercised. A CPU-only result would be slow.
- **Windows file endings.** The installer compares file hashes with stock 3.6.4 (LF endings). If your copy was checked out with CRLF, it will warn that the files differ and ask before overwriting.

## Known limitations

- Restorer weights are trusted downloads from the official Resemble AI Hugging Face repo and the VoiceFixer Zenodo record, and are not hash-pinned.
- Each file launches the restorer and reloads the model.
- Applio updates overwrite the patched files. Run `install.bat` again afterward.
- Very long vocals may still need a lot of memory. This is untested.
- Restoration changes the input signal. Compare against the original before converting at scale.
- Both restorers were designed for speech. Treat them as experimental on singing, and see the top of this file.
- Preset files do not save restoration settings yet. The command line options from the earlier patch are not included in the 3.6.4 version.

## Ideas for next steps

- Run real restorations once weights are reachable, and tune the guard and defaults on more than one vocal.
- Offer a music-trained cleanup pass (Mel-Roformer denoise, de-reverb) as the first step for separated vocals.
- Run the guard's pitch check with the RMVPE model Applio already uses, and compare ContentVec features, instead of a generic pitch tracker.
- Hash-pin the two checkpoints.
- Detect damaged frames and restore only those, blending the original elsewhere.
- Preset support and command line options.
