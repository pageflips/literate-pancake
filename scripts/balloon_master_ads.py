#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Committed copy of the ad-watching automation script with a few safety
and debugging improvements:

- `--dry-run` to print adb commands instead of executing them
- `--log-dumpsys N` to collect top-activity values for N cycles
- expanded ad/package/activity pattern lists from user input

This file is safe to run from the repo as: `python3 scripts/balloon_master_ads.py`
"""

import argparse
import subprocess
import time
import sys
import re
import random
import traceback
import logging

# ===============================================================
# =============== CONFIG — BALLOON MASTER 3D ====================
# ===============================================================

# ---- Device & Game ----
DEFAULT_DEVICE = "ZY22L7ZMHX"
GAME_PACKAGE = "com.balloon.master.cube.match"

# ---- In-Game Taps ----
SAFE_TAP = (567, 392)  # Startup popup dismissal
LVL_BTN = (300, 1317)  # Main screen level button
PAUSE_MENU = (625, 133)  # In-game pause button
HOME_BTN = (159, 851)  # Pause menu -> Home (TRIGGERS AD)
RETRY_BTN = (569, 884)  # Pause menu -> Retry (TRIGGERS AD)

# ---- Ad Strategy ----
USE_HOME_FIRST = True  # Start with HOME button, alternate to RETRY
AD_WAIT_AFTER_BUTTON = 3.5  # Wait after button tap to let ad appear

# ---- AGGRESSIVE Ad Clearing Settings ----
BACK_BUTTON_ATTEMPTS = (4, 6)  # Random between 4-6 attempts
BACK_BUTTON_DELAY = (0.5, 0.8)  # Random delay between back attempts
HOME_BUTTON_BURST = 3  # How many home button presses in burst
STICKY_AD_THRESHOLD = 2  # After this many same ads, escalate

# ---- Timing ----
GAME_READY_DELAY_SEC = 6.0  # Wait on first launch
APP_RESTART_WAIT_SEC = 12.0  # Wait after app restart
CYCLE_COOLDOWN_SEC = (1.9, 2.2)  # Random cooldown between cycles

# ---- Tap Jitter ----
JITTER_PX = 3

# Common locations for ad-close buttons (try several common corners/areas)
# Values are (x, y) and should be adjusted per device if needed.
# Device: 720x1600 recommended defaults + common ad X taps provided by user
CLOSE_COORDS = [
    # user-provided common ad 'X' taps (good on 720x1600)
    (650, 134),
    (59, 136),
    (649, 203),
    # typical top-right / top-left / center-top spots
    (690, 80),
    (60, 80),
    (360, 60),
]

# In-game popup close coordinates (user-provided)
POPUP_CLOSE_COORDS = [
    (552, 344),
    (643, 406),
    (679, 271),
    (558, 394),
]

# ===============================================================
# ===================== INTERNAL STATE ==========================
# ===============================================================
ad_cycle = 0
button_mode = "home" if USE_HOME_FIRST else "retry"
needs_lvl_click = False

# Sticky ad tracking
sticky_ad_counter = 0
last_ad_package = None

# Runtime flags (populated from argparse)
DRY_RUN = False
LOG_DUMPSYS = 0

# ===============================================================
# ==================== AD/ACTIVITY PATTERNS ======================
# ===============================================================

AD_KEYWORDS = {
    "adactivity",
    "admob",
    "google.android.gms.ads",
    "gms.ads",
    "googleads",
    "applovin",
    "max",
    "unityads",
    "ironsource",
    "supersonic",
    "vungle",
    "chartboost",
    "adcolony",
    "mintegral",
    "bytedance",
    "pangle",
    "facebook.ads",
    "audience",
    "moloco",
}

AD_PACKAGES = {
    "com.google.android.gms",
    "com.google.android.gms.ads",
    "com.applovin",
    "com.applovin.sdk",
    "com.unity3d.ads",
    "com.ironsource",
    "com.ironsource.sdk",
    "com.vungle",
    "com.chartboost",
    "com.adcolony",
    "com.mintegral.msdk",
    "com.bytedance.sdk",
    "com.bytedance.sdk.openadsdk",
    "com.pangle",
    "com.facebook.ads",
    "com.moloco",
}

# Strong patterns — applied ONLY to the focused activity name.
AD_ACTIVITY_PATTERNS = re.compile(r"(?:AdActivity$|Fullscreen|Interstitial|Rewarded)", re.IGNORECASE)

DANGEROUS_ACTIVITIES = {
    "com.android.vending/com.google.android.finsky.activities.MainActivity",
    "com.android.vending/com.android.vending.AssetBrowserActivity",
    "com.google.android.packageinstaller/com.android.packageinstaller.PackageInstallerActivity",
    "com.android.packageinstaller/com.android.packageinstaller.PackageInstallerActivity",
    "com.google.android.packageinstaller/com.android.packageinstaller.InstallStart",
    "com.android.packageinstaller/com.android.packageinstaller.InstallStart",
}

DANGEROUS_PACKAGES = {"com.android.vending", "com.google.android.packageinstaller", "com.android.packageinstaller"}

# Browsers / custom tabs that can reopen sticky ads
BROWSER_PACKAGES = {
    "com.android.chrome",
    "com.chrome.beta",
    "com.chrome.dev",
    "com.brave.browser",
    "org.mozilla.firefox",
    "org.mozilla.firefox_beta",
    "com.microsoft.emmx",
    "com.opera.browser",
    "com.opera.mini.native",
    "com.duckduckgo.mobile.android",
    "com.vivaldi.browser",
}

# ===============================================================
# ==================== HELPER FUNCTIONS ==========================
# ===============================================================


def adb(args_list):
    """Build ADB command with device serial."""
    base = ["adb"]
    if DEFAULT_DEVICE:
        base += ["-s", DEFAULT_DEVICE]
    return base + args_list


def run_adb(args_list, show_err=False):
    """Run ADB command and return stripped output. Honors `DRY_RUN`."""
    cmd = adb(args_list)
    if DRY_RUN:
        print("[dry-run] ", " ".join(cmd))
        return ""
    try:
        out = subprocess.check_output(cmd, stderr=(None if show_err else subprocess.DEVNULL), text=True)
        return out.strip()
    except subprocess.CalledProcessError:
        return ""


def boot_win_adb_once():
    """Windows-specific: ensure ADB server is running."""
    if sys.platform.startswith("win"):
        try:
            subprocess.check_call(["adb", "start-server"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            time.sleep(0.5)
        except Exception:
            pass


def tap(x, y):
    """Tap with jitter to avoid bot detection."""
    jx = x + random.randint(-JITTER_PX, JITTER_PX)
    jy = y + random.randint(-JITTER_PX, JITTER_PX)
    run_adb(["shell", "input", "tap", str(jx), str(jy)])


def go_home():
    """Press HOME."""
    run_adb(["shell", "input", "keyevent", "KEYCODE_HOME"])


def go_back():
    """Press BACK."""
    run_adb(["shell", "input", "keyevent", "KEYCODE_BACK"])


def app_switcher():
    """Open app switcher (recents)."""
    run_adb(["shell", "input", "keyevent", "KEYCODE_APP_SWITCH"])


def force_stop_pkg(pkg):
    """Force-stop a package."""
    run_adb(["shell", "am", "force-stop", pkg])


def launch_pkg(pkg):
    """Launch a package."""
    run_adb(["shell", "monkey", "-p", pkg, "1"])


def relaunch_game():
    """Monkey launch the game without force-stop (NO HOME/BACK)."""
    if DRY_RUN:
        print("[dry-run] monkey relaunch", GAME_PACKAGE)
        return
    subprocess.call(adb(["shell", "monkey", "-p", GAME_PACKAGE, "-c", "android.intent.category.LAUNCHER", "1"]))


def relaunch_and_verify(retries=5, initial_delay=1.5):
    """Relaunch the game and verify it's foregrounded. Returns True if successful."""
    backoff = initial_delay
    for attempt in range(retries):
        print(f"[relaunch] attempt {attempt+1}/{retries} (backoff {backoff}s)")
        relaunch_game()
        time.sleep(backoff)

        top = get_top_activity()
        if top and GAME_PACKAGE in top and not is_ad_playing():
            print("[relaunch] verified game is foregrounded")
            return True

        backoff = min(backoff * 1.8, 8.0)

    print("[relaunch] verification failed after retries")
    return False


