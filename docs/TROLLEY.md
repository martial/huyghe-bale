# Trolley — full functional reference

The trolley is a closed-loop stepper-driven carriage on a rail with two end-stop
microswitches and a pair of driver diagnostic outputs. It runs a Raspberry Pi
flashed with the "trolley" personality of `gpio-osc`. This document covers
everything the firmware, OSC contract, settings layer, calibration flow, admin
UI, and the two operator-facing CLI tools currently expose.

**Hardware datasheets** (in `docs/`):
- `Driver_CL86Y_V2.0_pulse_stepper_driver_manual_V1.0.pdf` — the stepper driver.
- `Motor_34HS38-4204D-E1000.pdf` — the NEMA 34 closed-loop stepper motor with 1000 CPR encoder.

Pin map and firmware constants live in `rpi-controller/config.py:39-72`.

---

## 1. Hardware overview

One closed-loop stepper, one driver, two end-stop microswitches.

- **Motor**: `34HS38-4204D-E1000` — NEMA 34, 1.8° / step (200 full steps per revolution),
  rated 3.39 V / 4.2 A per phase, 7.0 Nm holding torque, with a built-in
  1000 CPR rotary encoder. Datasheet: `docs/Motor_34HS38-4204D-E1000.pdf`.
- **Driver**: `CL86Y(V20)` — Stepperonline closed-loop pulse-type stepper driver,
  20–80 V AC / 30–110 V DC, up to 6.0 A continuous, 200 kHz pulse input,
  built-in position-out-of-tolerance protection.
  Manual: `docs/Driver_CL86Y_V2.0_pulse_stepper_driver_manual_V1.0.pdf`.
- **End-stops**: two mechanical microswitches, one at each end of the rail.

The driver is **closed-loop at the driver level** — it reads its own encoder and
adjusts current internally to keep the rotor on the commanded position. So
"missed steps" in the open-loop sense are corrected silently inside the driver.
However, the **Pi-to-driver relationship is still open-loop** — the Pi only
counts the pulses it *sent*, with no encoder feedback. Driver-side recovery
events (a brief stall the driver corrects) are invisible to the Pi.

### 1.1 Driver pin map (CL86Y signal ports)

The driver has **differential photocoupler I/O** — every signal is a pair of
+ and − wires. The Pi GPIOs are wired to one wire of each pair (and the other
wire to a fixed level depending on the wiring scheme).

| Driver port | Wire | Role |
|---|---|---|
| 1 / 2 | PU+ / PU− | pulse input (one rising edge = one step) |
| 3 / 4 | DR+ / DR− | direction input |
| 5 / 6 | MF+ / MF− | motor-free / enable input. **Active LOW per the manual** = motor coils OFF + alarm cleared. The convention used on this rig is "common-negative" wiring, so the Pi-side ENA pin pulls **LOW to enable** (motor energised) and **HIGH to disable**. |
| 7 / 8 | PEND+ / PEND− | position-end output. Optocoupler conducts when the driver finishes emitting the commanded pulse train. **Single signal, two wires.** |
| 9 / 10 | ALM+ / ALM− | alarm output. Optocoupler conducts on overcurrent, overvoltage, undervoltage, phase error, position-over-tolerance, or encoder fault. **Single signal, two wires.** |

### 1.2 Pi GPIO mapping

