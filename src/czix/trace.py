"""Phase-1 helper: runtime API trace + startup benchmark.

`czix trace` captures the container's logcat (while Roblox runs), extracts
native-library load events and graphics/audio/input stream activity, and
correlates loaded libraries with the static report from `czix surface --json`.

`czix bench` launches the client and reads the Android framework's own
"Displayed …" activity-timing line, so start-up time is measured by the
platform rather than guessed.

Only the user's own container logs are inspected; nothing is uploaded or
shipped. No Roblox code or assets are reproduced anywhere in this module.
"""
import json
import re
import time

# logcat lines that indicate a native library got loaded into the process
_LIB_LOAD = re.compile(
    r"\b(?:[Dd]lopen(?:ing)?|linker|[Ll]ibrary|System\.loadLibrary)[^\n]*?"
    r"(lib[\w]+(?:[-.][\w]+)*\.so)")

# logcat lines hinting at specific subsystem activity
_STREAM_HINTS = (
    ("egl-window", r"EGLNativeWindow|eglQuerySurface|eglInitialize|ANativeWindow_"),
    ("gles", r"OpenGLRenderer|libGLESv2|GLES2|GLESv2|glRender"),
    ("vulkan", r"Vulkan|VULKAN|vkQueuePresent|vkAcquire|\bvk[A-Z]"),
    ("audio", r"AAudio|AudioTrack|AudioFlinger|opensl|audio_hw"),
    ("media-codecs", r"AMediaCodec|MediaCodec|OMX\.|c2\."),
    ("sensors", r"SensorManager|sensorHub|accelerometer|rotation_vector"),
    ("camera", r"CameraManager|camera2|CameraService|CameraX"),
    ("java-bridge", r"UnsatisfiedLinkError|Java_[a-z]"),
)

# Android reports activity start duration as "Displayed <pkg>/<act> +1s234ms"
_DISPLAYED = re.compile(r"Displayed\s+(\S+)[^\n]*?\+(?:(\d+)s)?(\d+)ms")


def parse_lib_loads(text: str) -> dict[str, list]:
    """lib -> list of the raw logcat lines that mentioned its load."""
    loads: dict[str, list] = {}
    for line in text.splitlines():
        m = _LIB_LOAD.search(line)
        if m:
            lib = m.group(1)
            loads.setdefault(lib, []).append(line.strip())
    return loads


def parse_displayed(logtext: str) -> list[tuple[str, int]]:
    """(activity-component, start_ms) pairs, in log order."""
    out = []
    for line in logtext.splitlines():
        m = _DISPLAYED.search(line)
        if m:
            ms = int(m.group(2) or 0) * 1000 + int(m.group(3))
            out.append((m.group(1), ms))
    return out


def _streams(lines: list) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in lines:
        for cat, pat in _STREAM_HINTS:
            if re.search(pat, line):
                out[cat] = out.get(cat, 0) + 1
    return out


def _join_static(loads: dict[str, list], surface_report: dict) -> dict:
    """Map each runtime-loaded lib to its static import categories."""
    static: dict[str, list] = {}
    for _abi, slot in (surface_report.get("abis") or {}).items():
        for lib_name in (slot.get("libraries") or {}):
            static[lib_name] = [c for c in (slot.get("cats") or {})
                                if c not in ("bionic-cxx-std",
                                             "other-platform-relevant")]
    fired = {}
    unmatched = 0
    for lib in loads:
        cats = static.get(lib)
        if cats is None:
            base = re.sub(r"(?:-linux|-android|-\d+)+\.so$", ".so", lib)
            cats = static.get(base)
        if cats:
            fired[lib] = sorted(cats) or ["bionic-cxx-std"]
        else:
            unmatched += 1
    return {"fired": fired, "unmatched": unmatched}


def collect(logtext: str, surface_report: dict | None = None,
            keep_lines: int = 40) -> dict:
    lines = logtext.splitlines()
    out = {
        "total_lines": len(lines),
        "loaded_libraries": [],
        "unmatched_libraries": 0,
        "streams": {},
        "categories": [],
        "interesting": [],
    }
    if not lines:
        return out
    loads = parse_lib_loads(logtext)
    out["streams"] = dict(sorted(_streams(lines).items(),
                                 key=lambda kv: -kv[1]))
    interesting_pat = re.compile(
        "|".join(f"(?:{p})" for _, p in _STREAM_HINTS)
        + r"|sig[0-9]|SIGILL|SIGSEGV|An exception occurred|FATAL EXCEPTION")
    out["interesting"] = [l for l in lines
                          if interesting_pat.search(l)][:keep_lines]
    out["loaded_libraries"] = sorted(loads)
    if surface_report:
        joined = _join_static(loads, surface_report)
        out["fired_categories"] = joined["fired"]
        out["unmatched_libraries"] = joined["unmatched"]
        out["categories"] = sorted({c
                                    for cats in joined["fired"].values()
                                    for c in cats})
    return out