def get_top_activity():
    """Get the current top activity package name."""
    for svc in (["shell", "dumpsys", "window", "windows"], ["shell", "dumpsys", "activity", "activities"]):
        try:
            cmd = adb(svc)
            if DRY_RUN:
                print("[dry-run] ", " ".join(cmd))
                continue
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=5).decode(errors="ignore")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue

        for line in out.splitlines():
            if any(k in line for k in ("mResumedActivity", "mCurrentFocus", "mFocusedApp")):
                # Extract package name
                match = re.search(r"([\w\.]+)(?:/|$)", line)
                if match:
                    pkg = match.group(1)
                    # Filter out system UI
                    if pkg and pkg != "com.android.systemui":
                        return pkg
    return ""


def is_ad_playing():
    """Check if ad is currently playing using expanded heuristics."""
    top = get_top_activity()

    if not top:
        return False

    # If it's the game package, not an ad
    if GAME_PACKAGE in top:
        return False

    lower = top.lower()

    # Danger activities / packages (installers, play-store flows) — treat as ad/escape
    if any(d in top for d in DANGEROUS_ACTIVITIES) or any(p in top for p in DANGEROUS_PACKAGES):
        return True

    # Strong pattern match on focused activity name
    if AD_ACTIVITY_PATTERNS.search(top):
        return True

    # Package or keyword heuristics
    if any(pkg in lower for pkg in AD_PACKAGES):
        return True
    if any(kw in lower for kw in AD_KEYWORDS):
        return True

    # Browsers/custom tabs that often open from ads
    if any(bp in top for bp in BROWSER_PACKAGES):
        return True

    # If it's not the game and not system UI, assume ad context
    return True


