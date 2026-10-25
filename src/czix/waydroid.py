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


def doctor() -> list[tuple[str, bool, str]]:
    checks: list[tuple[str, bool, str]] = []
    wd = waydroid()
    checks.append(("waydroid binary", bool(wd), HINT if not wd else "ok"))
    if wd:
        ok, msg = status()
        checks.append(("waydroid running", ok, "ok" if ok else msg))
    for tool, hint in (("apksigner", "install 'apksigner' (Android build-tools) "
                                     "for signature pinning"),
                       ("aapt", "optional: install 'aapt' for richer APK info"),
                       ("curl", None)):
        exe = shutil.which(tool)
        checks.append((tool, bool(exe), "ok" if exe else (hint or "optional")))
    return checks