| Wire | BCM | Direction | Role |
|---|---|---|---|
| `DIR` | 23 | output | step direction |
| `PUL` | 18 | output | step pulse |
| `ENA` | 14 | output | drives MF± of the driver. Pi LOW = motor enabled (on this rig's wiring) |
| `LIM_HOME` | 20 | input, PUD_DOWN | home-end microswitch — HIGH when carriage is at home |
| `LIM_FAR` | 21 | input, PUD_DOWN | far-end microswitch — HIGH when carriage is at far end |
| `ALARM_1` | 1 | input, PUD_DOWN | one wire of the driver ALM± differential pair |
| `ALARM_2` | 16 | input, PUD_DOWN | the other wire of ALM± |
| `PEND_1` | 7 | input, PUD_DOWN | one wire of the driver PEND± differential pair |
| `PEND_2` | 12 | input, PUD_DOWN | the other wire of PEND± |

`ALARM_1` and `ALARM_2` are **two reads of the same single ALM signal**;
they will toggle in opposite directions (one HIGH, the other LOW) when the
optocoupler fires. Same for `PEND_1` / `PEND_2`. The bench tool prints both
so the operator can verify the wiring polarity. Treat *either* `ALARM_1` or
`ALARM_2` going active as "alarm fired" — both happen simultaneously.

Pin caveats — all fine on this Pi:
- `BCM 1` is the default `I²C-0 SDA` line; works as plain GPIO when no I²C HAT
  is attached.
- `BCM 7` is the default `SPI0 CE1` line; works as plain GPIO when SPI is
  disabled in `/boot/firmware/config.txt`.

Currently the runtime firmware reads only `LIM_HOME`. `LIM_FAR`, `ALARM_*`,
and `PEND_*` are visible in the bench tool but not in the OSC layer — see
§8 for the known gaps and §11.1 for the bench tool.

### 1.3 Driver fault LED — quick visual diagnostic

The CL86Y has one red LED that blinks a fault code:

| Blink count | Fault | How to clear |
|---|---|---|
| 1 | Overcurrent / phase short | power-off reset |
| 2 | Overvoltage on supply | auto-recovers when voltage normalises |
| 3 | Undervoltage on supply | auto-recovers when voltage normalises |
| 4 | Phase wiring error | check motor cable, restart |
| 5 | Position out of tolerance | release/power-off reset, or pulse MF (ENA) low |
| 6 | Encoder error | check encoder cable, restart |

When this LED blinks, the ALM optocoupler is also conducting — i.e. an `ALARM_*`
GPIO is HIGH on the Pi side.

### 1.4 Driver dip switches (set on the driver itself, not by Pi)

Set once with the rig powered down:

- **SW1** — ON = CW/CCW (two-pulse) control, OFF = pulse+direction (one-pulse) mode. Set OFF for this firmware.
- **SW2** — motor rotation direction (ON / OFF).
- **SW3–SW6** — microstep selector, 16 settings from 400 to 51200 steps per revolution. Whatever value is dialled in here must match the `microsteps` setting in the firmware (§3) for the mm/rev display to be accurate.

---

## 2. OSC contract

All OSC traffic is UDP. Pi listens on **port 9000**. The backend's reply
listener is on **port 9001**.

### 2.1 Backend → Pi (commands)

| Address | Args | Effect |
|---|---|---|
| `/sys/ping` | `reply_port:int` | Pi answers with `/sys/pong [origin_ip, type, hardware_id]` to the supplied port |
| `/trolley/enable` | `int 0\|1` | drive ENA pin (0 = disable, 1 = enable) |
| `/trolley/dir` | `int 0\|1` | raw DIR pin level (the firmware re-maps this through `calibration_direction`) |
| `/trolley/speed` | `float 0..1` | maps to pulse frequency, 0 = stopped, 1 = `1 / (2 × MIN_PULSE_DELAY_S)` |
| `/trolley/step` | `int N` | pulse `N` steps at the current speed/direction; aborts on home limit |
| `/trolley/stop` | — | drain queue + abort current motion |
| `/trolley/home` | — | drive toward the home limit switch until the ISR resets `position_steps=0` |
| `/trolley/position` | `float 0..1` | drive to a fraction of the calibrated rail length (see §4) |
| `/trolley/calibrate/start` | optional `str "forward"\|"reverse"` | drive away from home at calibration speed; if a direction is supplied, **persists** it as the new `calibration_direction` |
| `/trolley/calibrate/stop` | — | halt motion + record `calibration_candidate_steps` |
| `/trolley/calibrate/save` | — | write candidate to `device.json`, set `calibrated=1` |
| `/trolley/calibrate/cancel` | — | discard candidate, return to idle |
| `/trolley/config/set` | `str key`, value | stage one setting in memory (see §3 for valid keys) |
| `/trolley/config/save` | — | persist staged settings to `device.json` |
| `/trolley/config/get` | — | broadcast current settings as one `/trolley/config` JSON message |

### 2.2 Pi → backend (broadcasts)

| Address | Args | Cadence |
|---|---|---|
| `/sys/pong` | `[ip, type, hardware_id]` | reply to `/sys/ping` |
| `/trolley/status` | `[position, limit, homed, state, calibrated]` | unsolicited at 5 Hz once a `/sys/ping` has been received |
| `/trolley/config` | `[json_string]` | reply to `/trolley/config/get` |

Status field semantics:
- `position` — float 0..1, `position_steps / rail_length_steps`.
- `limit` — int 0/1, the home-end limit switch state.
- `homed` — int 0/1, set the moment the home switch trips while reversing.
- `state` — string `idle | homing | following | calibrating`.
- `calibrated` — int 0/1, true iff `device.json` has a non-null `rail_length_steps`.

The receiver (`admin/backend/engine/osc_receiver.py`) accepts the legacy 3-arg
shape (`[position, limit, homed]`) too, so older firmware revisions keep working.

---

## 3. Settings (per-Pi, persisted)

Stored in `~/.config/gpio-osc/device.json` under the `trolley` block. Source of
truth: `rpi-controller/trolley_settings.py`.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `rail_length_steps` | int or null | `null` | total step count between home and far end. `null` = uncalibrated |
| `lead_mm_per_rev` | float > 0 | `8.0` | leadscrew/belt pitch — informational, used by the UI to show mm |
| `steps_per_rev` | int > 0 | `200` | motor full-step count — informational |
| `microsteps` | int > 0 | `16` | driver microstep setting — informational |
| `max_speed_hz` | float > 0 | `2000` | playback ceiling for position-follow speed |
| `calibration_speed_hz` | float > 0 | `600` | speed used during the calibration span pass (deliberately slower) |
| `calibration_direction` | `"forward"\|"reverse"` | `"forward"` | which DIR-pin level drives **away** from home; flips wiring polarity |
| `soft_limit_pct` | float in (0, 1] | `0.98` | safety margin: `/trolley/position 1.0` lands at `rail_length_steps × soft_limit_pct` |
| `permissive_mode` | bool | **`true`** | allow `/trolley/position` to run on an unhomed/uncalibrated rig (bench testing) |

`/trolley/config/set` validates each value through `trolley_settings._coerce`
before accepting; bad values are logged and ignored client-side.

---

## 4. Position math

```
position_steps        # live counter, incremented per forward pulse, decremented per reverse
rail_length_steps     # ground truth from calibration
soft_limit_pct        # safety margin, default 0.98

# /trolley/position v   →
ceiling      = rail_length_steps × soft_limit_pct       # if calibrated
             = TROLLEY_MAX_STEPS (=20000)               # if NOT calibrated AND permissive_mode=true
target_steps = round(v × ceiling)
```

The motion thread then drives forward or reverse until `position_steps == target_steps`.

mm/rev/microstep settings do **not** influence the position math. They exist so
the UI (and the future calibration CLI) can convert between fraction and mm.

---

## 5. State machine

`controllers/trolley.py` runs a single background motion thread that reads from
a command queue. Module-level `state` is one of:

```
idle ── /trolley/home ──────────► homing  ── ISR/abort ─► idle (homed=1)
idle ── /trolley/position ──────► following ─► idle
idle ── /trolley/calibrate/start ► calibrating
calibrating ── /trolley/calibrate/stop  ─► calibrating (candidate set, idle physically)
calibrating ── /trolley/calibrate/save  ─► idle (calibrated=1, candidate persisted)
calibrating ── /trolley/calibrate/cancel ► idle
calibrating ── 5-min auto-timeout ──────► idle
```

Any new motion command sets `_abort_event` and drains the queue, so `Stop` is
always responsive (no race between "stop" and "next enqueue").

---

## 6. Calibration flow

The carriage is open-loop; calibration discovers `rail_length_steps` by driving
from one end to the other and counting pulses.

1. **Power-cycle.** `homed=0`, `calibrated=0`, `state=idle`.
2. **Home.** `/trolley/home` drives reverse until the home switch ISR fires.
   `position_steps` is forced to `0`, `homed` flips to `1`.
3. **Pick direction.** `/trolley/calibrate/start "forward"` or `"reverse"`.
   The chosen value is persisted as `calibration_direction` before motion
   starts, so home/calibrate remain consistent across reboots. State enters
   `calibrating`, `position_steps` resets to 0.
4. **Drive away from home.** Carriage moves at `calibration_speed_hz`.
   Position counter ticks up.
5. **Stop at the far end.** `/trolley/calibrate/stop` halts motion, snapshots
   `calibration_candidate_steps = position_steps`. State stays `calibrating`.
6. **Save.** `/trolley/calibrate/save` writes the candidate to
   `device.json:trolley.rail_length_steps`, reloads, sets `calibrated=1`,
   returns to `idle`. (Or **Cancel** discards.)
7. **Use.** `/trolley/position` is now bound to the calibrated rail length.

In **permissive mode** (default `true`) step 7 also works *without* steps 1–6,
falling back to a 20000-step placeholder span. Useful for bench testing without
limit switches wired.

---

## 7. Permissive mode

When `permissive_mode=true`:
- `/trolley/position` runs even with `homed=0` and/or `calibrated=0`.
- An uncalibrated rig uses `TROLLEY_MAX_STEPS = 20000` as the rail length.
- A `PERMISSIVE` warning is logged on every uncalibrated/unhomed call.

When `permissive_mode=false`:
- `/trolley/position` refuses (logs a clear "trolley not homed" /
  "not calibrated" message and does nothing) until the rig is properly
  homed and calibrated.

Recommended workflow: leave `permissive_mode=true` during commissioning; flip
it to `false` for the production show by sending
`/trolley/config/set permissive_mode 0` then `/trolley/config/save`.

---

## 8. Safety guards in firmware

| Guard | Where | What it does |
|---|---|---|
| Home limit ISR | `_home_limit_isr` in `controllers/trolley.py` | resets `position_steps=0`, sets `homed=1`, stops reverse motion |
| Soft forward limit | `_soft_limit_steps()` | `/trolley/position 1.0` lands at `rail_length_steps × soft_limit_pct` (default 98%) |
| Pulse-loop abort | `_pulse_once` | every commanded pulse checks `_abort_event` first |
| Race-proof stop | `_drain_queue + _abort_event.set()` | `/trolley/stop`, `/trolley/calibrate/stop`, and cancel all both *clear* the queue and *abort* — no wasted commands picked up after stop |
| Calibration timeout | motion-loop watchdog | a calibrating state with no commands for 300 s auto-cancels |

What is **not** guarded yet (known gaps):
- The far-end limit switch (BCM 21) is unread. A runaway forward `/position`
  is only protected by `soft_limit_pct`.
- `ALARM_1` / `ALARM_2` are unread. Driver faults during a show won't halt the
  pulse train.
- `PEND_1` / `PEND_2` are unread. They wouldn't help with position sensing
  even if read — they're per-burst events, not continuous signals.

---

## 9. Admin UI (web)

Live at `Trolleys page → click a trolley → trolley test panel`. Component:
`admin/frontend/src/components/trolley/TrolleyTestPanel.tsx`.

Status badges:
- **Online** / **Offline** dot (green/red) — driven by `/sys/ping` round-trip.
- **Homed** / **Not homed** — from `homed` in `/trolley/status`.
- **Calibrated** / **Not calibrated** — from `calibrated` in `/trolley/status`.
- **State** chip — `idle | homing | following | calibrating`.
- **⚠ limit** — flashes when the home switch is currently engaged.

Calibration card: numbered button row mirrors the OSC flow.
**1. Home → 2. Start → 3. Stop here → 4. Save**, with **Cancel** always
available. The radio above picks the calibration direction (forward/reverse).

Position slider: the explicit `/trolley/position` slider. **Disabled** until
the rig is homed AND calibrated. (When `permissive_mode=true` the firmware
would still accept the command — but the UI currently doesn't surface
permissive mode to the operator. Use the CLI tool or `/trolley/config/set` if
you need to slide before calibration.)

Motor settings (collapsible): editable form for `lead_mm_per_rev`,
`steps_per_rev`, `microsteps`, `max_speed_hz`, `calibration_speed_hz`,
`soft_limit_pct`. Click **Save settings** to push every changed value via
`/trolley/config/set` then commit with `/trolley/config/save`.

---

## 10. Backend playback

`POST /api/v1/playback/start` with `type=trolley-timeline` runs an event-based
trolley script. Before starting, it inspects every selected trolley's last
`/trolley/status` snapshot:

- If any target trolley reports `calibrated=0` and `permissive_mode` is false
  on that Pi, the backend returns `400 Bad Request` with an
  `uncalibrated_devices` list so the UI can show a clear error.
- Otherwise playback starts. Trolley timelines emit `/trolley/<command>`
  events at scheduled times; `/trolley/position` events use the same firmware
  guard rules as manual sends.

Trolley timelines are stored in `admin/backend/data/trolley_timelines/`.
Schema: `events` is a list of `{id, time, command, value?}` records sorted on
write.

---

## 11. Operator-facing CLI tools

Two tools, two purposes.

### 11.1 `rpi-controller/scripts/test_trolley.py` — direct-GPIO bench tool

Runs **on the Pi**. Bypasses the firmware entirely. Drives the GPIOs
directly. Useful for verifying wiring before booting the real service.

```bash
sudo systemctl stop gpio-osc-trolley
sudo ./rpi-controller/venv/bin/python rpi-controller/scripts/test_trolley.py
```

Menu actions:
- **Enable / disable driver (ENA)** — toggles the ENA pin.
- **Set direction (DIR)** — toggles the DIR pin.
- **Step N times at given speed (Hz)** — pulse loop. Aborts on either
  limit switch HIGH or either ALARM HIGH.
- **Read both limit switches (HOME / FAR)** — instantaneous reading of
  `LIM_HOME` (BCM 20) and `LIM_FAR` (BCM 21).
- **Read driver alarms (ALARM_1 / ALARM_2)** — instantaneous reading of
  `ALARM_1` (BCM 1) and `ALARM_2` (BCM 16).
- **Read PEND inputs (PEND_1 / PEND_2)** — instantaneous reading of
  `PEND_1` (BCM 7) and `PEND_2` (BCM 12).
- **Live monitor diagnostic inputs (5 s)** — polls all six diagnostic
  inputs at 10 Hz for 5 s and prints any change with timestamp + arrow.
  Use it to verify a limit switch by hand-pressing it, or to catch a driver
  alarm during a manual step burst.
- **Print pin snapshot** — one-line summary of every pin (DIR, ENA, all
  six diagnostic inputs).
- **Quit** — restores all pins to safe defaults and releases GPIO.

### 11.2 `rpi-controller/scripts/calibrate_trolley_osc.py` — OSC-driven CLI

Runs from any machine with `pythonosc` available. Drives the **live**
`gpio-osc-trolley` service over OSC. Useful when the admin UI is down or
when you want a scripted/loggable calibration session.

```bash
python3 rpi-controller/scripts/calibrate_trolley_osc.py --host 192.168.1.74
python3 rpi-controller/scripts/calibrate_trolley_osc.py --host 192.168.1.74 --verbose
```

Bootstrap:
1. Opens an ephemeral local UDP port for replies.
2. Sends `/sys/ping` and waits up to 3 s for `/sys/pong`. Exits 2 if
   unreachable; exits 3 if the device replies with the wrong type.
3. Sends `/trolley/config/get`. Prints the current settings dict.

Menu actions (exact mapping to OSC):
- `[1] Home` → `/trolley/home`. Watches state for up to 15 s.
- `[2] Start calibration (forward)` → `/trolley/calibrate/start "forward"`
  (also persists the direction). Refuses client-side if `homed=0`.
- `[3] Start calibration (reverse)` → `/trolley/calibrate/start "reverse"`.
- `[4] Stop here` → `/trolley/calibrate/stop`. Marks the session candidate
  flag so subsequent Save knows it's safe.
- `[5] Save calibration` → `/trolley/calibrate/save`. Re-fetches settings.
- `[6] Cancel calibration` → `/trolley/calibrate/cancel`.
- `[7] Re-read settings` → `/trolley/config/get`.
- `[8] Set a setting` → prompts for `key` (with valid-keys hint), then
  `value` (validated client-side via `trolley_settings._coerce`); sends
  `/trolley/config/set` then `/trolley/config/save`.
- `[9] Send /trolley/position` → prompts for `0..1`. Refuses unless
  `homed=1` AND `calibrated=1` (mirrors the strict firmware behaviour even
  though permissive mode would relax this).
- `[s] Stop motion` → `/trolley/stop`.
- `[q] Quit` → sends a final `/trolley/stop`, tears down the listener.

Logging:
- Every menu action timestamps a labelled section.
- State transitions from `/trolley/status` print as
  `state: idle → calibrating` once per transition.
- `--verbose` adds a per-packet trace for both directions.
- ANSI colours auto-disable when stdout is not a TTY.

---

## 12. Tests

`rpi-controller/tests/test_trolley.py` — pytest suite (105 tests at last
count). Coverage:

- GPIO setup/cleanup hygiene.
- Each raw OSC handler (enable, dir, speed, step, stop, home, position).
- Motion thread: step burst, position-follow, follow-then-new-target.
- Limit switch ISR semantics (resets only when reversing, ignores otherwise).
- Calibration state machine: start → stop snapshot → save persists,
  start → cancel discards, save without candidate refuses.
- Settings: stage-vs-save split, validation rejects bad keys/values,
  `calibration_direction` "forward"/"reverse" both round-trip.
- `permissive_mode`:
  - default-True path lets uncalibrated/unhomed `/trolley/position` enqueue a
    follow,
  - explicit-False path preserves the strict "refused" log.
- Soft-limit clamp: `/trolley/position 1.0` lands at `soft_limit_pct × rail`.
- HTTP test surface mirrors the OSC surface.
- Status payload shape: `[position, limit, homed, state, calibrated]`.

Run all of it:
```bash
cd rpi-controller && python3 -m pytest tests/ -q
```

`admin/backend/tests/` covers the wire shapes too (`test_osc_surfaces.py`
asserts every admin trigger maps to the exact OSC tuple,
`test_osc_receiver.py` covers legacy + extended status-payload parsing,
`test_playback_calibration_guard.py` covers the playback uncalibrated-refusal).

---

## 13. Quick reference — what each pin does, in one line

```
DIR       (BCM 23)   output  step direction → driver DR±
PUL       (BCM 18)   output  step pulse → driver PU±
ENA       (BCM 14)   output  drives driver MF±. LOW = motor enabled on this rig
LIM_HOME  (BCM 20)   input   home-end microswitch — HIGH when carriage is at home
LIM_FAR   (BCM 21)   input   far-end microswitch — HIGH at far end (bench tool only)
ALARM_1   (BCM 1)    input   driver ALM+ wire (bench tool only)
ALARM_2   (BCM 16)   input   driver ALM− wire (bench tool only — same single signal)
PEND_1    (BCM 7)    input   driver PEND+ wire (bench tool only)
PEND_2    (BCM 12)   input   driver PEND− wire (bench tool only — same single signal)
```
