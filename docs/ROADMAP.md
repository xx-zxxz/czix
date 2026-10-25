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
- [ ] Real icon + Flathub-quality manifest polishing
- [ ] `czix doctor --fix` for image init (`waydroid init` needs sudo discussion)
- [ ] Gamepad passthrough notes; multi-window tweaks

## Phase 1 — *learn the API surface*
- [ ] Config: FPS cap unlock, GLES renderer preference (vstr)
- [ ] Trace which Android APIs Roblox calls (strace under Waydroid, `ltrace`,
      plumbing from Lineage logs) → `API-SURFACE.md`
- [ ] Prototype: run the extracted `lib/*.so` directly against a tiny shim
      (EGL/GLES via surfaceless Wayland, PipeWire audio) on a hello-window
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
