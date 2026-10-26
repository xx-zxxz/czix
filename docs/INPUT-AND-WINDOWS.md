# Input (gamepads) and window behavior

Practical notes for Roblox-on-Waydroid ergonomics. Everything below is plain
Waydroid behavior; Czix only reads/writes documented container properties.

## Multi-window vs single-window (the Sober-like mode)

Waydroid's default is *multi-window*: every Android app gets its own floating
window, and Android's home screen shows full-screen. Roblox then opens as a
separate window with no launcher UI in front - good on desktops.

| Setting | Value | Effect |
|---|---|---|
| `persist.waydroid.multi_windows` | `false` | one big compositor window (full Android UI inside) |
| `persist.waydroid.multi_windows` | `true` | each app in its own window (default in recent images) |

`czix play`/`czix doctor --fix` set the *single game window* arrangement for
you. Manual tweaks:

```sh
czix prop get persist.waydroid.multi_windows
czix prop set persist.waydroid.multi_windows true   # pkexec fallback built in
```

Sizing the container (only relevant in multi-window mode):

```sh
czix prop set persist.waydroid.width 1280
czix prop set persist.waydroid.height 720
waydroid show-full-ui    # full Android home, useful for debugging
```

## Gamepads

Waydroid receives input through the Wayland seat, so a controller already
working in your desktop session automatically appears inside Android as a
standard gamepad - no config normally needed. Verify what Android sees:

```sh
waydroid shell -- getevent -pl     # input devices visible to the container
czix trace --seconds 10            # watch Roblox's own input log lines
```

- Roblox's Android build supports standard Android gamepad APIs; with the
  device visible to the container, nothing needs mapping by Czix.
- If nothing shows up under `getevent`, your compositor (or Steam Input /
  an overlay tool) is grabbing the device exclusively - release it there.
- Mouse-as-touch: `czix prop set persist.waydroid.fake_touch true` helps when
  Roblox's touch UI ignores a plain mouse click.

Scaling/rotation quirks: multi-window + fixed container sizes can letterbox the
game; if Roblox uses portrait UI, prefer `multi_windows false` (full window) or
square-ish `width`/`height`.
