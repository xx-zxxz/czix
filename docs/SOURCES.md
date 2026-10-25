# APK sources & verification policy

## Sources
| Source      | Kind   | Freshness | Notes |
|-------------|--------|-----------|-------|
| `apkpure`   | direct | latest    | Mirrors of the official Google Play build, signature-identical. We probe the direct endpoint `d.apkpure.com/b/APK/<pkg>?version=latest` and fall back to scraping the app page. |
| `archive`   | direct | may lag   | Internet Archive item *ROBLOX Android Archive* (`com.roblox.client`), dozens of historical versions. Good fallback when mirrors are down. |
| manual      | local  | n/a       | `czix install ./path.apk` always works. The user downloaded the file themselves. |

## What we deliberately DO NOT do
- ❌ Do not redistribute Roblox APKs (that's Roblox IP).
- ❌ Do not fetch from "MOD APK" repos (malware/adware risk; disallowed).
- ❌ Do not patch/modify the APK (anti-tamper + ToS).

## Verification (trust-on-first-use)
1. `czix fetch` → the resolved file is unpacked (XAPK → base + splits).
2. `czix trust` pins the signing-certificate SHA-256 (via `apksigner`) into
   `~/.local/state/czix/trusted.json`.
3. Every later `czix install` re-verifies: a different signing cert = hard
   abort unless `--force`. This defends against a mirror serving a trojaned
   build under the same file name.

## APK integrity limits (v0.1, honest)
- We verify the *signer*, not Roblox's own CDN hashes (Android has no
  rbxPkgManifest like the Windows client exposes).
- Split bundles: we pin the cert of the base APK, and assume splits of the
  same bundle share it (true for official builds).
