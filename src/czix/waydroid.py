"""Waydroid integration: status, install (incl. split-APK streaming), launch.
Commands are prefixed with flatpak-spawn when running inside a Flatpak sandbox.
"""
import os
import re
import shutil
import subprocess
from pathlib import Path

HINT = (
    "Waydroid not ready. On Arch:\n"
    "    sudo pacman -S waydroid\n"
    "    sudo waydroid init                 # fetches Android image\n"
    "    sudo systemctl start waydroid-container\n"
    "    waydroid session start             # run inside your desktop session\n"
)


def base_cmd() -> list:
    """flatpak-spawn --host lets us talk to host Waydroid inside the sandbox."""
    if os.environ.get("FLATPAK_ID"):
        return ["flatpak-spawn", "--host"]
    return []


def waydroid() -> list | None:
    exe = shutil.which("waydroid")
    return None if not exe else base_cmd() + [exe]


def run(args: list, timeout: int = 300, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(base_cmd() + args, capture_output=True,
                          text=True, timeout=timeout, **kw)


def status_text() -> dict:
    """Parse `waydroid status` into {'session': 'RUNNING', ...} or {}."""
    wd = waydroid()
    if not wd:
        return {}
    try:
        p = run(["status"], timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    out = (p.stdout + p.stderr)
    d = {k.lower(): v for k, v in re.findall(r"(Session|Container|Service):\s+([A-Z]+)", out)}
    return d


def status() -> tuple[bool, str]:
    wd = waydroid()
    if not wd:
        return False, "waydroid not found on PATH (or via flatpak-spawn)"
    try:
        p = run(["status"])
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, f"waydroid status failed: {e}"
    out = (p.stdout + p.stderr).strip()
    if "RUNNING" in out.upper():
        return True, f"running ({out.splitlines()[0] if out else 'ok'})"
    return False, f"not running: {out}"


def install(apks: list[Path]) -> bool:
    """Install one apk, or stream a split bundle via `pm install-create`."""
    wd = waydroid()
    if not wd:
        print(HINT)
        return False
    ok, msg = status()
    if not ok:
        print(f"Waydroid is not running: {msg}\n{HINT}")
        return False

    total = sum(a.stat().st_size for a in apks)
    try:
        if len(apks) == 1:
            p = run(["app", "install", str(apks[0])], timeout=900)
            if p.returncode != 0:
                print(p.stdout + p.stderr)
                return False
            print("Installed (single APK).")
            return True

        # ---- split APK installation --------------------------------
        print(f"Streaming {len(apks)} splits ({total/1048576:.0f} MiB) …")
        p = run(["shell", "--", "pm", "install-create", "-r", "-S", str(total)])
        if p.returncode != 0:
            print(p.stdout + p.stderr)
            return False
        m = re.search(r"\[([A-Za-z0-9_.\-]+)\]", p.stdout)
        if not m:
            print(f"install-create gave no session id: {p.stdout}{p.stderr}")
            return False
        sess = m.group(1)
        for apk in apks:
            name = apk.name
            size = apk.stat().st_size
            cmd = wd + ["shell", "--",
                        f"pm install-write -S {size} {sess} {name} -"]
            with open(apk, "rb") as f:
                w = subprocess.run(cmd, stdin=f, capture_output=True,
                                   text=True, timeout=900)
            if w.returncode != 0:
                print(f"install-write failed for {name}: {w.stdout}{w.stderr}")
                return False
        p = run(["shell", "--", "pm", "install-commit", sess])
        if p.returncode != 0:
            print(p.stdout + p.stderr)
            return False
        print("Installed (split bundle).")
        return True
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"Install failed: {e}")
        return False


def launch(package: str) -> bool:
    ok, msg = status()
    if not ok:
        print(f"Waydroid is not running: {msg}\n{HINT}")
        return False
    try:
        p = run(["app", "launch", package])
        if p.returncode == 0:
            return True
        print(p.stdout + p.stderr)
        print("Hint: was Roblox installed with `czix install`, and does the "
              "container have network access?")
        return False
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"Launch failed: {e}")
        return False


# ---- environment bootstrap (Sober-style click-to-play support) --------------

def _pkexec(args: list, timeout: int = 300) -> bool:
    exe = shutil.which("pkexec")
    if not exe:
        return False
    try:
        p = subprocess.run([exe] + args, capture_output=True, text=True,
                           timeout=timeout)
        return p.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _poll(fn, timeout_s: int, interval: float = 1.0) -> bool:
    import time
    end = time.time() + timeout_s
    while time.time() < end:
        if fn():
            return True
        time.sleep(interval)
    return False


def _container_running() -> bool:
    return status_text().get("container") == "RUNNING"


def _session_running() -> bool:
    return status_text().get("session") == "RUNNING"


