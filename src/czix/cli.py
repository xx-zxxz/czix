"""Czix CLI — fetch/verify/install/update/launch the Roblox Android client.

`czix play` is the Sober-style UX: guaranteed single command / double-click
behavior. It bootstraps the environment, installs Roblox on first run, keeps
it silently up to date, and launches the game in its own window.
"""
import argparse
import json
import os
import pathlib
import re
import sys

from . import __version__, apk, config, waydroid

SOURCES = {"apkpure", "archive"}

NOTICE_SHORT = (
    "Czix is unofficial and not affiliated with Roblox Corporation. Czix does "
    "not redistribute Roblox code; APKs are fetched from public mirrors of the "
    "official app. Use at your own risk — third-party clients are a ToS gray "
    "area and may lead to account actions. See `czix notice`."
)

_VERSION_RE = r"(\d+)\.?(\d+)?\.?(\d+)?"


def _resolve_source(source: str, package: str, cfg: dict) -> dict:
    if source == "apkpure":
        from .sources import apkpure
        return apkpure.resolve(package, cfg)
    if source == "archive":
        from .sources import archiveorg
        return archiveorg.resolve(package, cfg)
    raise SystemExit(f"unknown source {source!r}")


def _fetch_to_disk(cfg: dict, package: str, source: str,
                   dest_dir: pathlib.Path) -> tuple[list[pathlib.Path], dict]:
    """Resolve + download + normalize. Raises RuntimeError/TimeoutError."""
    import zipfile as _zf
    cand = _resolve_source(source, package, cfg)
    if not os.environ.get("CZIX_QUIET"):
        print(f"  {cand['note']}\nDownloading → {dest_dir}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    raw = apk.download(cand["url"], dest_dir, headers=cand["headers"],
                       timeout_s=int(cfg["timeout_s"]))
    apks = apk.normalize_bundle(raw, work_dir=dest_dir)
    if not apks:
        raise RuntimeError(f"{raw} is not a valid APK/bundle (HTML page? bad link?).")
    meta: dict = {}
    try:
        with _zf.ZipFile(raw) as z:
            if "manifest.json" in z.namelist():
                meta = json.loads(z.read("manifest.json"))
    except Exception:  # noqa: BLE001 — cosmetic metadata only
        pass
    if not os.environ.get("CZIX_QUIET"):
        for path_ in apks:
            print(apk.inspect(path_).describe())
            print("-" * 46)
    version = (apk.inspect(apks[0]).version_name
               or meta.get("version_name") or meta.get("vername"))
    return apks, {**meta, "version": version}


def _vkey(version: str | None):
    if not version:
        return None
    parts = re.findall(r"\d+", version)
    return tuple(int(p) for p in parts[:3]) if parts else None


def cmd_fetch(ns) -> int:
    cfg = config.load_config()
    package = ns.package or cfg["package"]
    source = ns.source or cfg["source"]
    print(f"Resolving latest {package} via {source} …")
    budget = int(os.environ.get("CZIX_RESOLVE_TIMEOUT", "90"))
    try:
        apks, meta = apk.run_with_budget(lambda: _fetch_to_disk(
            cfg, package, source,
            pathlib.Path(ns.dir or cfg["download_dir"]).expanduser()), budget)
    except (RuntimeError, TimeoutError) as e:
        print(f"ERROR: {e}")
        return 1

    info = apk.inspect(apks[0])
    config.save_state("last", {
        "package": package, "source": source,
        "apks": [str(p) for p in apks],
        "sha256": info.sha256, "version": meta.get("version"),
    })
    print(f"{len(apks)} APK file(s) ready. Next: `czix trust` then `czix install`")
    print(NOTICE_SHORT)
    return 0


def _latest_paths(cfg: dict) -> list[pathlib.Path]:
    st = config.read_state("last")
    if not st or not st.get("apks"):
        raise SystemExit("No fetched APK yet — run `czix fetch` first, or pass a path.")
    return [pathlib.Path(p) for p in st["apks"]]


