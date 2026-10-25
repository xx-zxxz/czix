"""Config + TOFU trust-pin storage (no third-party deps)."""
import json
import os
from pathlib import Path

SECTION_NAME = "czix"

DEFAULTS = {
    "package": "com.roblox.client",
    "source": "apkpure",
    "download_dir": "~/.local/share/czix/apks",
    "timeout_s": 600,
}


def config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "czix" / "config.toml"


def state_dir() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "state"
    out = base / "czix"
    out.mkdir(parents=True, exist_ok=True)
    return out


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    p = config_path()
    if p.exists():
        text = p.read_text(encoding="utf-8")
        try:
            import tomllib  # py3.11+
            data = tomllib.loads(text)
            data = data.get(SECTION_NAME, data)
        except ImportError:
            # minimal fallback parser for our flat keys
            data = {}
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("[") or not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    data[k.strip()] = v.strip().strip('"')
        for k in DEFAULTS:
            if k in data:
                cfg[k] = data[k]
    cfg["download_dir"] = str(Path(cfg["download_dir"]).expanduser())
    Path(cfg["download_dir"]).mkdir(parents=True, exist_ok=True)
    return cfg


def save_state(key: str, value: dict) -> None:
    p = state_dir() / f"{key}.json"
    p.write_text(json.dumps(value, indent=2), encoding="utf-8")


def read_state(key: str) -> dict | None:
    p = state_dir() / f"{key}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


# ---- TOFU signature pinning -------------------------------------------------

def pin_trusted(package: str, cert_sha256: str, version: str | None = None) -> None:
    save_state("trusted", {
        "package": package,
        "cert_sha256": cert_sha256.lower(),
        "version": version,
        "pinned_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
    })


def read_trusted(package: str) -> dict | None:
    d = read_state("trusted")
    if d and d.get("package") == package:
        return d
    return None


def find_on_path(name: str) -> str | None:
    """Return the absolute path of a helper binary, or None."""
    import shutil
    return shutil.which(name)
