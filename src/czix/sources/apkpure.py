"""APKPure resolver — mirrors of the official Google Play build.

d.apkpure.com hosts direct downloads keyed by package id. We try the direct
endpoint first and fall back to scraping the app page if the direct link
shape changes again.
"""
import re
import urllib.request

from ..apk import UA, run_with_budget

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


# version patterns, most-specific first
_VERSION_PATTERNS = (
    r'itemprop="version[^"]*"[^>]*content="([^"]+)"',
    r'"versionName"\s*:\s*"([^"]+)"',
    r'"version"\s*:\s*"(\d[\w.]+)"',
    r'[vV]ersion[^<]{0,20}&gt;?\s*(\d+\.\d+\.\d+)',
)


def latest_version(package: str, budget: float = 8) -> dict | None:
    """Cheapest possible update check: scrape app page metadata, no download.

    Returns {"version_name": ..., "version_code": ...} or None if unknown.
    """
    def _page() -> str:
        req = urllib.request.Request(_PAGE_URL.format(pkg=package),
                                     headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read(400_000).decode("utf-8", "replace")

    try:
        html = run_with_budget(_page, budget)
    except BaseException:  # noqa: BLE001 — any failure = "can't tell"
        return None

    out: dict = {}
    m = re.search(r'"versionCode"\s*:\s*"?(\d+)"?', html)
    if m:
        out["version_code"] = m.group(1)
    for pat in _VERSION_PATTERNS:
        m = re.search(pat, html)
        if m:
            out["version_name"] = m.group(1).strip()
            break
    if "version_name" not in out:
        m = re.search(r"\b(\d+\.\d+\.\d+)\b", html)
        if m:
            out["version_name"] = m.group(1)
    return out or None