def _pin_if_first(cfg: dict, apks: list[pathlib.Path],
                  version: str | None) -> None:
    """TOFU: on the very first install, pin the official signer silently."""
    digest = apk.verify_signature(apks[0])
    if digest is None:
        print("apksigner not found — skipping TOFU pin "
              "(install Android build-tools for stronger verification).")
        return
    if config.read_trusted(cfg["package"]) is None:
        config.pin_trusted(cfg["package"], digest, version)
        print(f"Pinned official signing cert {digest[:24]}… (TOFU)")


def _check_pinned(cfg: dict, paths: list[pathlib.Path], force: bool) -> bool:
    digest = apk.verify_signature(paths[0])
    if digest is None:
        print("apksigner not found — skipping signature pin check.")
        return True
    trusted = config.read_trusted(cfg["package"])
    if trusted and trusted["cert_sha256"] != digest:
        print(f"SIGNATURE MISMATCH!\n  pinned: {trusted['cert_sha256']}\n"
              f"  got:    {digest}")
        if not force:
            print("Refusing to install. Use `czix install --force` — then re-run "
                  "`czix trust` to re-pin.")
            return False
        print("Proceeding with --force …")
    elif not trusted:
        print(f"Cert {digest[:24]}… not pinned yet. Run `czix trust` (TOFU).")
    return True


def _verify_installable(cfg: dict, paths: list[pathlib.Path],
                        force: bool = False) -> bool:
    """A single bare APK without native libs can never run — refuse it."""
    abis: set[str] = set()
    for p in paths:
        abis.update(apk.inspect(p).abis)
    if abis:
        return True
    print("ERROR: no native libraries (lib/*.so) in these APK file(s).\n"
          "       This looks like a bare BASE split — the engine binaries live "
          "in ABI splits that only ship inside an XAPK bundle.\n"
          "       Fix: `czix fetch` (now prefers the XAPK route) and retry.")
    if force:
        print("Proceeding only because --force was given.")
        return True
    return False


def cmd_install(ns) -> int:
    cfg = config.load_config()
    paths = [pathlib.Path(p) for p in (ns.paths or [])] or _latest_paths(cfg)
    for p in paths:
        if not p.exists():
            raise SystemExit(f"missing APK: {p}")
    if not _verify_installable(cfg, paths, ns.force):
        return 2
    if not _check_pinned(cfg, paths, ns.force):
        return 2
    ok = waydroid.install(paths)
    if ok:
        info = apk.inspect(paths[0])
        config.save_state("installed", {
            "package": cfg["package"], "version": info.version_name})
    return 0 if ok else 1


def cmd_trust(ns) -> int:
    cfg = config.load_config()
    paths = [pathlib.Path(p) for p in (ns.paths or [])] or _latest_paths(cfg)
    digest = apk.verify_signature(paths[0])
    if digest is None:
        print("apksigner missing — cannot compute cert digest. "
              "Install 'apksigner' from Android build-tools.")
        return 1
    info = apk.inspect(paths[0])
    config.pin_trusted(cfg["package"], digest, info.version_name)
    print(f"Pinned {cfg['package']} certificate {digest} (version "
          f"{info.version_name or '?'}). Future updates with a different cert "
          "will be refused at install.")
    return 0


# ---- Sober-style one-command flow ------------------------------------------

def _maybe_auto_update(cfg: dict, package: str, installed: str | None,
                       quiet_ok: bool) -> bool:
    """True if an update happened. Silent skip when offline/unknown."""
    if installed is None:
        return False
    from .sources import apkpure
    latest = None
    try:
        latest = apk.run_with_budget(apkpure.latest_version, 8, package)
    except BaseException:  # offline / mirror hiccup → don't block launch
        return False
    if not latest or not latest.get("version_name"):
        return False
    new, old = _vkey(latest["version_name"]), _vkey(installed)
    if new is None or old is None or new <= old:
        if not quiet_ok:
            print(f"Up to date ({installed}).")
        return False
    print(f"Roblox {latest['version_name']} available (installed {installed}) "
          "— updating…")
    return _ensure_installed(cfg, package, update=True)


