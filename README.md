# Czix

> Run Roblox Player on Linux via a containerized Android environment.

Czix is a fully free-software (GPL-3.0) launcher/manager for playing Roblox on
Linux. Phase 0 wraps **Waydroid** (a Wayland-native Android container) and keeps
you on the latest Roblox Android client, phase 1+ will grow toward a bespoke
runtime for Roblox (similar in goal to the reservation that inspired this
project — but 100% open source).

## ⚠ Legal & ethical notice (please read)

- Czix is **unofficial** and not affiliated with, endorsed by, or connected to
  Roblox Corporation in any way.
- Czix **never redistributes** Roblox's code or intellectual property. The APK
  is downloaded by *you*, from far-east mirror APKPure (a byte-identical mirror
  of the Google Play app) or the Internet Archive.
- Using any third-party client for a network can violate that network's Terms
  of Service — including getting your Roblox account suspended. Use at your own
  risk. See `NOTICE`.

## Quick start — play like Sober

One command does everything (bootstrap, first-run install, silent auto-update,
launch in its own window):

```sh
# 0. one-time system prep (Arch)
sudo pacman -S --needed waydroid python
sudo waydroid init                    # downloads Android image
sudo systemctl start waydroid-container

# 1. grab Czix
git clone https://github.com/<youruser>/czix && cd czix && pipx install .

# 2. From now on:
czix play                      # or: double-click the Czix desktop icon
czix doctor --fix              # if anything looks off, this self-heals
```

What `czix play` guarantees, Sober-style:

- ✅ launches **directly into Roblox**, not an Android home screen
  (multi-window mode is enabled automatically = single game window)
- ✅ first run: downloads the official APK, verifies the signer, installs
- ✅ every run: silent update check (8-second, offline-tolerant) — auto-upgrade
- ✅ works via `flatpak-spawn --host` from inside a Flatpak too

Manual commands (also available):

```sh
czix fetch        # download latest official APK (APKPure source)
czix install      # install into Waydroid
czix trust        # pin the APK signing cert (TOFU)
czix update       # explicit update check
czix launch       # just start Roblox
czix status       # container/session status
```

## How it works

```
┌─────────────────────────────────────────────────────────────┐
│ czix CLI                                                    │
│  ┌────────────────┐  ┌────────────────┐  ┌───────────────┐  │
│  │ sources/       │→ │ apk.py         │→ │ waydroid.py   │  │
│  │ apkpure/org/   │  │ verify,pin,    │  │ install,      │  │
│  │ archive,manual │  │ unpack, sha    │  │ launch        │  │
│  └────────────────┘  └────────────────┘  └───────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

- `czix fetch`   – resolve the newest APK, unpack if it is an XAPK bundle
- `czix install` – push APK into the Android container
- `czix trust`   – record (TOFU) the APK signing cert; later updates abort on mismatch
- `czix launch`  – start Waydroid + Roblox

## Why Waydroid (Phase 0) and not FEX/wine?

- Wine is blocked outright by Roblox.
- Waydroid boots a real Linux-kernel Android (no VM) using your GPU via Mesa —
  that is why high performance is achievable AND why Roblox's anti-cheat does
  not immediately see wine platform markers.
- Roblox's Android build ships **x86_64** native libraries, so on x86_64 hosts
  no ARM translation (libhole/libndk) is normally needed.

See `docs/ROADMAP.md` for the long game (own minimal runtime, no container).

## Repo map

| Path                  | Purpose                                          |
|-----------------------|--------------------------------------------------|
| `src/czix/`           | CLI + logic (pure Python stdlib)                  |
| `src/czix/sources/`   | APK sources (apkpure, archive.org, manual)         |
| `packaging/`          | Flatpak manifest                                  |
| `data/`               | Desktop entry, icons                              |
| `docs/`               | Roadmap & source/verification policy              |

## License

GPL-3.0-or-later — see [`LICENSE`](./LICENSE). Czix borrows its *ethics* from
VinegarHQ's NOTICE culture: unofficial, no Roblox code shipped, no money      .
