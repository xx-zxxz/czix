---
name: 🐞 Bug report
about: Something in czix broke (fetch/install/launch)
labels: bug
---

## What happened

<!-- clear description -->

## What you ran

```sh
# full command + output (czix fetch/install/play …)
```

## Environment

- Distro: (e.g. Arch / Fedora / Ubuntu 24.04)
- Python: (`python3 --version`)
- Waydroid: (`waydroid --version`; container GPU: `waydroid shell getprop ro.product.model`)
- Session: `waydroid status` output

## Extra

- Was the APK signature pin involved? (`~/.local/state/czix/`)
- Anything in Android logs? (`waydroid logcat -d | tail -50`)

---
⚠ Reminder: czix is unofficial & unaffiliated with Roblox Corporation.
