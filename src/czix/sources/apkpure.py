"""APKPure resolver — mirrors of the official Google Play build.

d.apkpure.com hosts direct downloads keyed by package id. We try the direct
endpoint first and fall back to scraping the app page if the direct link
shape changes again.
"""
import re
import urllib.request

from ..apk import UA

REFERER = "https://apkpure.com/"

_APPS_URL = "https://d.apkpure.com/b/APK/{pkg}?version=latest"
_PAGE_URL = "https://apkpure.com/roblox/{pkg}"


def _probe(url: str, headers: dict) -> str | None:
    """Range-request 1 byte to validate the link; None if unusable."""
    req = urllib.request.Request(url, headers={**headers, "Range": "bytes=0-0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if ctype.startswith("text/html"):
                return None
            return url
    except Exception:  # noqa: BLE001 — any HTTP problem means: try next
        return None


def resolve(package: str, cfg: dict) -> dict:
    headers = {"User-Agent": UA, "Referer": REFERER}
    for url in (_APPS_URL.format(pkg=package),):
        ok = _probe(url, headers)
        if ok:
            return {"url": ok, "headers": headers, "source": "apkpure",
                    "note": "direct APKPure endpoint (latest)"}

    # fallback: scrape the app page for a direct download link
    req = urllib.request.Request(_PAGE_URL.format(pkg=package),
                                 headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read(400_000).decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            f"APKPure unreachable ({e}). Source alternatives: `--source archive`, "
            "or download an APK yourself and use `czix install <file.apk>`."
        ) from e

    links = re.findall(r'https://d\.apkpure\.(?:com|net)/[^"\'\s<]+', html)
    good = [u for u in dict.fromkeys(links) if "APK" in u or "XAPK" in u]
    if good:
        return {"url": good[0], "headers": headers, "source": "apkpure",
                "note": "scraped from APKPure app page"}
    raise RuntimeError(
        "Could not find a download link on APKPure. The page layout may have "
        "changed. Use `--source archive` or a manual APK path."
    )
