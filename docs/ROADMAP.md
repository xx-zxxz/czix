# Roadmap

Goal: 100% free-software Roblox-on-Linux, growing from Phase 0 (working
launcher) to Phase 2 (bespoke runtime, Sober-class).

## Phase 0 — *ship something* (current)
- [x] Multi-source APK resolver (apkpure direct + scrape, archive.org, manual)
- [x] XAPK/APKS/APK unpacking (base-first ordering)
- [x] Waydroid install: single APK + split-APK streaming via `pm install-*`
- [x] TOFU signature pinning (`czix trust`) with mismatch abort
- [x] `doctor` env checks; Flatpak-aware host command dispatch
- [x] **Sober-style `czix play`**: bootstrap (pkexec container start, session
      daemon, multi-window single-game-window mode), first-run fetch+verify+
      install, silent auto-update on every launch
- [x] `czix update` standalone; version probe via APKPure metadata (no DL)
- [x] Real icon (`data/org.czix.Czix.svg`, original artwork) + Flatpak
      manifest polish (icon/desktop install, input device, download dir)
- [x] `czix doctor --fix` covers image init (pkexec `waydroid init`, image
      presence check, session start, single-window mode)
- [x] Gamepad passthrough notes + multi-window tweaks: `docs/INPUT-AND-WINDOWS.md`,
      `czix prop get|set|list` (documented properties only)

## Phase 1 — *learn the API surface*
- [x] **`czix surface`** — static NDK/Android API mapping from the APK's
      `lib/*.so` (stdlib-only ELF32/64 parser; imports by category, DT_NEEDED,
      JNI bridge). First real output: `docs/API-SURFACE.md` (arm64-v8a).
- [x] **Runtime trace** — `czix trace`: logcat capture (dump window or live
      window), native-lib load events, per-subsystem stream activity, and
      correlation with the static `czix surface --json` report
- [ ] Graphics path decision: GLES (seen imported: libEGL/libGLESv2, no vk)
      → shim via Wayland+EGL surfaceless first (now data-backed by `czix trace`)
- [ ] **x86_64 gap discovered**: APKPure splits pack arm64-v8a only; x86_64
      Android builds exist upstream (Play metadata lists x86_64) but need a
      Play-mirror/split-source (Aurora-style) or ABI parameter … TBD
- [ ] Config: FPS cap unlock, GLES renderer preference
- [x] Benchmark tooling: `czix bench` measures Android's own activity-start
      ("Displayed …") timing over repeated launches (JSON out)
- [ ] Benchmark: Waydroid vs Windows native on same GPU

## Phase 2 — *bespoke runtime* (Sober-class, open source)
- [ ] Minimal Android JNI/NativeActivity glue implementing only the subset
      Roblox uses (map from Phase 1)
- [ ] APK acquisition flow with strong verification; no redistribution
- [ ] Performance parity goal: ≥ Waydroid; stretch: native-like
- [ ] Flatpak-only distribution (Sober-style) for safety-updates
- [ ] Upstream collaboration: Android Translation Layer community

## Names & mythos
- Czix is deliberately neutral-named; no Roblox trademark usage.
- NOTICE documents the unofficial stance; users fetch APKs themselves.