# ---- capture ----------------------------------------------------------------

def capture_dump(lines: int = 20000) -> str:
    """Dump the tail of the container's logcat buffer."""
    from . import waydroid
    p = waydroid.run(["shell", "--", "logcat", "-d", "-t", str(lines)],
                     timeout=120)
    if p.returncode != 0:
        raise RuntimeError((p.stdout + p.stderr).strip()
                           or "logcat dump failed (is the session running?)")
    return p.stdout


def capture_live(seconds: int) -> str:
    """Record `logcat` output for `seconds` (kbd-free live trace)."""
    import subprocess
    from . import waydroid
    wd = waydroid.waydroid()
    if not wd:
        raise RuntimeError("waydroid not found")
    p = subprocess.Popen(wd + ["shell", "--", "logcat", "-T", "1"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, errors="replace")
    try:
        out, _ = p.communicate(timeout=seconds)
    except subprocess.TimeoutExpired as e:
        out = e.stdout or ""
        p.kill()
        p.wait()
    return out or ""


def measure_start(package: str, timeout_s: int = 120) -> int | None:
    """Launch `package` and return Android's reported start time in ms.

    Clears the logcat buffer first, so the "Displayed" line we find belongs
    to *this* launch (cold vs warm distinction is the caller's business).
    """
    from . import waydroid
    waydroid.run(["shell", "--", "logcat", "-c"], timeout=30)
    if not waydroid.launch(package):
        return None
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        p = waydroid.run(["shell", "--", "logcat", "-d", "-t", "800",
                          "-s", "ActivityTaskManager"], timeout=60)
        for comp, ms in parse_displayed(p.stdout or ""):
            if package in comp:
                return ms
        time.sleep(2)
    return None


# ---- rendering --------------------------------------------------------------

def render_terminal(rep: dict) -> str:
    o = ["runtime trace",
         f"  logcat lines scanned : {rep['total_lines']}",
         f"  native libs loaded   : {len(rep['loaded_libraries'])}"]
    if rep["loaded_libraries"]:
        o.append("    " + ", ".join(rep["loaded_libraries"]))
    streams = rep.get("streams") or {}
    if streams:
        o.append("  stream activity:")
        for cat, n in streams.items():
            o.append(f"    {cat:14}{n:6} log lines")
    if "fired_categories" in rep:
        o.append("  correlation with static surface (`czix surface --json`):")
        for lib, cats in sorted(rep["fired_categories"].items()):
            o.append(f"    {lib:36} {', '.join(cats)}")
        o.append(f"    unmatched runtime libs : {rep.get('unmatched_libraries', 0)}")
        if rep.get("categories"):
            o.append("    categories firing      : "
                     + ", ".join(rep["categories"]))
    if rep.get("interesting"):
        o.append(f"  notable log lines ({len(rep['interesting'])}):")
        for l in rep["interesting"]:
            o.append("    " + l)
    if not (rep["loaded_libraries"] or streams or rep.get("interesting")):
        o.append("  nothing notable yet - run Roblox, then retry `czix trace`")
    return "\n".join(o)


def render_markdown(rep: dict) -> str:
    o = ["# Runtime API trace", "",
         "Produced by `czix trace` from the container's own logcat buffer.",
         "Runtime log lines stay local - Czix never ships them.", "",
         f"- logcat lines scanned: **{rep['total_lines']}**",
         f"- native libraries loaded: "
         f"**{len(rep['loaded_libraries'])}**"]
    libs = rep.get("loaded_libraries") or []
    if libs:
        o += ["", "## Loaded native libraries", "",
              "| library |", "|---|"]
        o += [f"| `{l}` |" for l in libs]
    streams = rep.get("streams") or {}
    if streams:
        o += ["", "## Stream activity", "",
              "| category | log lines |", "|---|---|"]
        o += [f"| `{k}` | {n} |" for k, n in streams.items()]
    if "fired_categories" in rep:
        o += ["", "## Correlation with static surface", "",
              "| runtime library | static import categories |", "|---|---|"]
        o += [f"| `{lib}` | {', '.join('`' + c + '`' for c in cats) or '-'} |"
              for lib, cats in sorted(rep["fired_categories"].items())]
        o += ["",
              f"unmatched runtime libraries: "
              f"**{rep.get('unmatched_libraries', 0)}**"]
        if rep.get("categories"):
            o += ["", "categories seen firing: "
                  + ", ".join(f"`{c}`" for c in rep["categories"])]
    interesting = rep.get("interesting") or []
    if interesting:
        o += ["", "## Notable log lines", "", "```"]
        o += [l for l in interesting]
        o += ["```"]
    return "\n".join(o) + "\n"


def json_dumps(rep: dict) -> str:
    return json.dumps(rep, indent=2, sort_keys=True)
