# APK sources & verification policy

## Sources
| Source      | Kind   | Freshness | Notes |
|-------------|--------|-----------|-------|
| `apkpure`   | direct | latest    | Mirrors of the official Google Play build. We prefer the **XAPK route** (`d.apkpure.com/b/XAPK/...`) because Roblox's engine binaries live in *ABI splits* that only ship inside the bundle — the bare-APK endpoint mirrors just the lib-less base split (found live: 99 MiB, zero `lib/*.so`). Czix unpacks base+config splits and installs them together via `pm install-create`. |
| `archive`   | direct | may lag   | Internet Archive item *ROBLOX Android Archive* (`com.roblox.client`), filtered strictly to official-package names (rejects `com.tencent.*` lookalikes seen in that item). |
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
