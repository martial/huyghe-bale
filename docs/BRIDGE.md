# OSC bridge

The admin runs a UDP OSC listener (`admin/backend/engine/osc_bridge.py`) that
accepts messages from external sources (show controller, Max/MSP, TouchDesigner,
…) and fans them out to the Pi devices.

**Default port:** 9002 (configurable in admin Settings).

## Routing modes

Set in admin Settings → Bridge.

| Mode | Behaviour |
|---|---|
| `type-match` (default) | `/vents/*` → vents devices, `/trolley/*` → trolley devices, `/sys/*` → all devices. Anything else is logged but not forwarded. |
| `passthrough` | Every message forwarded unchanged to every device. |
| `none` | Logged in the SSE stream only — useful as a tap. |

## Per-device targeting: `/to/<identifier>/<rest>`

Wrap any address with `/to/<identifier>/...` to send only to one device. The
identifier matches `id`, `name`, `ip_address`, or `hardware_id` (in that order).
Always wins over the routing mode — works even when routing is `none`.

```
/to/vents-1/vents/fan/1 0.5      # fan 1 on the vents-1 device only
/to/screenclub.home/trolley/stop # stop one trolley by name
```

## Bridge macros (`/bridge/*`)

Macros are interpreted by the bridge itself and expanded into multiple
device-native messages. They are **never** forwarded as `/bridge/...` to a Pi —
the controllers don't speak that namespace. Macros bypass routing mode (same as
`/to/...`).

### `/bridge/vents/off`

Args: none.

Per vents device, in order:

1. `/vents/mode "raw"` — disable auto mode (so the auto loop can't fight us).
2. `/vents/peltier 0` — bitmask 0, all three peltiers off.
3. `/vents/fan/1 0.0`
4. `/vents/fan/2 0.0`

Use this as a safe-shutdown bang from a show controller.

### `/bridge/trolley/off`

Args: none.

Sends `/trolley/stop` to every trolley device. Aborts any motion in progress.

### `/bridge/position [<float>]` and `/bridge/position/<id> <float>`

Maps an external `0.0..1.0` value into the soft window `0.1..0.9`, then sends
`/trolley/position <mapped>`.

| Address | Target |
|---|---|
| `/bridge/position 0.5` | every trolley device |
| `/bridge/position/<id> 0.5` | one device, looked up by id / name / ip / hardware_id |

Mapping: `mapped = 0.1 + clamp(value, 0, 1) * 0.8` — so `0.0 → 0.1`, `1.0 → 0.9`,
`0.5 → 0.5`. Out-of-range values are clamped silently. Targeting a non-trolley
device is rejected.

## Diagnostics

- `GET /api/v1/bridge/state` — last 500 events (ring buffer).
- `GET /api/v1/bridge/stream` — SSE stream of every event in real time.
- `POST /api/v1/bridge/clear` — empty the ring buffer.

Each event records `{address, args, targets, [forwarded_as], [dropped], [expanded]}`.
Macros surface their per-device sends in `expanded` so you can see exactly what
hit the wire.

## Quick smoke test

```sh
python3 -c "from pythonosc.udp_client import SimpleUDPClient; \
  c=SimpleUDPClient('127.0.0.1', 9002); \
  c.send_message('/bridge/vents/off', [])"
```

Watch `/api/v1/bridge/stream` (or the admin Bridge tab) for the event.
