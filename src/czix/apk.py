"""APK machinery: download, validate, unpack bundles (XAPK/APKS), inspect,
verify signing cert with apksigner. Pure stdlib."""
import hashlib
import re
import shutil
import subprocess
import threading
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

UA = "Czix/0.1 (unofficial Roblox-on-Linux apk launcher; +https://czix.example) Python-urllib"
CHUNK = 1024 * 1024


def run_with_budget(fn, budget_s: float, *args, **kwargs):
    """Run fn in a daemon thread, abandon it after budget_s.

    Daemon threads never block interpreter exit, so a black-holed DNS lookup
    cannot hang the CLI forever (signals can't interrupt getaddrinfo).
    """
    box: dict = {}

    def work():
        try:
            box["ok"] = fn(*args, **kwargs)
        except BaseException as e:  # re-raised in main thread
            box["err"] = e

    t = threading.Thread(target=work, daemon=True)
    t.start()
    t.join(budget_s)
    if t.is_alive():
        raise TimeoutError(
            "network call abandoned after %.0fs (DNS dead? offline?). "
            "Try `--source archive`, a manual APK path, or check connectivity."
            % budget_s)
    if "err" in box:
        raise box["err"]
    return box.get("ok")


@dataclass
class ApkInfo:
    path: Path
    name: str = ""
    size: int = 0
    sha256: str = ""
    package: str | None = None
    version_name: str | None = None
    version_code: str | None = None
    abis: list = field(default_factory=list)
    is_split: bool = False

    def describe(self) -> str:
        lines = [
            f"file:     {self.path}",
            f"sha256:   {self.sha256[:16]}{'…' if self.sha256 else ''}",
            f"size:     {self.size/1048576:.1f} MiB",
        ]
        if self.package:
            lines.append(f"package:  {self.package}")
        if self.version_name:
            vc = f" ({self.version_code})" if self.version_code else ""
            lines.append(f"version:  {self.version_name}{vc}")
        if self.abis:
            lines.append(f"abis:     {', '.join(self.abis)}")
        if self.is_split:
            lines.append("note:     part of a split-APK bundle")
        return "\n".join(lines)


def is_apk(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            return "AndroidManifest.xml" in z.namelist()
    except (zipfile.BadZipFile, IsADirectoryError):
        return False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def which(name: str) -> str | None:
    return shutil.which(name)


def _aapt_inspect(path: Path, info: ApkInfo) -> None:
    for tool in ("aapt2", "aapt"):
        exe = which(tool)
        if not exe:
            continue
        try:
            out = subprocess.run([exe, "dump", "badging", str(path)],
                                 capture_output=True, text=True, timeout=60)
            if out.returncode != 0:
                continue
            m = re.search(r"package: name='([^']+)' "
                          r"versionCode='([^']+)' "
                          r"versionName='([^']+)'", out.stdout)
            if m:
                info.package, info.version_code, info.version_name = m.groups()
            nc = re.search(r"^native-code: (.+)$", out.stdout, re.M)
            if nc:
                info.abis = nc.group(1).split()
            return
        except (OSError, subprocess.TimeoutExpired):
            continue


def inspect(path: Path) -> ApkInfo:
    info = ApkInfo(path=path, name=path.name, size=path.stat().st_size)
    info.sha256 = sha256_file(path)
    if is_apk(path):
        _aapt_inspect(path, info)
        if not info.version_name:
            # no aapt? best-effort from the file name (mirrors embed version)
            m = re.search(r"(\d+(?:\.\d+){1,3})", path.name)
            if m:
                info.version_name = m.group(1)
        try:
            with zipfile.ZipFile(path) as z:
                if not info.abis:
                    info.abis = sorted({n.split("/")[1]
                                        for n in z.namelist()
                                        if n.startswith("lib/") and len(n.split("/")) > 2})
        except zipfile.BadZipFile:
            pass
    return info


# ---- download --------------------------------------------------------------

def _filename_from_headers(resp, url: str) -> str:
    cd = resp.headers.get("Content-Disposition", "")
    m = re.search(r"filename\*?=(?:UTF-8'')?\"?([^\";\r\n]+)", cd)
    if m:
        return Path(m.group(1)).name
    name = urllib.parse.urlparse(url).path.rsplit("/", 1)[-1]
    return name or "download.bin"


def download(url: str, dest_dir: Path, headers: dict | None = None,
             timeout_s: int = 600, quiet: bool = False) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    open_budget = int(__import__("os").environ.get("CZIX_OPEN_TIMEOUT", "45"))
    resp = run_with_budget(
        lambda: urllib.request.urlopen(req, timeout=timeout_s), open_budget)
    with resp:
        fname = _filename_from_headers(resp, str(resp.geturl()))
        dest = dest_dir / fname
        total = int(resp.headers.get("Content-Length") or 0)
        got = 0
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as f:
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if total and not quiet and (got // CHUNK) % 16 == 0:
                    print(f"\r  {got/1048576:7.1f} / {total/1048576:.1f} MiB",
                          end="", flush=True)
        if not quiet:
            print(f"\r  {got/1048576:.1f} MiB downloaded        ")
        tmp.rename(dest)
        return dest


# ---- bundle handling (XAPK / APKS / zipped APK) ----------------------------

def normalize_bundle(path: Path, work_dir: Path | None = None,
                     _depth: int = 0) -> list[Path]:
    """Resolve a downloaded artifact into one or more installable .apk paths.

    Handles: plain .apk, .xapk/.apks (zip of apk splits), and archives that
    merely contain an apk (e.g. Archive.org wrapper zips).
    """
    path = path.resolve()
    suffix = path.suffix.lower()
    is_single_apk = suffix == ".apk" and is_apk(path)
    if is_single_apk:
        return [path]
    if _depth > 2 or not zipfile.is_zipfile(path):
        return []

    out_dir = (work_dir or path.with_suffix("")) / path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        apk_names = [n for n in names if n.lower().endswith(".apk")]
        if not apk_names:
            # maybe *this* zip has a nested container
            nested = [n for n in names
                      if n.lower().endswith((".xapk", ".apks", ".zip"))
                      and not n.endswith("/")]
            if len(nested) != 1:
                return []
            inner = out_dir / Path(nested[0]).name
            inner.write_bytes(z.read(nested[0]))
            return normalize_bundle(inner, work_dir, _depth + 1)

        paths: list[Path] = []
        for n in sorted(apk_names, key=lambda n: (n == "base.apk", z.getinfo(n).file_size)):
            target = out_dir / Path(n).name
            target.write_bytes(z.read(n))
            paths.append(target)
    # order: base first → good for pm install
    return sorted(paths, key=lambda p: 0 if p.name == "base.apk" else 1)


def verify_signature(path: Path) -> str | None:
    """Return SHA-256 cert digest of an (x)apk, or None if apksigner missing."""
    exe = which("apksigner")
    if not exe:
        return None
    apks = [path] if is_apk(path) else normalize_bundle(path)
    if not apks:
        return None
    try:
        out = subprocess.run([exe, "verify", "--print-certs", str(apks[0])],
                             capture_output=True, text=True, timeout=120)
        m = re.search(r"Certificate SHA-256 digest:\s*([0-9a-fA-F]+)", out.stdout)
        return m.group(1).lower() if m else None
    except (OSError, subprocess.TimeoutExpired):
        return None
