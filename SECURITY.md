# Security policy

## Supported versions

Only the latest `main` of czix is supported; releases are rolling.

## Reporting a vulnerability

Please **do NOT open a public issue** for security problems (download
verification bypass, shell injection in waydroid helpers, TOFU pin issues…).

- Open a GitHub **security advisory** (Repo → Security → Advisories) — preferred
- Best effort contact: maintainer handle from the repo owner profile.

## Threat position (please read)

- czix never ships Roblox binaries; APKs come from mirrors of the official
  app and are pinned to their signing certificate (TOFU) — tampered downloads
  fail loudly at `czix install`.
- For safe APK acquisition, trust the pin chain, not memory: prefer `apksigner`
  being installed so `czix trust`/`install` actually verifies.
- We consider a "no native libs" bare split reaching `waydroid app install`
  without loud user-facing warning a security/UX bug — please report.
