# OSC wire runbook — manual verification on live hardware

Automated tests (`tests/test_osc_surfaces.py`) prove the **right command
at the right address leaves the backend**. This runbook covers the
other half: the OSC actually reaches the Pi and moves the physical
device. Work through it with a vents Pi + a trolley Pi both on the LAN.

## Prep

1. Pis running (`systemctl is-active gpio-osc-vents` / `-trolley`).
2. Admin launched, both devices registered on the Devices page, both
   heartbeat dots green.
3. Two terminal windows:
   - `ssh pi@<vents-ip>` — `journalctl -u gpio-osc-vents -f`
   - `ssh pi@<trolley-ip>` — `journalctl -u gpio-osc-trolley -f`
4. In the admin, expand the bottom **Activity** bar. It echoes every
   state transition and value drift — the admin-side half of each
   check.

For each row below:
- Admin: perform the listed action.
- Activity bar: confirm the line shown.
- Pi journal: confirm the line shown.
- Then mark ✓ / ✗.

If a row fails on either side, capture the Activity bar line + the
journal line and file it as a bug — the unit tests have already ruled
out a wrong address or type, so a failure here means either the
network (firewall / UDP blocked / wrong port on the device record) or
the Pi handler.

---

## Vents panel — per control

Go to the **Vents** page → **Test panel** tab → pick your vents card.

| # | Action | Expected journal line |
|---|---|---|
| V1  | Click **mode raw**               | `mode = raw` (or the vents controller's equivalent) |
| V2  | Click **mode auto**              | `mode = auto`, bang-bang loop resumes |
| V3  | Drag **target** slider to 22.5°C | `target set to 22.5` + mode forced to auto |
| V4  | Click **P1** (on)                | `peltier 1 ON` — cell clicks on. Mode flips to raw. |
| V5  | Click **P1** (off)               | `peltier 1 OFF` |
| V6  | Click **P2** (on)                | `peltier 2 ON` |
| V7  | Click **P3** (on)                | `peltier 3 ON` |
| V8  | Click **ALL OFF**                | mask=0, all three cells off |
| V9  | (no UI button → use Docs Quick Test `peltier_mask=7` or edit via script) | mask=7, all three cells on |
| V10 | Drag **Fan 1** slider to 50 %    | `fan1 duty = 50%` |
| V11 | Drag **Fan 2** slider to 80 %    | `fan2 duty = 80%` |
| V12 | Settings → Vents safety max → set 80 (which POSTs to `/vents/max_temp` per device) | `max_temp = 80.0`, persists to `~/.config/gpio-osc/vents_prefs.json` |

Safety bonus check: trigger over-temp (raise max_temp low, or heat the
probe) and confirm the Pi's state flips to `over_temp` and Peltiers
force-off; the admin's red banner should surface the device in
`vents_over_temp`.

---

## Trolley panel — per control

Go to the **Trolleys** page → **Test panel** tab → pick your trolley card.

| # | Action | Expected journal line |
|---|---|---|
| T1 | **Enable** ON    | `ENA LOW (enabled)` |
| T2 | **Enable** OFF   | `ENA HIGH (disabled)` |
| T3 | **Dir** forward  | `DIR = forward` |
| T4 | **Dir** reverse  | `DIR = reverse` |
| T5 | **Speed** slider to 0.5 | `speed = 0.5` (follow-loop delay updates) |
| T6 | **Step** count 1000, press **Step** | `stepping 1000 pulses` + motor runs |
| T7 | **Stop**         | `stop — abort in-flight motion` |
| T8 | **Home**         | reverse → limit-switch hit → `position = 0` |
| T9 | Goto (position) slider → 0.25 | `position follow → target_steps = MAX*0.25`, motor runs to target |

Also check the Pi's `/trolley/status` broadcast is coming back — the
admin card should show the live position tracking the target.

---

## Timeline playback

### Vents timeline

Go to **Vents** → **Timelines** → open a timeline with points (or
create `New Timeline`, duration 10s, add points at t=0 a=0.2 b=0.2 and
t=5 a=0.8 b=0.8).

| # | Action | Expected journal line |
|---|---|---|
| VP1 | Click Play | Journal floods with `fan1 duty = X%` / `fan2 duty = Y%` at ~30 Hz, X/Y following the curve. Activity bar logs `▶ timeline · <id>` and every A/B drift >2%. |
| VP2 | Settings → Output cap = 50, re-click Play | Same curves, but duty values halved. |
| VP3 | Register a second vents Pi and Play | Both journals receive the same fan duty stream. |
| VP4 | Click Stop | Journal shows `fan1 0`, `fan2 0`, peltier mask 0. Activity bar: `◼ stop @ Xs`. |

### Trolley timeline

Go to **Trolleys** → **Timelines** → pick `Example — Ping-pong` (the
built-in readonly example).

| # | Action | Expected journal line |
|---|---|---|
| TP1–TP7 | Click Play | Journal should see in order: `enable 1` @ t0, `home` @ t2, then six `position 0/1` bangs at 4s intervals, then `enable 0` at t40. Motor actually runs between those positions. Activity bar logs each bang. |
| TP8 | Edit a custom timeline with `enable`, `dir`, `speed`, `position`, `step`, `stop`, `home` all at the same t (say t=2) | Journal shows them fire in the fixed order enable → dir → speed → position → step → stop → home. |
| TP9 | At timeline end with `loop=false` | Journal: `stop` to every targeted trolley. |

---

## Docs Quick Test

Go to **Docs** → **Protocol reference** → expand a row → click **Send
test** (requires picking a device from the Quick Test dropdown).

| # | Action | Expected |
|---|---|---|
| D1 | `/vents/fan/1` with default arg on a vents device | Journal shows fan 1 duty update |
| D2 | `/trolley/speed` 0.3 on a trolley device | Journal shows speed change |
| D3 | `/vents/fan/1` when trolley is the selected device | Admin toast: type mismatch, no OSC |
| D4 | `/sys/ping 9001` on any device | Pi sends `/sys/pong` back; admin's Last-seen column updates to "just now" |

---

## OSC Bridge

Enable bridge in Settings (routing `type-match`, port 9002). Use
another machine or `python -m pythonosc.send_message` to inject.

| # | Inbound (from external) | Expected |
|---|---|---|
| B1 | `/to/<trolley-id>/trolley/speed 0.4` → udp://admin:9002 | Only that trolley receives `/trolley/speed 0.4`. Admin's Bridge page event row shows `→ <trolley>`, address rewritten. |
| B2 | `/vents/fan/1 0.3` (routing=type-match) | Every vents Pi receives it, trolley Pis do not. |
| B3 | `/trolley/speed 0.2` (routing=type-match) | Every trolley Pi receives it, vents Pis do not. |
| B4 | `/sys/ping 9001` | Every Pi receives it. |
| B5 | `/custom/anything 1` (routing=passthrough) | Every Pi receives it (most handlers drop it, but it arrives). |
| B6 | Any (routing=none) | No Pi receives anything; Bridge event row shows `⊘ routing=none`. |

---

## Closing check

After the full run, backend tests should still be green:

```
cd admin/backend && .venv/bin/pytest tests/ -q
```

Commit any findings as bugs with a link to the failing row above.