def _ensure_installed(cfg: dict, package: str, update: bool = False) -> bool:
    source = cfg["source"]
    try:
        dest_dir = pathlib.Path(cfg["download_dir"]).expanduser()
        apks, meta = _fetch_to_disk(cfg, package, source, dest_dir)
        info_v = meta.get("version") or apk.inspect(apks[0]).version_name
        if not _verify_installable(cfg, apks, force=False):
            return False
        _pin_if_first(cfg, apks, info_v)
        if config.read_trusted(cfg["package"]) is not None:
            if not _check_pinned(cfg, apks, force=False):
                return False
        if not waydroid.install(apks):
            return False
        config.save_state("installed", {
            "package": package, "version": info_v})
        return True
    except (RuntimeError, TimeoutError) as e:
        print(f"ERROR during {'update' if update else 'install'}: {e}")
        return False


def cmd_play(ns) -> int:
    cfg = config.load_config()
    package = ns.package or cfg["package"]

    if waydroid.waydroid() is None:
        print("Czix needs Waydroid.\n" + waydroid.HINT)
        return 1
    ok, msg = waydroid.ensure_environment(auto=not ns.no_fix)
    if not ok:
        print(f"Environment not ready: {msg}\n{waydroid.HINT}")
        return 1

    installed = waydroid.installed_version(package) \
        or (config.read_state("installed") or {}).get("version")

    if installed is None:
        print("Roblox is not installed in the container yet — "
              "fetching the official client…")
        if not _ensure_installed(cfg, package):
            return 1
        installed = (config.read_state("installed") or {}).get("version")

    if not ns.no_update:
        _maybe_auto_update(cfg, package, installed, quiet_ok=not ns.verbose_update)
        installed = (config.read_state("installed") or {}).get("version") or installed

    return 0 if waydroid.launch(package) else 1


def cmd_update(ns) -> int:
    cfg = config.load_config()
    package = ns.package or cfg["package"]
    installed = waydroid.installed_version(package) \
        or (config.read_state("installed") or {}).get("version")
    if installed is None:
        print("No installed version recorded — running `czix play` will install.")
        return 1
    updated = _maybe_auto_update(cfg, package, installed, quiet_ok=False)
    return 0 if updated else 0  # 'already up to date' is not an error


def cmd_launch(ns) -> int:
    cfg = config.load_config()
    package = ns.package or cfg["package"]
    return 0 if waydroid.launch(package) else 1


def cmd_status(ns) -> int:
    ok, msg = waydroid.status()
    print(("READY — " if ok else "NOT READY — ") + msg)
    return 0 if ok else 1


def cmd_doctor(ns) -> int:
    print("czix doctor")
    bad = 0
    for name, ok, note in waydroid.doctor(fix=ns.fix):
        mark = "✓" if ok else "✗"
        print(f"  [{mark}] {name:18} {note}")
        bad += 0 if ok else 1
    print(f"\n{('all good' if bad == 0 else f'{bad} check(s) need attention')}")
    return 0 if bad == 0 else 1


def cmd_notice(ns) -> int:
    root = pathlib.Path(__file__).resolve().parents[2]
    notice = root / "NOTICE"
    if notice.exists():
        print(notice.read_text(encoding="utf-8"))
    else:
        print(NOTICE_SHORT)
    return 0


def cmd_info(ns) -> int:
    paths = [pathlib.Path(p) for p in (ns.paths or [])]
    if not paths:
        print("usage: czix info <apk-or-bundle> [...]")
        return 2
    for path in paths:
        print(apk.inspect(path).describe())
        print("-" * 46)
    return 0


