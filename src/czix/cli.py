"""Czix CLI — fetch/verify/install/launch the Roblox Android client."""
import argparse
import os
import pathlib
import sys

from . import __version__, apk, config, waydroid

SOURCES = {"apkpure", "archive"}

NOTICE_SHORT = (
    "Czix is unofficial and not affiliated with Roblox Corporation. Czix does "
    "not redistribute Roblox code; APKs are fetched from public mirrors of the "
    "official app. Use at your own risk — third-party clients are a ToS gray "
    "area and may lead to account actions. See `czix notice`."
)


def _resolve_source(source: str, package: str, cfg: dict) -> dict:
    if source == "apkpure":
        from .sources import apkpure
        return apkpure.resolve(package, cfg)
    if source == "archive":
        from .sources import archiveorg
        return archiveorg.resolve(package, cfg)
    raise SystemExit(f"unknown source {source!r}")


def cmd_fetch(ns) -> int:
    cfg = config.load_config()
    package = ns.package or cfg["package"]
    source = ns.source or cfg["source"]
    print(f"Resolving latest {package} via {source} …")
    budget = int(os.environ.get("CZIX_RESOLVE_TIMEOUT", "90"))
    try:
        cand = apk.run_with_budget(_resolve_source, budget,
                                   source, package, cfg)
        print(f"  {cand['note']}")

        dest_dir = pathlib.Path(ns.dir or cfg["download_dir"]).expanduser()
        dest_dir.mkdir(parents=True, exist_ok=True)
        print(f"Downloading → {dest_dir}")
        raw = apk.download(cand["url"], dest_dir, headers=cand["headers"],
                           timeout_s=int(cfg["timeout_s"]))
    except (RuntimeError, TimeoutError) as e:
        print(f"ERROR: {e}")
        return 1

    print("Normalizing bundle…")
    apks = apk.normalize_bundle(raw, work_dir=dest_dir)
    if not apks:
        # keep the artifact for manual inspection, still fail loudly
        print(f"ERROR: {raw} is not a valid APK/bundle (HTML page? bad link?).")
        config.save_state("last", {"package": package, "source": source})
        return 1

    infos = [apk.inspect(p) for p in apks]
    for info in infos:
        print(info.describe())
        print("-" * 46)

    config.save_state("last", {
        "package": package, "source": source,
        "apks": [str(p) for p in apks],
        "sha256": infos[0].sha256,
        "version": infos[0].version_name,
    })
    print(f"{len(apks)} APK file(s) ready. Next: `czix trust` then `czix install`")
    print(NOTICE_SHORT)
    return 0


def _latest_paths(cfg: dict) -> list[pathlib.Path]:
    st = config.read_state("last")
    if not st or not st.get("apks"):
        raise SystemExit("No fetched APK yet — run `czix fetch` first, or pass a path.")
    return [pathlib.Path(p) for p in st["apks"]]


def cmd_install(ns) -> int:
    cfg = config.load_config()
    paths = [pathlib.Path(p) for p in (ns.paths or [])] or _latest_paths(cfg)
    for p in paths:
        if not p.exists():
            raise SystemExit(f"missing APK: {p}")

    digest = apk.verify_signature(paths[0])
    if digest is None:
        print("apksigner not found — skipping signature pin check "
              "(install Android build-tools for stronger verification).")
    else:
        trusted = config.read_trusted(cfg["package"])
        if trusted and trusted["cert_sha256"] != digest:
            print(f"SIGNATURE MISMATCH!\n  pinned: {trusted['cert_sha256']}\n"
                  f"  got:    {digest}")
            if not ns.force:
                print("Refusing to install. If you really mean it: czix install "
                      "--force (then re-run `czix trust`.)")
                return 2
            print("Proceeding with --force …")
        elif not trusted:
            print(f"Cert {digest[:24]}… is not pinned yet. Run `czix trust` "
                  "to pin it (TOFU).")

    return 0 if waydroid.install(paths) else 1


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
          "will be refused at `czix install`.")
    return 0


def cmd_launch(ns) -> int:
    cfg = config.load_config()
    package = ns.package or cfg["package"]
    return 0 if waydroid.launch(package) else 1


def cmd_status(ns) -> int:
    ok, msg = waydroid.status()
    print(("WANT: READY — " if ok else "WANT: NOT READY — ") + msg)
    return 0 if ok else 1


def cmd_doctor(ns) -> int:
    print("czix doctor")
    bad = 0
    for name, ok, note in waydroid.doctor():
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="czix",
        description="Unofficial Roblox-on-Linux launcher (Waydroid phase 0)",
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
    p = sub.add_parser("launch", parents=[common], help="launch Roblox in Waydroid")
    p.set_defaults(func=cmd_launch)
    sub.add_parser("status", parents=[common],
                   help="waydroid status").set_defaults(func=cmd_status)
    sub.add_parser("doctor", parents=[common],
                   help="check the environment").set_defaults(func=cmd_doctor)
    sub.add_parser("notice", parents=[common],
                   help="show legal notice").set_defaults(func=cmd_notice)

    ns = ap.parse_args(argv)
    return ns.func(ns)


def cmd_info(ns) -> int:
    paths = [pathlib.Path(p) for p in (ns.paths or [])]
    if not paths:
        print("usage: czix info <apk-or-bundle> [...]")
        return 2
    for path in paths:
        print(apk.inspect(path).describe())
        print("-" * 46)
    return 0


if __name__ == "__main__":
    sys.exit(main())
