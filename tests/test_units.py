"""Czix unit tests — runnable with pytest OR plain `python3 tests/test_units.py`."""
import os
import pathlib
import sys
import tempfile
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
os.environ.setdefault("XDG_STATE_HOME",
                      tempfile.mkdtemp(prefix="czix-test-state-"))
os.environ.setdefault("XDG_CONFIG_HOME",
                      tempfile.mkdtemp(prefix="czix-test-config-"))

from czix import trace as czix_trace
from czix.apk import (filter_split_abi, is_apk,   # noqa: E402
                      normalize_bundle)
from czix.cli import _vkey                               # noqa: E402
from czix.config import pin_trusted, read_trusted        # noqa: E402
from czix.elfdyn import parse as elf_parse               # noqa: E402
from czix.sources.archiveorg import _parse_version       # noqa: E402
from czix.surface import _categorize                     # noqa: E402
from czix.waydroid import PROPS                          # noqa: E402


def test_bundle_base_first():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="czix-test-"))
    fake = tmp / "app.xapk"
    with zipfile.ZipFile(fake, "w") as z:
        z.writestr("manifest.json", b'{"package":"com.roblox.client"}')
        z.writestr("base.apk", b"M" * 5000)
        z.writestr("config.arm64_v8a.apk", b"S")
        z.writestr("x_categorical_foo.apk", b"X")
    out = normalize_bundle(fake, work_dir=tmp)
    assert [o.name for o in out] == ["base.apk", "x_categorical_foo.apk",
                                     "config.arm64_v8a.apk"]
    assert not is_apk(fake)  # the container itself is not an apk


def test_bundle_named_base_first():
    """Real XAPKs name the base freely - it must still sort first."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="czix-test-"))
    fake = tmp / "app.xapk"
    with zipfile.ZipFile(fake, "w") as z:
        z.writestr("manifest.json", b'{"package":"com.roblox.client"}')
        z.writestr("com.roblox.client.apk", b"B" * 9000)   # the base
        z.writestr("config.arm64_v8a.apk", b"S")           # split
        z.writestr("config.mdpi.apk", b"D")
    out = normalize_bundle(fake, work_dir=tmp)
    assert [o.name for o in out] == ["com.roblox.client.apk",
                                     "config.arm64_v8a.apk", "config.mdpi.apk"]


def test_version_compare():
    assert _vkey("2.744.1081") == (2, 744, 1081)
    assert _vkey("2.737.1584") < _vkey("2.744.1081")
    assert _vkey("2.750") < _vkey("2.750.1")
    assert _vkey(None) is None


def test_trust_tofu():
    pin_trusted("com.test.thing", "AB" * 32, "1.2.3")
    t = read_trusted("com.test.thing")
    assert t and t["cert_sha256"] == "ab" * 32 and t["version"] == "1.2.3"
    assert read_trusted("com.other.thing") is None


def test_elf_parse_on_system_libs():
    import glob
    candidates = (glob.glob("/usr/lib/libc.so*")
                  + glob.glob("/usr/lib/x86_64-linux-gnu/libc.so*")
                  + glob.glob("/usr/lib/libz.so*")
                  + glob.glob("/usr/lib/x86_64-linux-gnu/libz.so*"))
    tested = 0
    for path in candidates:
        raw = open(path, "rb").read()
        if not raw.startswith(b"\x7fELF"):
            continue  # e.g. glibc's text-format linker script
        info = elf_parse(raw)
        assert info["machine"] == "x86_64"
        assert info["needed"], f"{path} should report DT_NEEDED"
        assert info["exported"], f"{path} should export symbols"
        tested += 1
    assert tested, "expected at least one parseable system ELF"


def test_archive_version_sort():
    assert _parse_version("x-2.154.47738.apk") == (2, 154, 47738)
    assert _parse_version("unknown-format.apk") == (0, 0, 0)


def test_categorize():
    assert _categorize("Java_com_roblox_client_A_b") == "java-bridge"
    assert _categorize("vkCreateInstance") == "vulkan"
    assert _categorize("eglCreateContext") == "egl-window"
    assert _categorize("glShaderSource") == "gles"
    assert _categorize("AAudioStreamBuilder_openStream") == "audio"
    assert _categorize("AMediaCodec_configure") == "media-codecs"
    assert _categorize("__system_property_get") == "props"
    assert _categorize("malloc") == "bionic-cxx-std"
    assert _categorize("curses_unknown_platform_thing") == "other-platform-relevant"


def test_filter_split_abi():
    names = ["base.apk", "config.arm64_v8a.apk", "config.armeabi_v7a.apk",
             "config.xxhdpi.apk", "split_config.arm64_v8a.apk", "weird.apk"]
    paths = [pathlib.Path(n) for n in names]
    kept, dropped = filter_split_abi(paths, "arm64-v8a")
    assert dropped == ["config.armeabi_v7a.apk"]
    assert [p.name for p in kept] == ["base.apk", "config.arm64_v8a.apk",
                                      "config.xxhdpi.apk",
                                      "split_config.arm64_v8a.apk",
                                      "weird.apk"]


def test_trace_collect_and_render():
    log = (
        "e/linker: dlopening /system/lib64/libEGL.so\n"
        "ActivityTaskManager: Displayed com.roblox.client/act.Main +1s233ms\n"
        "ActivityTaskManager: Displayed com.roblox.client/act.Main2 +412ms\n"
        "VulkanDevice: vkCreateInstance unsupported on GLES path\n"
        "AudioTrack: opened stream for voice chat\n"
        "SQLite: scribbles\n")
    rep = czix_trace.collect(log)
    assert rep["total_lines"] == 6
    assert rep["loaded_libraries"] == ["libEGL.so"]
    assert rep["streams"]["vulkan"] == 1
    assert rep["streams"]["audio"] == 1
    assert czix_trace.parse_displayed(log) == [
        ("com.roblox.client/act.Main", 1233),
        ("com.roblox.client/act.Main2", 412)]
    assert czix_trace.render_terminal(rep).startswith("runtime trace")
    assert czix_trace.render_markdown(rep).startswith("# Runtime API trace")
    assert czix_trace.json_dumps(rep).strip().startswith("{")

    # static-surface correlation
    surf = {"abis": {"arm64-v8a": {
        "libraries": {"libEGL.so": {"machine": "aarch64", "class": 64,
                                    "imported": 10, "exported": 5}},
        "cats": {"egl-window": ["eglCreateContext"]},
        "needed": []}}}
    rep2 = czix_trace.collect(log, surface_report=surf)
    assert rep2["fired_categories"]["libEGL.so"] == ["egl-window"]
    assert rep2["unmatched_libraries"] == 0
    assert rep2["categories"] == ["egl-window"]


def test_trace_load_library_variant():
    loads = czix_trace.parse_lib_loads('app: System.loadLibrary("libfoo.so")')
    assert list(loads) == ["libfoo.so"]


def test_props_documented():
    assert PROPS
    for name, desc in PROPS:
        assert name.startswith("persist.waydroid.")
        assert len(desc) > 10


def main() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