def cmd_surface(ns) -> int:
    from . import surface
    paths = [pathlib.Path(p) for p in (ns.paths or [])] or _latest_paths(cfg_paths_fallback())
    for p in paths:
        if not p.exists():
            raise SystemExit(f"missing file: {p}")
    summary = surface.summarize(paths)
    line = surface.render_terminal(summary)
    print(line)
    if ns.json_out:
        pathlib.Path(ns.json_out).write_text(surface.json_dumps(summary),
                                             encoding="utf-8")
        print(f"full JSON → {ns.json_out}")
    if ns.md_out:
        pathlib.Path(ns.md_out).write_text(surface.render_markdown(summary),
                                           encoding="utf-8")
        print(f"markdown  → {ns.md_out}")
    return 0


def cfg_paths_fallback() -> dict:
    return {"download_dir": config.load_config()["download_dir"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="czix",
        description="Unofficial Roblox-on-Linux launcher (Waydroid-based)",
        epilog="Not affiliated with Roblox Corporation. See NOTICE.")
    ap.add_argument("--source", choices=sorted(SOURCES),
                    help="APK source (default: config, else apkpure)")
    ap.add_argument("--package", help="Android package id override")
    ap.add_argument("--dir", help="download directory override")
    ap.add_argument("--version", action="version",
                    version=f"czix {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--source", choices=sorted(SOURCES))
    common.add_argument("--package")
    common.add_argument("--dir")

    p = sub.add_parser("play", parents=[common],
                       help="(Sober-style) bootstrap + update + launch Roblox")
    p.add_argument("--no-fix", action="store_true",
                   help="don't attempt to fix/start environment")
    p.add_argument("--no-update", action="store_true",
                   help="skip the silent update check")
    p.add_argument("--verbose-update", action="store_true",
                   help="print 'up to date' instead of staying silent")
    p.set_defaults(func=cmd_play)

    sub.add_parser("fetch", parents=[common],
                   help="download latest APK / bundle").set_defaults(func=cmd_fetch)
    p = sub.add_parser("info", parents=[common], help="inspect an APK/bundle")
    p.add_argument("paths", nargs="*")
    p.set_defaults(func=cmd_info)
    p = sub.add_parser("install", parents=[common], help="install APK(s) into Waydroid")
    p.add_argument("paths", nargs="*")
    p.add_argument("--force", action="store_true",
                   help="install even if pinned cert mismatches")
    p.set_defaults(func=cmd_install)
    p = sub.add_parser("trust", parents=[common], help="TOFU-pin the signing cert")
    p.add_argument("paths", nargs="*")
    p.set_defaults(func=cmd_trust)
    p = sub.add_parser("update", parents=[common],
                       help="check + silently apply newer Roblox version")
    p.set_defaults(func=cmd_update)
    p = sub.add_parser("launch", parents=[common], help="launch Roblox in Waydroid")
    p.set_defaults(func=cmd_launch)
    sub.add_parser("status", parents=[common],
                   help="waydroid status").set_defaults(func=cmd_status)
    p = sub.add_parser("doctor", parents=[common],
                       help="check the environment")
    p.add_argument("--fix", action="store_true",
                   help="attempt auto-fixes (pkexec, multi-window mode, session)")
    p.set_defaults(func=cmd_doctor)
    p = sub.add_parser("surface", parents=[common],
                       help="static Android/NDK API-surface analysis of an APK")
    p.add_argument("paths", nargs="*")
    p.add_argument("--json", dest="json_out", help="write full symbol JSON here")
    p.add_argument("--md", dest="md_out", help="write markdown report here")
    p.set_defaults(func=cmd_surface)
    sub.add_parser("notice", parents=[common],
                   help="show legal notice").set_defaults(func=cmd_notice)

    ns = ap.parse_args(argv)
    return ns.func(ns)


if __name__ == "__main__":
    sys.exit(main())