def close_ad_by_tap(max_rounds=2):
    """Try common 'close' tap positions to dismiss overlays. Returns True if ad cleared."""
    print("🖱️ Trying targeted ad-close taps...")
    for r in range(max_rounds):
        for (cx, cy) in CLOSE_COORDS:
            tap(cx, cy)
            time.sleep(0.25)
            if not is_ad_playing():
                print(f"✅ ad cleared by tap after {r+1} rounds")
                return True
        # small pause between rounds
        time.sleep(0.4)

    print("⚠️ targeted taps didn't clear ad")
    return False


def kill_browser_packages_if_needed(current_top):
    """Force-stop browser/custom-tab packages if they're the likely ad host."""
    if not current_top:
        return False

    for bp in BROWSER_PACKAGES:
        if bp in current_top:
            print(f"🧨 Detected browser ad host '{bp}' — force-stopping it")
            force_stop_pkg(bp)
            time.sleep(0.8)
            return True
    return False


# ===============================================================
# ========== SUPER AGGRESSIVE AD CLEARING METHODS ===============
# ===============================================================


def back_button_burst():
    """Aggressive back button burst with random timing."""
    attempts = random.randint(*BACK_BUTTON_ATTEMPTS)
    print(f"⬅️ back button burst ({attempts} attempts)...")

    for i in range(attempts):
        go_back()
        delay = random.uniform(*BACK_BUTTON_DELAY)
        time.sleep(delay)

        # Check every 2 attempts
        if i % 2 == 1 and not is_ad_playing():
            print(f"✅ back button worked after {i+1} attempts!")
            return True

    return not is_ad_playing()


def home_button_burst():
    """Rapid home button presses to kill ads."""
    print(f"🏠 home button burst ({HOME_BUTTON_BURST} presses)...")

    for _ in range(HOME_BUTTON_BURST):
        go_home()
        time.sleep(0.2)

    time.sleep(0.5)
    return not is_ad_playing()


def app_switcher_clear():
    """Use app switcher to kill ad context."""
    print("📱 app switcher clear...")

    # Open app switcher
    app_switcher()
    time.sleep(0.6)

    # Tap game to foreground it
    tap(360, 800)  # Approximate middle of screen
    time.sleep(0.8)

    return not is_ad_playing()


def minimize_and_monkey_relaunch():
    """Minimize and use monkey relaunch (your friend's method)."""
    print("🔄 minimize & monkey relaunch...")

    go_home()
    time.sleep(0.8)
    success = relaunch_and_verify(retries=4, initial_delay=1.2)
    return success


def force_stop_and_relaunch():
    """Last resort: force stop and relaunch."""
    print("🛑 FORCE STOP & RELAUNCH...")

    force_stop_pkg(GAME_PACKAGE)
    time.sleep(1.5)
    # Try relaunch and verify; if verification fails, still return False
    success = relaunch_and_verify(retries=5, initial_delay=2.0)
    if not success:
        # Give the device a final wait and assume best effort
        time.sleep(APP_RESTART_WAIT_SEC)
    return success