def ensure_environment(auto: bool = True) -> tuple[bool, str]:
    """Get to: container up + session up + single-window mode. Best effort."""
    wd = waydroid()
    if not wd:
        return False, "waydroid not found"
    st = status_text()
    if st.get("container", "").startswith("NOT RUNNING") or \
       (st and st.get("container") != "RUNNING"):
        if not auto:
            return False, "waydroid container is not running"
        print("Starting waydroid container (needs authorization via pkexec)…")
        if _pkexec(["systemctl", "start", "waydroid-container"]):
            if not _poll(_container_running, 20):
                return False, "container start command ran but state stays: " \
                              + status_text().get("container", "?")
        else:
            return False, "could not start container; run once: " \
                          "sudo systemctl start waydroid-container"
    if not _image_present():
        if not auto:
            return False, "waydroid image missing - need `sudo waydroid init`"
        if not init_image():
            return False, ("could not initialize the waydroid image; run once: "
                           "sudo waydroid init (downloads the system image)")
        print("  container image initialized.")

    if not _session_running():
        if not auto:
            return False, "waydroid session is not running"
        # session start is a long-lived daemon; detach it
        try:
            subprocess.Popen(waydroid() + ["session", "start"],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        except OSError as e:
            return False, f"could not start session: {e}"
        if not _poll(_session_running, 25):
            return False, "session did not come up (are you in a desktop " \
                          "session? run `waydroid session start` manually)"

    # single-window mode ≈ Sober UX: each app opens in its own window
    if _prop_get("persist.waydroid.multi_windows") not in ("true",):
        if not _prop_set("persist.waydroid.multi_windows", "true"):
            print("  note: could not enable multi-window mode. For single-window "
                  "launches run: sudo waydroid prop set "
                  "persist.waydroid.multi_windows true")
    return True, "ready"


def _prop_get(name: str) -> str:
    try:
        p = run(["prop", "get", name], timeout=30)
        return (p.stdout or p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


prop_get = _prop_get  # public alias for the `czix prop` command group


def _prop_set(name: str, value: str) -> bool:
    """Try user-level set; fall back to pkexec."""
    try:
        p = run(["prop", "set", name, value], timeout=30)
        if p.returncode == 0:
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    return _pkexec(["waydroid", "prop", "set", name, value])


prop_set = _prop_set  # public alias for the `czix prop` command group


def abilist() -> list[str]:
    """CPU ABIs the container reports (ro.product.cpu.abilist). Empty = unknown."""
    try:
        p = run(["shell", "--", "getprop", "ro.product.cpu.abilist"],
                timeout=30)
        return [a for a in (p.stdout or "").strip().split(",") if a]
    except (OSError, subprocess.TimeoutExpired):
        return []


# Curated, documented Waydroid properties - shown by `czix prop list`.
PROPS = (
    ("persist.waydroid.multi_windows",
     "false = every app in its own window (Sober-like); true = one big window"),
    ("persist.waydroid.fake_touch",
     "treat mouse input as touch (some games only accept touch)"),
    ("persist.waydroid.cursor_on_subsurface",
     "keep a visible cursor inside the container surface"),
    ("persist.waydroid.width", "container display width in pixels"),
    ("persist.waydroid.height", "container display height in pixels"),
)


def _image_present() -> bool:
    img = "/var/lib/waydroid/images/system.img"
    if os.path.exists(img):
        return True
    try:  # inside a Flatpak sandbox: ask the host
        r = subprocess.run(base_cmd() + ["test", "-f", img],
                           capture_output=True, timeout=30)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def init_image(timeout_s: int = 1800) -> bool:
    """Run `waydroid init` via pkexec to download the container image."""
    print("Running `waydroid init` (system image download, "
          "authorization prompt - can take several minutes)…")
    if _pkexec(["waydroid", "init"], timeout=timeout_s):
        if _poll(_image_present, 60):
            return True
    return _image_present()


def installed_version(package: str) -> str | None:
    """versionName of `package` inside the container, or None."""
    try:
        p = run(["shell", "--", "pm", "dump", package], timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"versionName=([0-9][^\s]+)", p.stdout or "")
    return m.group(1) if m else None


def doctor(fix: bool = False) -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    wd = waydroid()
    checks.append(("waydroid binary", bool(wd), HINT if not wd else "ok"))
    if wd:
        img = _image_present()
        checks.append(("container image", img, "ok" if img else
                       "--fix runs `waydroid init` (pkexec; system-image "
                       "download takes a while)"))
        if fix and not img:
            img = init_image()
            checks.append(("container image (after fix)", img,
                           "ok" if img else "failed"))
        st = status_text()
        cok = st.get("container") == "RUNNING"
        sok = st.get("session") == "RUNNING"
        checks.append(("waydroid container", cok,
                       "ok" if cok else "--fix will pkexec systemctl start it"))
        checks.append(("waydroid session", sok,
                       "ok" if sok else "--fix will start it (desktop needed)"))
        mw = _prop_get("persist.waydroid.multi_windows")
        checks.append(("single-window mode", mw == "true",
                       "ok" if mw == "true" else
                       "sudo waydroid prop set persist.waydroid.multi_windows true"))
        if fix:
            ensure_environment(auto=True)
            st = status_text()
            cok = st.get("container") == "RUNNING"
            sok = st.get("session") == "RUNNING"
            checks.append(("waydroid container (after fix)", cok, "ok" if cok else "failed"))
            checks.append(("waydroid session (after fix)", sok, "ok" if sok else "failed"))
    for tool, hint in (("apksigner", "install 'apksigner' (Android build-tools) "
                                     "for signature pinning"),
                       ("aapt", "optional: install 'aapt' for richer APK info"),
                       ("curl", None)):
        exe = shutil.which(tool)
        checks.append((tool, bool(exe), "ok" if exe else (hint or "optional")))
    return checks
