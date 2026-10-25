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

from czix.apk import is_apk, normalize_bundle            # noqa: E402
from czix.cli import _vkey                               # noqa: E402
from czix.config import pin_trusted, read_trusted        # noqa: E402
from czix.elfdyn import parse as elf_parse               # noqa: E402
from czix.sources.archiveorg import _parse_version       # noqa: E402
from czix.surface import _categorize                     # noqa: E402


def test_bundle_base_first():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="czix-test-"))
    fake = tmp / "app.xapk"
    with zipfile.ZipFile(fake, "w") as z:
        z.writestr("manifest.json", b'{"package":"com.roblox.client"}')
        z.writestr("base.apk", b"M" * 5000)
        z.writestr("config.arm64_v8a.apk", b"S")
        z.writestr("x_categorical_foo.apk", b"X")
    out = normalize_bundle(fake, work_dir=tmp)
    assert [o.name for o in out] == ["base.apk", "config.arm64_v8a.apk",
                                     "x_categorical_foo.apk"]
    assert not is_apk(fake)  # the container itself is not an apk


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


def main() -> None:
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"  ✓ {name}")
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