def mega_escape_sequence():
    """Combined escape: back burst + home burst + switcher."""
    print("💥 MEGA ESCAPE SEQUENCE...")

    # Phase 1: Back burst
    for _ in range(3):
        go_back()
        time.sleep(0.3)

    time.sleep(0.5)

    # Phase 2: Home burst
    for _ in range(2):
        go_home()
        time.sleep(0.2)

    time.sleep(0.5)

    # Phase 3: App switcher
    app_switcher()
    time.sleep(0.5)
    go_home()
    time.sleep(0.5)

    # Relaunch
    # If the ad opened a browser or custom tab, try to kill it first
    top = get_top_activity()
    kill_browser_packages_if_needed(top)

    success = relaunch_and_verify(retries=4, initial_delay=1.2)
    return success


def handle_ads():
    """
    WATCHDOG METHOD - always assume ad is present and clear it.
    No detection checks, just blast through clearing methods.
    """
    global sticky_ad_counter, last_ad_package

    current_ad = get_top_activity()

    # Track sticky ads
    if current_ad == last_ad_package and current_ad != "" and current_ad != GAME_PACKAGE:
        sticky_ad_counter += 1
        print(f"⚠️ STICKY AD! count: {sticky_ad_counter}/{STICKY_AD_THRESHOLD}")
    else:
        last_ad_package = current_ad

    # WATCHDOG: No detection check, just always clear
    print(f"🔴 WATCHDOG: clearing ad (current activity: {current_ad})")

    # QUICK ATTEMPT: try targeted ad-close taps first
    if close_ad_by_tap():
        print("✅ closed by targeted taps")
        sticky_ad_counter = 0
        return True

    # PHASE 1: Minimize & monkey relaunch (FIRST - most reliable method)
    monkey_ok = minimize_and_monkey_relaunch()
    print("✅ monkey relaunch complete" if monkey_ok else "⚠️ monkey relaunch did not finish")

    # Check if we're back in game after monkey
    if monkey_ok and not is_ad_playing():
        print("✅ back in game after monkey!")
        sticky_ad_counter = 0
        return True

    # PHASE 2: Back button burst
    if back_button_burst():
        print("✅ cleared with back button!")
        sticky_ad_counter = 0
        return True

    # PHASE 3: Home button burst
    if home_button_burst():
        print("✅ cleared with home button!")
        sticky_ad_counter = 0
        return True

    # PHASE 4: App switcher
    if app_switcher_clear():
        print("✅ cleared with app switcher!")
        sticky_ad_counter = 0
        return True

    # PHASE 5: Mega escape (if sticky)
    if sticky_ad_counter >= STICKY_AD_THRESHOLD:
        print("🔥 STICKY AD - MEGA ESCAPE!")
        if mega_escape_sequence():
            print("✅ cleared with mega escape!")
            sticky_ad_counter = 0
            return True

    # PHASE 6: Nuclear (force stop)
    print("⚠️ AD WON'T DIE - FORCE STOPPING!")
    fs_ok = force_stop_and_relaunch()
    if fs_ok:
        print("✅ cleared after force-stop & relaunch")
    else:
        print("⚠️ force-stop relaunch failed to verify")

    sticky_ad_counter = 0
    return fs_ok


# ===============================================================
# ==================== GAME INTERACTION =========================
# ===============================================================


def click_lvl_button():
    """Click the level button to enter game mode."""
    print("[game] clicking LVL button...")
    tap(*LVL_BTN)
    time.sleep(1.2)


def click_pause_menu():
    """Click pause menu to access HOME/RETRY buttons."""
    print("[game] opening pause menu...")
    tap(*PAUSE_MENU)
    time.sleep(0.8)


def click_home_button():
    """Click HOME button in pause menu (triggers ad)."""
    print("[game] clicking HOME button (triggers ad)...")
    tap(*HOME_BTN)


def click_retry_button():
    """Click RETRY button in pause menu (triggers ad)."""
    print("[game] clicking RETRY button (triggers ad)...")
    tap(*RETRY_BTN)


def trigger_ad_button(button_type="home"):
    """Click pause menu then HOME or RETRY to trigger an ad."""
    global needs_lvl_click

    # Open pause menu
    click_pause_menu()

    # Click the appropriate button to trigger ad
    if button_type == "home":
        click_home_button()
        needs_lvl_click = True  # Need LVL after HOME
    else:  # retry
        click_retry_button()
        needs_lvl_click = False  # RETRY keeps us in game mode

    return True


# ===============================================================
# ===================== MAIN AD CYCLE ===========================
# ===============================================================


