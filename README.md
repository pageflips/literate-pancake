# literate-pancake — Balloon Master ad automation

This repository contains a small automation script that drives an Android device via ADB
to trigger rewarded ads in "Balloon Master 3D" and reliably clear them so new ads can be
watched in sequence.

Quick start

- Requirements: `python3` (3.8+), `adb` on PATH, an Android device or emulator with USB debugging enabled.
- Default device serial is set to `ZY22L7ZMHX` in `scripts/balloon_master_ads.py`.

Run (dry-run first to inspect commands):

```bash
# dry-run prints adb commands instead of executing them
python3 scripts/balloon_master_ads.py --dry-run

# collect top-activity samples (N cycles) to help tune ad patterns
python3 scripts/balloon_master_ads.py --log-dumpsys 12 --dry-run

# run against device (will interact with device)
python3 scripts/balloon_master_ads.py --device ZY22L7ZMHX
```

Calibration & tuning

- The script centralizes adb calls in `adb()` / `run_adb()` and honors `--dry-run` to print commands.
- Primary tunables are at the top of `scripts/balloon_master_ads.py`:
	- `LVL_BTN`, `PAUSE_MENU`, `HOME_BTN`, `RETRY_BTN` — UI coordinates for in-game taps
	- `CLOSE_COORDS` and `POPUP_CLOSE_COORDS` — positions the script will try to dismiss ads/popups
	- Timing constants: `AD_WAIT_AFTER_BUTTON`, `BACK_BUTTON_DELAY`, `APP_RESTART_WAIT_SEC`, etc.

Useful adb commands for debugging while reproducing an ad

```bash
# show resumed/focused activity
adb -s <serial> shell dumpsys window windows | grep -E "mResumedActivity|mFocusedApp|mCurrentFocus" -n
adb -s <serial> shell dumpsys activity activities | grep -E "mResumedActivity|mFocusedApp|mCurrentFocus" -n
# list processes matching a package fragment
adb -s <serial> shell ps -A | grep <package-fragment>
# view device logcat
adb -s <serial> logcat -v time
```

What changed in this repo (recent)

- `scripts/balloon_master_ads.py` now includes:
	- `--dry-run` and `--log-dumpsys` flags
	- targeted close-tap attempts (`CLOSE_COORDS`) and `POPUP_CLOSE_COORDS` for in-game popups
	- relaunch verification loop to ensure the game is foregrounded
	- forced browser/custom-tab kill as a fallback for sticky ads

Safety & testing notes

- Always test with `--dry-run` before running live.
- Tune `CLOSE_COORDS` / `POPUP_CLOSE_COORDS` to match your device resolution. The script defaults have been tuned for 720x1600 devices.

If you'd like, I can open a PR with these changes and include any additional coordinates you want added. Feel free to update coordinates in `scripts/balloon_master_ads.py` and re-run with `--dry-run` to verify.
# literate-pancake