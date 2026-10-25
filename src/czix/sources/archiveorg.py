"""Archive.org resolver — 'ROBLOX Android Archive' item com.roblox.client.

Keeps historical APKs; may lag behind the Play Store release. Useful as a
fallback when mirrors are unreachable.
"""
import json
import re
import urllib.parse
import urllib.request

from ..apk import UA

ITEM = "com.roblox.client"
META = f"https://archive.org/metadata/{ITEM}"
DL = f"https://archive.org/download/{ITEM}"


def _parse_version(name: str) -> tuple[int, int, int]:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", name)
    return tuple(map(int, m.groups())) if m else (0, 0, 0)


def resolve(package: str, cfg: dict) -> dict:
    req = urllib.request.Request(META, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            meta = json.loads(resp.read())
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"archive.org unreachable ({e}).") from e

    all_files = [f["name"] for f in meta.get("files", [])]
    # stay strictly inside the official-app namespace; reject lookalikes
    # (e.g. "com.tencent.roblox-*" uploads that exist in some archives).
    official = [f for f in all_files
                if f.lower().startswith("com.roblox.client")
                and f.lower().endswith((".apk", ".zip"))]
    roblox_any = [f for f in all_files
                  if "roblox" in f.lower()
                  and f.lower().endswith((".apk", ".zip"))]
    files = official or roblox_any
    if not files:
        raise RuntimeError(f"No official Roblox APKs found in item {ITEM}.")
    best = max(files, key=_parse_version)
    url = f"{DL}/{urllib.parse.quote(best)}"
    return {
        "url": url,
        "headers": {"User-Agent": UA},
        "source": "archive",
        "note": f"picked {best} (newest by version number; archive may lag)",
    }