def run_one_ad_cycle():
    """
    Run one complete ad cycle:
    1. Click LVL (if needed)
    2. Click pause -> button (triggers ad)
    3. Wait for ad to appear
    4. AGGRESSIVELY clear ad with multiple methods
    5. Repeat
    """
    global ad_cycle, button_mode, needs_lvl_click

    print(f"\n{'='*60}")
    print(f"[CYCLE {ad_cycle + 1}] using {button_mode.upper()} button")
    print(f"{'='*60}")

    # If we need LVL (after HOME button or app restart), click it
    if needs_lvl_click:
        click_lvl_button()
        needs_lvl_click = False
        time.sleep(0.5)

    # Trigger ad with button
    trigger_ad_button(button_mode)

    # Wait for ad to appear
    print(f"[ad] waiting {AD_WAIT_AFTER_BUTTON}s for ad to appear...")
    time.sleep(AD_WAIT_AFTER_BUTTON)

    # Handle/clear the ad AGGRESSIVELY
    cleared = handle_ads()

    # Check if we're back in game
    if cleared and not is_ad_playing():
        print(f"[SUCCESS] ✅ ad cycle {ad_cycle + 1} complete!")
        ad_cycle += 1

        # Alternate buttons
        button_mode = "retry" if button_mode == "home" else "home"

        return True
    else:
        print("[warning] ⚠️ cycle incomplete, will retry")
        return False


# ===============================================================
# ========================= MAIN LOOP ===========================
# ===============================================================


def log_dumpsys_cycles(n):
    """Collect top-activity values for `n` cycles and print them."""
    print(f"[log-dumpsys] collecting {n} cycles of top activity...")
    for i in range(n):
        top = get_top_activity()
        print(f"[{i+1}] top_activity={top}")
        time.sleep(1)


def main(argv=None):
    global needs_lvl_click, DRY_RUN, LOG_DUMPSYS, DEFAULT_DEVICE

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print adb commands instead of executing them")
    parser.add_argument("--log-dumpsys", type=int, default=0, help="Collect top-activity values for N cycles and exit")
    parser.add_argument("--device", type=str, default=DEFAULT_DEVICE, help="ADB device serial to use")
    args = parser.parse_args(argv)

    DRY_RUN = args.dry_run
    LOG_DUMPSYS = args.log_dumpsys
    DEFAULT_DEVICE = args.device

    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

    boot_win_adb_once()
    print("\n" + "="*60)
    print("🎈 BALLOON MASTER 3D - WATCHDOG AD CLEARING")
    print("="*60)
    print(f"[config] device: {DEFAULT_DEVICE}")
    print(f"[config] package: {GAME_PACKAGE}")
    print(f"[config] starting button: {button_mode.upper()}")
    print("\n[strategy] WATCHDOG MODE - always clear, no detection:")
    print("  1. minimize & monkey relaunch (ALWAYS FIRST)")
    print("  2. back button burst (4-6 random)")
    print("  3. home button burst")
    print("  4. app switcher clear")
    print("  5. mega escape sequence (for sticky)")
    print("  6. force stop (nuclear)")
    print("="*60 + "\n")

    if LOG_DUMPSYS > 0:
        log_dumpsys_cycles(LOG_DUMPSYS)
        return 0

    # Initial launch
    print("[setup] force stopping and relaunching app...")
    force_stop_pkg(GAME_PACKAGE)
    time.sleep(1.0)
    relaunch_game()
    time.sleep(GAME_READY_DELAY_SEC)

    # Give game extra time to fully load before any taps
    print("[setup] letting game fully load before starting...")
    time.sleep(6.0)

    # ALWAYS click LVL first to enter game mode
    print("[setup] initial LVL button click to enter game...")
    click_lvl_button()
    needs_lvl_click = False

    try:
        while True:
            success = run_one_ad_cycle()

            # Random cooldown to avoid patterns
            cooldown = random.uniform(*CYCLE_COOLDOWN_SEC)
            print(f"[cooldown] waiting {cooldown:.2f}s before next cycle...")
            time.sleep(cooldown)

            if not success:
                # If cycle failed, extra wait
                print("[retry] extra wait after failed cycle...")
                time.sleep(2)

    except KeyboardInterrupt:
        print("\n[STOP] script stopped by user")
    except Exception as e:
        print(f"\n[ERROR] script crashed: {e}")
        print(traceback.format_exc())


if __name__ == "__main__":
    sys.exit(main())
