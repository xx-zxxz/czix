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

## Quick start

```sh
# 1. Install prerequisites (Arch example)
sudo pacman -S --needed waydroid python
# Waydroid image: pick a Lineage OS ~ Android 11 system image,
# `sudo waydroid init` then `sudo systemctl start waydroid-container`

# 2. Grab Czix
git clone https://github.com/<youruser>/czix
cd czix && pipx install .            # or: make install

# 3. Get the newest Roblox APK & install it into the container
czix fetch        # downloads latest official APK (APKPure source)
czix install      # installs into Waydroid
czix trust        # pins the APK signing certificate (TOFU model)
czix launch       # enjoy :)
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
