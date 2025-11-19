<!-- Guidance for AI coding agents working on the Balloon Master ad automation script -->
# Copilot / AI Agent Instructions — literate-pancake

Purpose: help an AI contributor become productive quickly with the ad-watching automation script the user provided (`untitled:balloon_master_ads.py`).

Quick start

- Requirements: `python3` (3.8+), `adb` on PATH, an Android device or emulator with USB debugging enabled.
- Run locally (script is currently opened as `untitled:balloon_master_ads.py`):

```bash
python3 untitled:balloon_master_ads.py
```

High-level architecture & intent

- Single-script automation that drives the device using ADB. All device interactions go through two helpers: `adb(args_list)` and `run_adb(args_list)`.
- Control flow:
  - Trigger an ad in-game via UI taps (`click_pause_menu()`, `click_home_button()` / `click_retry_button()`).
  - Wait (`AD_WAIT_AFTER_BUTTON`) and then run the watchdog `handle_ads()` which tries multiple escape strategies until the game is foregrounded.
  - Alternate button mode between `home` and `retry` each successful cycle.

Key project-specific patterns (only change when you confirm behavior on-device)

- Top-activity detection: `get_top_activity()` parses `dumpsys window windows` and `dumpsys activity activities`. Keep both calls when editing detection logic.
- Ad heuristic: `is_ad_playing()` checks `get_top_activity()` against `GAME_PACKAGE` and an `ad_indicators` list. If ad-detection fails, add observed package names to `ad_indicators` (see Debugging tips).
- Watchdog ordering: `handle_ads()` runs methods in a deliberate order: `minimize_and_monkey_relaunch()` → `back_button_burst()` → `home_button_burst()` → `app_switcher_clear()` → `mega_escape_sequence()` → `force_stop_and_relaunch()`. The script relies on that ordering for this game.
- Sticky-ad tracking: `last_ad_package` + `sticky_ad_counter` escalate to `mega_escape_sequence()` and `force_stop_and_relaunch()` when repeats occur.
- Tuning via constants: adjust top-of-file constants (`AD_WAIT_AFTER_BUTTON`, `BACK_BUTTON_ATTEMPTS`, `HOME_BUTTON_BURST`, `JITTER_PX`, coordinate tuples) rather than changing logic when possible.

Useful code locations and functions to inspect

- `untitled:balloon_master_ads.py` — primary script (key functions):
  - `adb()`, `run_adb()` — centralize modification of adb calls
  - `get_top_activity()` — dumpsys parsing and package extraction
  - `is_ad_playing()` — ad vs game detection
  - `handle_ads()` — main watchdog orchestration
  - escape primitives: `back_button_burst()`, `home_button_burst()`, `app_switcher_clear()`, `minimize_and_monkey_relaunch()`, `mega_escape_sequence()`, `force_stop_and_relaunch()`

Developer workflows & debugging tips (project-specific)

- Reproduce detection: run these on the host to inspect the real activity name when an ad is showing:

```bash
adb -s <serial> shell dumpsys window windows | grep -E "mResumedActivity|mFocusedApp|mCurrentFocus" -n
adb -s <serial> shell dumpsys activity activities | grep -E "mResumedActivity|mFocusedApp|mCurrentFocus" -n
adb -s <serial> shell ps -A | grep <ad-package-fragment>
# Copilot / AI Agent Instructions — literate-pancake

Purpose: onboard AI contributors quickly to the single automation script that drives an Android game via ADB.

Quick start
- Prereqs: `python3` (3.8+), `adb` on PATH, Android device/emulator with USB debugging.
- Run (dry-run recommended while iterating):
  - `python3 scripts/balloon_master_ads.py` (consider adding `--dry-run` to avoid sending adb commands initially)

Key files & single responsibility
- `scripts/balloon_master_ads.py`: one-file automation. Everything (adb wrappers, heuristics, watchdog) lives here — edit carefully.

Important patterns & why they matter
- Centralized adb: modify `adb()` / `run_adb()` to change execution behavior (dry-run, logging).
- Heuristic detection: `get_top_activity()` parses `dumpsys` output; `is_ad_playing()` compares that with `GAME_PACKAGE` and `ad_indicators`. Add new ad package fragments to `ad_indicators` when you observe unknown ad packages.
- Watchdog order: `handle_ads()` runs escape primitives in a strict sequence (minimize → back taps → home → app-switch clear → mega escape → force-stop). The sequence and escalation logic (via `sticky_ad_counter`) are intentional — changing order may break recovery.
- Tunables live as top-of-file constants (example: `AD_WAIT_AFTER_BUTTON`, `BACK_BUTTON_ATTEMPTS`, `HOME_BUTTON_BURST`, `JITTER_PX`, coordinate tuples). Prefer tuning constants over changing core logic.

Developer workflows & debugging commands
- Inspect current top activity while reproducing an ad:
  - `adb -s <serial> shell dumpsys window windows | grep -E "mResumedActivity|mFocusedApp|mCurrentFocus" -n`
  - `adb -s <serial> shell dumpsys activity activities | grep -E "mResumedActivity|mFocusedApp|mCurrentFocus" -n`
  - `adb -s <serial> shell ps -A | grep <package-fragment>`
  - `adb -s <serial> logcat -v time`
- Calibrate tap coords interactively: `adb shell input tap X Y` then copy working values into constants (`LVL_BTN`, `PAUSE_MENU`, `HOME_BTN`, `RETRY_BTN`).

Conventions & gotchas
- No tests/CI — validate changes on-device incrementally.
- Randomized delays and jitter are deliberate to avoid deterministic behavior; preserve them unless you understand the risk.
- `GAME_PACKAGE` default is `com.balloon.master.cube.match`; keep it correct when committing.

Suggested small improvements (low-risk)
- Add `--dry-run` flag and implement printing instead of executing in `run_adb()`.
- Add `--log-dumpsys N` to capture `get_top_activity()` outputs across N cycles (helps augment `ad_indicators`).
- Add a retry/backoff loop around `relaunch_game()` verifying focus with `get_top_activity()`.

When opening a PR, ask the owner
- Which device serial(s) are canonical (`DEFAULT_DEVICE`)?
- Any observed ad package names to add to `ad_indicators`?
- Should the script be committed under `scripts/balloon_master_ads.py` and should we add a short `README.md` for usage?

End of instructions — ask me to expand any section or add a short `README` and `--dry-run` support.
