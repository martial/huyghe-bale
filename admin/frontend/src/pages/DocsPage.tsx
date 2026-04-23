import { useEffect, useState } from "react";
import { listDevices } from "../api/devices";
import { getSettings } from "../api/settings";
import type { Settings } from "../api/settings";
import {
  filterDevicesForOscAddress,
  protocolTestBridge,
  protocolTestHttp,
  protocolTestOsc,
} from "../api/protocol-test";
import type { Device } from "../types/device";
import { formatQuickTestPreview, resolveQuickTest, type QuickTestSpec } from "./docsQuickTest";

/**
 * Protocol reference for every OSC address and HTTP endpoint the system speaks.
 *
 * Content is hard-coded from what the codebase implements today:
 *   - vents  → rpi-controller/controllers/vents.py, admin/backend/engine/playback.py
 *   - trolley → rpi-controller/controllers/trolley.py, admin/backend/api/trolley_control.py
 *   - system → rpi-controller/gpio_osc.py, admin/backend/engine/osc_receiver.py
 *
 * Keep this file in sync by grepping for the addresses above when they change.
 */

type Direction = "admin-to-pi" | "pi-to-admin" | "http";

interface Endpoint {
  address: string;
  direction: Direction;
  args?: string;
  description: string;
  example?: string;
}

interface Section {
  id: string;
  title: string;
  subtitle: string;
  transport: { osc?: string; http?: string };
  groups: { label: string; direction: Direction; items: Endpoint[] }[];
}

const VENTS: Section = {
  id: "vents",
  title: "Vents",
  subtitle:
    "Thermoelectric stacks (3 cells on GPIO 26/25/24): each module has a cold face and a hot face — powered, heat is pumped from one side to the other. Fan 1 (GPIO 20) serves the cold-side heat exchanger, fan 2 (GPIO 18) the hot-side box (see tachos A/B per fan). Two DS18B20 probes read those air paths (temp1 / temp2 in status). Auto mode compares the average of both readings to /vents/target with bang‑bang Peltier power (states heating = all cells on, cooling = all off, holding = deadband); it does not PWM fans for regulation. Max (persisted on the Pi) is a separate safety ceiling — above max, over_temp (Peltiers off; fan duty unchanged) and the admin banner.",
  transport: { osc: "UDP 9000 (admin → Pi) · UDP 9001 (Pi → admin)", http: "http://<ip>:9001" },
  groups: [
    {
      label: "OSC — admin → Pi (raw)",
      direction: "admin-to-pi",
      items: [
        {
          address: "/vents/peltier/1",
          direction: "admin-to-pi",
          args: "int 0|1",
          description:
            "Cell 1 on/off (BCM GPIO 26, active HIGH). Sending any value forces mode=raw unless blocked: while average temp exceeds the safety max (see /vents/max_temp), turning on is ignored (cells stay off).",
        },
        {
          address: "/vents/peltier/2",
          direction: "admin-to-pi",
          args: "int 0|1",
          description:
            "Cell 2 on/off (BCM GPIO 25, active HIGH). Forces mode=raw unless over-temperature interlock applies (same as cell 1).",
        },
        {
          address: "/vents/peltier/3",
          direction: "admin-to-pi",
          args: "int 0|1",
          description:
            "Cell 3 on/off (BCM GPIO 24, active HIGH). Forces mode=raw unless over-temperature interlock applies (same as cell 1).",
        },
        {
          address: "/vents/peltier",
          direction: "admin-to-pi",
          args: "int mask 0..7",
          description:
            "Set all three cells at once as a bitmask (bit 0 = P1, bit 1 = P2, bit 2 = P3). Forces mode=raw; non-zero masks are clamped to off while over-temperature interlock applies.",
          example: "/vents/peltier 5   # P1 + P3",
        },
        {
          address: "/vents/fan/1",
          direction: "admin-to-pi",
          args: "float 0..1",
          description: "Cold-side fan PWM duty (BCM GPIO 20, 1 kHz). Forces mode=raw.",
        },
        {
          address: "/vents/fan/2",
          direction: "admin-to-pi",
          args: "float 0..1",
          description: "Hot-side fan PWM duty (BCM GPIO 18, 1 kHz). Forces mode=raw.",
        },
      ],
    },
        {
          label: "OSC — admin → Pi (auto-regulation)",
          direction: "admin-to-pi",
          items: [
            {
              address: "/vents/max_temp",
              direction: "admin-to-pi",
              args: "float °C",
              description:
                "Safety ceiling (°C): independent of target. If average temp exceeds this value, over_temp — all Peltiers off; auto does not change fan PWM. Persisted at ~/.config/gpio-osc/vents_prefs.json; must stay above the regulation band (Pi may bump the value). Also set from Admin → Settings.",
            },
            {
              address: "/vents/mode",
          direction: "admin-to-pi",
          args: "string raw|auto",
          description:
            "'raw' = manual Peltiers and fans. 'auto' = bang‑bang uses Peltiers only toward /vents/target (±0.5°C band); fans are not driven for thermoregulation — switching to auto zeros fan PWM once. Use /vents/fan/* or raw mode for airflow.",
        },
        {
          address: "/vents/target",
          direction: "admin-to-pi",
          args: "float °C",
          description:
            "Regulation setpoint (°C): auto bang-bang on cell power — below target−0.5°C all cells on (state heating: thermoelectric heat pump active); above target+0.5°C and under max all off (state cooling: no pumping). Deadband holds the previous mask. Labels refer to control action, not which physical face is hot/cold. Fans unchanged by auto. Safety max separate (Settings, /vents/max_temp). Pi clamps target/max so the band stays below max.",
        },
      ],
    },
    {
      label: "OSC — Pi → admin (push)",
      direction: "pi-to-admin",
      items: [
        {
          address: "/vents/status",
          direction: "pi-to-admin",
          args:
            "float temp1_c, float temp2_c, float fan1, float fan2, int peltier_mask, int rpm1A, int rpm1B, int rpm2A, int rpm2B, float target_c, string mode, string state, float max_temp_c",
          description:
            "Broadcast at 5 Hz to the last admin that pinged. Missing DS18B20 sensors report -1.0. state ∈ {idle, heating, cooling, holding, sensor_error, over_temp}. Older firmware omits the final max_temp_c arg. GET /health lists vents in over_temp for the banner.",
        },
      ],
    },
    {
      label: "HTTP — on the Pi",
      direction: "http",
      items: [
        {
          address: "GET /status",
          direction: "http",
          description:
            "JSON snapshot: uptime, last_osc, version, system_info (model/OS/RAM/CPU temp/disk), device_type, hardware_id.",
        },
        {
          address: "POST /gpio/test",
          direction: "http",
          args:
            '{command: "peltier"|"peltier_mask"|"fan"|"mode"|"target"|"max_temp", index?: 1..3, value: …}',
          description:
            "Runs the same handler as the matching OSC address, bypassing UDP. Returns {ok, …current status snapshot}.",
          example:
            'curl -XPOST -d \'{"command":"target","value":22.0}\' http://<ip>:9001/gpio/test',
        },
        {
          address: "POST /update",
          direction: "http",
          description:
            "Triggers auto_update.sh on the Pi; systemd service restarts on success. Admin proxies this from the Devices page.",
        },
      ],
    },
  ],
};

const TROLLEY: Section = {
  id: "trolley",
  title: "Trolley",
  subtitle:
    "Stepper driver (DIR / PUL / ENA, active-LOW enable) with a limit switch at the home end. Motion runs on a Pi-side thread; /trolley/stop and any new command abort whatever's running.",
  transport: { osc: "UDP 9000 (admin → Pi) · UDP 9001 (Pi → admin)", http: "http://<ip>:9001" },
  groups: [
    {
      label: "OSC — admin → Pi (raw)",
      direction: "admin-to-pi",
      items: [
        {
          address: "/trolley/enable",
          direction: "admin-to-pi",
          args: "int 0|1",
          description:
            "Drive ENA pin. Active LOW: 1 pulls LOW (driver engaged, holding torque), 0 pulls HIGH (coasts).",
        },
        {
          address: "/trolley/dir",
          direction: "admin-to-pi",
          args: "int 0|1",
          description: "Direction pin. 0 = reverse (toward home / limit switch), 1 = forward.",
        },
        {
          address: "/trolley/speed",
          direction: "admin-to-pi",
          args: "float 0..1",
          description:
            "Pulse frequency. 0 = stopped, 1 ≈ 1 kHz (capped by TROLLEY_MIN_PULSE_DELAY_S). Used by subsequent /trolley/step and /trolley/position.",
        },
        {
          address: "/trolley/step",
          direction: "admin-to-pi",
          args: "int N",
          description:
            "Burst N pulses at the current dir and speed. Aborts on limit switch or any new /trolley/* command.",
          example: "/trolley/step 2000",
        },
        {
          address: "/trolley/stop",
          direction: "admin-to-pi",
          description:
            "Cancel any running burst or position follow. Holding torque stays on if enabled.",
        },
        {
          address: "/trolley/home",
          direction: "admin-to-pi",
          description:
            "Auto-enables, then drives reverse until the limit switch trips. Position is forced to 0 by the ISR; homed = true.",
        },
      ],
    },
    {
      label: "OSC — admin → Pi (position)",
      direction: "admin-to-pi",
      items: [
        {
          address: "/trolley/position",
          direction: "admin-to-pi",
          args: "float 0..1",
          description:
            "Target position along the rail (0 = home, 1 = far end = TROLLEY_MAX_STEPS). Controller runs a follow loop toward the target at the last /trolley/speed (or default). Sent as a bang by trolley-timeline playback (the Pi-side follow loop handles smooth motion — no per-tick traffic).",
          example: "/trolley/position 0.42",
        },
      ],
    },
    {
      label: "OSC — Pi → admin",
      direction: "pi-to-admin",
      items: [
        {
          address: "/trolley/status",
          direction: "pi-to-admin",
          args: "float position_0_1, int limit, int homed",
          description:
            "Broadcast by the Pi at TROLLEY_STATUS_HZ (5 Hz) to the last ping-replier's port. The backend's OscReceiver stores it and exposes it at GET /api/v1/trolley-control/<device_id>/status for the admin test panel.",
        },
      ],
    },
    {
      label: "HTTP — on the Pi",
      direction: "http",
      items: [
        {
          address: "GET /status",
          direction: "http",
          description:
            "Same shape as vents — uptime, last_osc, version, system_info, device_type (\"trolley\"), hardware_id.",
        },
        {
          address: "POST /gpio/test",
          direction: "http",
          args: '{command: "enable"|"dir"|"speed"|"step"|"stop"|"home"|"position", value: …}',
          description:
            "Runs the same handler as the matching OSC address, bypassing UDP. Returns {ok, position_steps, max_steps, homed, limit, enabled}.",
          example:
            'curl -XPOST -d \'{"command":"position","value":0.5}\' http://<ip>:9001/gpio/test',
        },
        {
          address: "POST /update",
          direction: "http",
          description: "Triggers auto_update.sh, restarts the gpio-osc-trolley service.",
        },
      ],
    },
  ],
};

const SYSTEM: Section = {
  id: "system",
  title: "System (every device)",
  subtitle:
    "Device discovery / identity protocol. The admin broadcasts /sys/ping; each Pi replies with /sys/pong carrying (ip, type, hardware_id) so the backend can identify the personality behind each IP.",
  transport: { osc: "UDP 9000 (admin → Pi) · UDP 9001 (Pi → admin)" },
  groups: [
    {
      label: "OSC — admin → Pi",
      direction: "admin-to-pi",
      items: [
        {
          address: "/sys/ping",
          direction: "admin-to-pi",
          args: "int return_port",
          description:
            "Sent every 5 s by the backend's SSE status stream (admin/backend/api/devices.py). The Pi replies to client_address[0] at return_port.",
        },
      ],
    },
    {
      label: "OSC — Pi → admin",
      direction: "pi-to-admin",
      items: [
        {
          address: "/sys/pong",
          direction: "pi-to-admin",
          args: "string origin_ip, string device_type, string hardware_id",
          description:
            "Pi's reply to /sys/ping. hardware_id is {type}_{8hex} persisted at ~/.config/gpio-osc/device.json. Legacy Pis send 1 arg — the backend defaults those to type=vents.",
        },
      ],
    },
  ],
};

const BRIDGE: Section = {
  id: "bridge",
  title: "Bridge (external source → admin → devices)",
  subtitle:
    "Optional OSC listener on the admin host. Point an external source (Max, TouchDesigner, show controller) at the bridge port; the admin forwards each incoming message to the devices that care about its address. Live feed at /bridge. Enable + configure in Settings.",
  transport: { osc: "UDP (default 9002, configurable)" },
  groups: [
    {
      label: "OSC — external → admin (anything)",
      direction: "admin-to-pi",
      items: [
        {
          address: "/<any-address>",
          direction: "admin-to-pi",
          args: "any",
          description:
            "Every message reaching the bridge port is logged into a 500-entry ring buffer and dispatched to devices according to the Routing setting.",
          example: "oscsend <admin-ip> 9002 /vents/fan/1 f 0.5",
        },
      ],
    },
    {
      label: "Routing modes (Settings → OSC Bridge → Routing)",
      direction: "admin-to-pi",
      items: [
        {
          address: "type-match (default)",
          direction: "admin-to-pi",
          description:
            "/vents/* → forwarded to every vents device. /trolley/* → every trolley device. /sys/* → every device. Any other prefix is logged as 'no type-matching device' and not forwarded.",
        },
        {
          address: "passthrough",
          direction: "admin-to-pi",
          description:
            "Every message is forwarded verbatim to every device regardless of address prefix. Use when the source is driving custom addresses.",
        },
        {
          address: "none",
          direction: "admin-to-pi",
          description:
            "Tap-only. Messages are logged in the live feed but never forwarded. Useful for inspecting what a source is sending without side effects.",
        },
      ],
    },
    {
      label: "Targeting a single device (overrides routing mode)",
      direction: "admin-to-pi",
      items: [
        {
          address: "/to/<identifier>/<real-address>",
          direction: "admin-to-pi",
          args: "any",
          description:
            "Prefix any address with /to/<identifier>/ and the bridge forwards only to that one device, regardless of routing mode. <identifier> matches (in order): device id, name, IP address, or hardware id. Match is exact and case-sensitive. Name renames take effect immediately — the bridge re-reads the device store on every message. Unknown identifier → event logged with dropped=\"no device matching '<x>'\" and not forwarded.",
          example:
            "oscsend <admin-ip> 9002 /to/vents-1/vents/fan/1 f 0.5\noscsend <admin-ip> 9002 /to/192.168.1.74/vents/target f 20\noscsend <admin-ip> 9002 /to/vents_a1b2c3d4/vents/mode s auto",
        },
        {
          address: "Name constraints",
          direction: "admin-to-pi",
          description:
            "Device names are auto-trimmed on save and cannot contain '/' (conflicts with /to/<name>/… parsing). Empty names rejected. Names are not enforced unique — if two devices share a name, the first match wins by store order. Use IPs or hardware ids to be unambiguous.",
        },
        {
          address: "Event log shape",
          direction: "admin-to-pi",
          description:
            "Each forwarded /to/ message shows in the feed with a 'forwarded_as' field equal to the unwrapped address that was actually sent. GET /api/v1/bridge/state returns the current 500-entry ring buffer; GET /api/v1/bridge/stream is an SSE feed pushing each event as it arrives.",
        },
      ],
    },
  ],
};

const SECTIONS: Section[] = [VENTS, TROLLEY, SYSTEM, BRIDGE];

const DIR_MD: Record<Direction, string> = {
  "admin-to-pi": "admin → Pi",
  "pi-to-admin": "Pi → admin",
  http: "HTTP (on the Pi)",
};

function flowLabelForMarkdown(section: Section, groupLabel: string, item: Endpoint): string {
  if (section.id === "bridge" && groupLabel.includes("external → admin")) {
    return "External → admin";
  }
  return DIR_MD[item.direction];
}

/** Markdown technical sheet: single source of truth is SECTIONS (same data as the Protocol UI). */
function sectionsToMarkdown(sections: Section[]): string {
  const date = new Date().toISOString().slice(0, 10);
  const lines: string[] = [
    "# OSC technical sheet — Huyghe Bale",
    "",
    `Generated: ${date}`,
    "",
    "OSC and HTTP reference for the Pi controllers and the admin OSC Bridge (including routing and per-device targeting).",
    "Ports: UDP from admin to Pi is typically 9000; Pi replies to the admin on 9001; the Bridge listens on the admin host (default 9002, configurable in Settings).",
    "",
  ];

  for (const sec of sections) {
    lines.push(`## ${sec.title}`);
    lines.push("");
    lines.push(sec.subtitle);
    lines.push("");
    const t: string[] = [];
    if (sec.transport.osc) t.push(`**OSC:** ${sec.transport.osc}`);
    if (sec.transport.http) t.push(`**HTTP:** ${sec.transport.http}`);
    if (t.length) {
      lines.push(t.join("  \n"));
      lines.push("");
    }

    for (const g of sec.groups) {
      lines.push(`### ${g.label}`);
      lines.push("");
      for (const item of g.items) {
        const addr = item.address.includes("`") ? item.address.replace(/`/g, "'") : item.address;
        lines.push(`#### \`${addr}\``);
        lines.push("");
        lines.push(`- **Flow:** ${flowLabelForMarkdown(sec, g.label, item)}`);
        if (item.args) lines.push(`- **Args:** ${item.args}`);
        lines.push(`- **Description:** ${item.description}`);
        if (item.example) {
          lines.push("");
          lines.push("Example:");
          lines.push("");
          lines.push("```");
          lines.push(item.example);
          lines.push("```");
        }
        lines.push("");
      }
    }
  }

  lines.push("---");
  lines.push("");
  lines.push(
    "*Source of truth in repo:* `rpi-controller/controllers/*.py`, `rpi-controller/gpio_osc.py`, `admin/backend/api/*.py`, `admin/backend/engine/osc_receiver.py`, `admin/backend/engine/osc_bridge.py`."
  );
  return lines.join("\n");
}

function downloadOscTechnicalSheet(): void {
  const md = sectionsToMarkdown(SECTIONS);
  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `huyghe-bale-osc-protocol-${new Date().toISOString().slice(0, 10)}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

const DIR_BADGE: Record<Direction, { label: string; cls: string }> = {
  "admin-to-pi": {
    label: "admin → Pi",
    cls: "bg-orange-500/10 text-orange-300 border-orange-500/30",
  },
  "pi-to-admin": {
    label: "Pi → admin",
    cls: "bg-sky-500/10 text-sky-300 border-sky-500/30",
  },
  http: {
    label: "HTTP",
    cls: "bg-zinc-500/10 text-zinc-300 border-zinc-500/30",
  },
};

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`w-4 h-4 text-zinc-500 transition-transform duration-200 ${open ? "rotate-90" : ""}`}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8.25 4.5l7.5 7.5-7.5 7.5" />
    </svg>
  );
}

function CopyButton({ text, alwaysVisible = false }: { text: string; alwaysVisible?: boolean }) {
  const [copied, setCopied] = useState(false);
  const baseOpacity = alwaysVisible
    ? "opacity-60 group-hover:opacity-100"
    : "opacity-0 group-hover:opacity-100";
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard?.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        });
      }}
      className={`inline-flex items-center gap-1 px-2 py-1 rounded text-[10px] uppercase tracking-wider font-semibold text-zinc-400 hover:text-white hover:bg-white/5 transition-all ${baseOpacity}`}
      title="Copy to clipboard"
    >
      {copied ? (
        <>
          <svg className="w-3 h-3 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          copied
        </>
      ) : (
        <>
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h6a2 2 0 002-2M8 5a2 2 0 012-2h6a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
          </svg>
          copy
        </>
      )}
    </button>
  );
}

function detectLang(code: string): string {
  const first = code.trimStart().split("\n", 1)[0];
  if (/^#\s*!.*\b(bash|sh)\b/.test(first)) return "bash";
  if (/^(curl|sudo|ssh|cd|ls|apt|systemctl|journalctl)\b/.test(first)) return "bash";
  if (/^\s*(GET|POST|PUT|DELETE|PATCH)\s/i.test(first)) return "http";
  return "shell";
}

function renderCodeLines(code: string) {
  return code.split("\n").map((line, i) => {
    if (line.trimStart().startsWith("#")) {
      return (
        <span key={i} className="text-zinc-500 italic">
          {line}
          {"\n"}
        </span>
      );
    }
    return (
      <span key={i} className="text-zinc-100">
        {line}
        {"\n"}
      </span>
    );
  });
}

function CodeBlock({ code }: { code: string }) {
  const lang = detectLang(code);
  return (
    <div className="group relative rounded-lg overflow-hidden border border-white/10 bg-zinc-950">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-white/5 bg-white/[0.02]">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5">
            <span className="w-2 h-2 rounded-full bg-red-500/40" />
            <span className="w-2 h-2 rounded-full bg-yellow-500/40" />
            <span className="w-2 h-2 rounded-full bg-green-500/40" />
          </div>
          <span className="text-[10px] uppercase tracking-wider font-medium text-zinc-500">{lang}</span>
        </div>
        <CopyButton text={code} alwaysVisible />
      </div>
      <pre className="px-4 py-3 text-[12.5px] leading-relaxed font-mono overflow-x-auto whitespace-pre">
        <code>{renderCodeLines(code)}</code>
      </pre>
    </div>
  );
}

function ProtocolQuickTestInner({
  qt,
  item,
  devices,
  bridgeEnabled,
}: {
  qt: QuickTestSpec;
  item: Endpoint;
  devices: Device[];
  bridgeEnabled: boolean;
}) {
  const [deviceId, setDeviceId] = useState("");
  const [busy, setBusy] = useState(false);
  const [hint, setHint] = useState<string | null>(null);
  const preview = formatQuickTestPreview(qt);

  const needsDevice =
    qt.kind === "osc" ||
    qt.kind === "http" ||
    (qt.kind === "bridge" && qt.variant === "to");

  const candidates =
    qt.kind === "osc"
      ? filterDevicesForOscAddress(devices, item.address)
      : qt.kind === "http"
        ? devices.filter((d) => d.ip_address)
        : qt.kind === "bridge" && qt.variant === "to"
          ? devices.filter((d) => d.ip_address)
          : [];

  async function run() {
    setHint(null);
    if (qt.kind === "bridge" && !bridgeEnabled) {
      setHint("Enable Bridge in Settings");
      return;
    }
    if (needsDevice && !deviceId) {
      setHint("Select a device");
      return;
    }
    setBusy(true);
    try {
      if (qt.kind === "osc") {
        await protocolTestOsc({ device_id: deviceId, address: item.address, values: qt.values });
        setHint("Sent");
      } else if (qt.kind === "http") {
        await protocolTestHttp({
          device_id: deviceId,
          method: qt.method,
          path: qt.path,
          json: qt.json,
        });
        setHint("OK");
      } else if (qt.kind === "bridge" && qt.variant === "direct") {
        await protocolTestBridge({ address: qt.address, values: qt.values });
        setHint("Sent");
      } else if (qt.kind === "bridge" && qt.variant === "to") {
        await protocolTestBridge({
          inner_address: qt.innerAddress,
          device_id: deviceId,
          values: qt.values,
        });
        setHint("Sent");
      }
    } catch (e) {
      setHint(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 rounded-lg border border-white/[0.07] bg-black/30 px-3 py-2.5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between sm:gap-4">
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-[10px] uppercase tracking-wider font-medium text-zinc-500">Quick test payload</p>
          <code className="block text-[11px] font-mono text-zinc-300/95 leading-relaxed break-all">{preview}</code>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          {needsDevice && (
            <select
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
              className="text-xs rounded-lg border border-white/12 bg-zinc-950 text-zinc-200 px-2.5 py-2 min-h-[36px] max-w-[min(100%,240px)] focus:outline-none focus:ring-2 focus:ring-orange-500/25 focus:border-orange-500/30"
            >
              <option value="">Choose device…</option>
              {candidates.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} · {d.ip_address || "—"}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            onClick={run}
            disabled={busy}
            className="text-xs font-semibold rounded-lg bg-orange-500/15 border border-orange-500/25 text-orange-300 px-3 py-2 min-h-[36px] hover:bg-orange-500/25 disabled:opacity-45 transition-colors"
          >
            {busy ? "Sending…" : "Send test"}
          </button>
          {hint && (
            <span
              className={`text-[11px] tabular-nums ${hint === "Sent" || hint === "OK" ? "text-emerald-400/95" : "text-amber-400/90"}`}
            >
              {hint}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function ProtocolQuickTest({
  sectionId,
  item,
  devices,
  bridgeEnabled,
}: {
  sectionId: string;
  item: Endpoint;
  devices: Device[];
  bridgeEnabled: boolean;
}) {
  const qt = resolveQuickTest(sectionId, item.direction, item.address);
  if (!qt) return null;
  return (
    <ProtocolQuickTestInner qt={qt} item={item} devices={devices} bridgeEnabled={bridgeEnabled} />
  );
}

function EndpointRow({
  item,
  sectionId,
  devices,
  bridgeEnabled,
}: {
  item: Endpoint;
  sectionId: string;
  devices: Device[];
  bridgeEnabled: boolean;
}) {
  const isHttp = item.direction === "http";
  const isPiInbound = item.direction === "pi-to-admin";
  const addrCls = isHttp
    ? "text-emerald-200/90"
    : isPiInbound
      ? "text-sky-200/90"
      : "text-orange-200/90";
  return (
    <div className="group rounded-xl border border-white/[0.07] bg-zinc-950/35 hover:border-white/[0.12] transition-colors overflow-hidden">
      <div className="px-4 pt-4 pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <code className={`text-[13px] font-mono font-medium tracking-tight bg-black/35 border border-white/[0.08] rounded-md px-2.5 py-1 ${addrCls}`}>
            {item.address}
          </code>
          {!isHttp && (
            <span
              className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-medium border ${DIR_BADGE[item.direction].cls}`}
            >
              {DIR_BADGE[item.direction].label}
            </span>
          )}
          {item.args && (
            <code className="text-[11px] font-mono text-zinc-500">{item.args}</code>
          )}
          <CopyButton text={item.address} />
        </div>
        {isPiInbound && (
          <p className="mt-3 text-[11px] text-zinc-500 leading-relaxed border-l-2 border-sky-500/25 pl-3">
            Sent by the Pi toward the admin — nothing to fire from here. Use device status or the Bridge feed to observe.
          </p>
        )}
        {!isPiInbound && (
          <ProtocolQuickTest sectionId={sectionId} item={item} devices={devices} bridgeEnabled={bridgeEnabled} />
        )}
      </div>
      <div className="border-t border-white/[0.05] px-4 py-3 bg-black/15">
        <p className="text-[13px] text-zinc-400 leading-relaxed">{item.description}</p>
        {item.example && (
          <div className="mt-3">
            <CodeBlock code={item.example} />
          </div>
        )}
      </div>
    </div>
  );
}

function SectionBlock({
  section,
  open,
  onToggle,
  devices,
  bridgeEnabled,
}: {
  section: Section;
  open: boolean;
  onToggle: () => void;
  devices: Device[];
  bridgeEnabled: boolean;
}) {
  return (
    <div className="rounded-2xl border border-white/[0.07] bg-zinc-900/50 backdrop-blur-sm overflow-hidden shadow-sm shadow-black/20">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-start gap-3 px-5 py-4 text-left hover:bg-white/[0.03] transition-all"
      >
        <div className="pt-1">
          <ChevronIcon open={open} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-xl font-medium text-white">{section.title}</h3>
          <p className="text-sm text-zinc-400 mt-1">{section.subtitle}</p>
        </div>
      </button>

      {open && (
        <div className="px-5 pb-5 space-y-4">
          {(() => {
            const oscGroups = section.groups.filter((g) => g.direction !== "http");
            const httpGroups = section.groups.filter((g) => g.direction === "http");
            return (
              <>
                {oscGroups.length > 0 && (
                  <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] overflow-hidden">
                    <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-b border-white/[0.06] bg-black/20">
                      <span className="inline-flex items-center rounded-md bg-orange-500/15 border border-orange-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-orange-300">
                        OSC
                      </span>
                      {section.transport.osc && (
                        <span className="text-[11px] font-mono text-zinc-500">{section.transport.osc}</span>
                      )}
                    </div>
                    <div className="p-4 space-y-4">
                      {oscGroups.map((g) => (
                        <div key={g.label}>
                          <h4 className="text-[10px] uppercase tracking-wider font-medium text-zinc-500 mb-2">
                            {g.label}
                          </h4>
                          <div className="space-y-3">
                            {g.items.map((item) => (
                              <EndpointRow
                                key={`${section.id}-${g.label}-${item.address}`}
                                item={item}
                                sectionId={section.id}
                                devices={devices}
                                bridgeEnabled={bridgeEnabled}
                              />
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {httpGroups.length > 0 && (
                  <div className="rounded-xl border border-white/[0.07] bg-white/[0.02] overflow-hidden">
                    <div className="flex flex-wrap items-center gap-2 px-4 py-2.5 border-b border-white/[0.06] bg-black/20">
                      <span className="inline-flex items-center rounded-md bg-emerald-500/12 border border-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-300">
                        HTTP
                      </span>
                      {section.transport.http && (
                        <span className="text-[11px] font-mono text-zinc-500">{section.transport.http}</span>
                      )}
                    </div>
                    <div className="p-4 space-y-4">
                      {httpGroups.map((g) => (
                        <div key={g.label}>
                          <h4 className="text-[10px] uppercase tracking-wider font-medium text-zinc-500 mb-2">
                            {g.label}
                          </h4>
                          <div className="space-y-3">
                            {g.items.map((item) => (
                              <EndpointRow
                                key={`${section.id}-${g.label}-${item.address}`}
                                item={item}
                                sectionId={section.id}
                                devices={devices}
                                bridgeEnabled={bridgeEnabled}
                              />
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            );
          })()}
        </div>
      )}
    </div>
  );
}

// ── Install guide ─────────────────────────────────────────────────────────

interface InstallStep {
  title: string;
  body: string;
  code?: string | string[];
}

const INSTALL_STEPS: InstallStep[] = [
  {
    title: "Prerequisites",
    body:
      "You need a Raspberry Pi 4 or Pi 5 running Raspberry Pi OS (Lite 64-bit recommended), already on the network, with SSH enabled and reachable. You'll also need sudo on the Pi.",
  },
  {
    title: "SSH in",
    body:
      "From your laptop, connect to the Pi. Replace <pi-ip> with the Pi's LAN address (or <pi-hostname>.local if mDNS works on your network).",
    code: "ssh pi@<pi-ip>",
  },
  {
    title: "Run the one-liner installer",
    body:
      "This downloads and runs install.sh from Google Cloud Storage. It installs git if missing, clones the repo into ~/huyghe-bale, then hands off to rpi-controller/install.sh — which creates a Python venv, installs dependencies (rpi-lgpio on Pi 5), generates the device identity, writes a systemd unit, and starts it. Re-running is idempotent: it'll git pull and re-install instead of re-cloning.",
    code: [
      "# vents device (L298N fan driver)\ncurl -sSL https://storage.googleapis.com/apps-screen-club/huyghe-bale/install.sh \\\n  | sudo bash -s -- --type=vents",
      "# trolley device (stepper + limit switch)\ncurl -sSL https://storage.googleapis.com/apps-screen-club/huyghe-bale/install.sh \\\n  | sudo bash -s -- --type=trolley",
    ],
  },
  {
    title: "Verify the service is running",
    body:
      "The service name depends on the type you picked. You should see 'active (running)'. Logs live in the systemd journal — follow them with journalctl -f to watch OSC messages arrive in real time.",
    code:
      "sudo systemctl status gpio-osc-vents    # or gpio-osc-trolley\njournalctl -u gpio-osc-vents -f          # live log",
  },
  {
    title: "Add the device in the admin",
    body:
      "Open the admin app, go to Devices, and either click Scan (finds Pis on the subnet and auto-fills name/IP/type from the /sys/pong reply) or add it manually with the Pi's IP and port 9000. Within a few seconds the heartbeat dot should turn green. The hardware_id shown on the card is the one persisted on the Pi at ~/.config/gpio-osc/device.json — it stays the same across IP changes.",
  },
  {
    title: "Updating a Pi later",
    body:
      "Once a Pi is registered in the admin, clicking Update on its device card pulls the latest code and restarts the service — no SSH needed. The same flow runs from a systemd ExecStartPre hook, so every reboot also auto-pulls the latest main.",
  },
];

function InstallGuide() {
  return (
    <div className="rounded-2xl border border-white/10 bg-gradient-to-br from-sky-500/[0.04] to-transparent overflow-hidden">
      <div className="px-6 py-4 border-b border-white/10 bg-white/[0.02] flex items-start gap-3">
        <svg className="w-5 h-5 text-sky-300 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17v-2a4 4 0 014-4h3m0 0l-3-3m3 3l-3 3M5 19.5v-15A1.5 1.5 0 016.5 3h11A1.5 1.5 0 0119 4.5v15a1.5 1.5 0 01-1.5 1.5h-11A1.5 1.5 0 015 19.5z" />
        </svg>
        <div>
          <h2 className="text-xl font-medium text-white">Install on a Raspberry Pi</h2>
          <p className="text-sm text-zinc-400 mt-1">
            Start-to-finish steps for turning a fresh Pi into a vents or trolley device. Assumes the
            Pi already has Raspberry Pi OS installed and is reachable over SSH.
          </p>
        </div>
      </div>

      <ol className="p-6 space-y-5">
        {INSTALL_STEPS.map((step, i) => (
          <li key={step.title} className="flex gap-4">
            <span className="w-7 h-7 rounded-full bg-sky-500/20 border border-sky-400/40 text-sky-300 text-xs font-semibold flex items-center justify-center shrink-0">
              {i + 1}
            </span>
            <div className="flex-1 min-w-0 space-y-2">
              <h3 className="text-sm font-semibold text-white">{step.title}</h3>
              <p className="text-sm text-zinc-400 leading-relaxed">{step.body}</p>
              {Array.isArray(step.code)
                ? step.code.map((c, j) => <CodeBlock key={j} code={c} />)
                : step.code && <CodeBlock code={step.code} />}
            </div>
          </li>
        ))}
      </ol>

      <div className="px-6 pb-6 pt-2 border-t border-white/5 bg-white/[0.01]">
        <p className="text-[11px] text-zinc-500">
          Troubleshooting:{" "}
          <span className="text-zinc-400">
            on Pi 5, the installer installs <code className="font-mono text-zinc-300">rpi-lgpio</code> because the default{" "}
            <code className="font-mono text-zinc-300">RPi.GPIO</code> doesn't work on the Pi 5's GPIO chip.
          </span>{" "}
          If the service fails to start, check{" "}
          <code className="font-mono text-zinc-300">journalctl -u gpio-osc-&lt;type&gt; -n 50</code>.
        </p>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────────

type DocsTab = "install" | "protocol";

const TABS: { id: DocsTab; label: string }[] = [
  { id: "install", label: "Install on a Pi" },
  { id: "protocol", label: "Protocol reference" },
];

export default function DocsPage() {
  const [tab, setTab] = useState<DocsTab>("install");
  const [openIds, setOpenIds] = useState<Record<string, boolean>>({
    vents: true,
    trolley: true,
    system: false,
  });
  const [docDevices, setDocDevices] = useState<Device[]>([]);
  const [docSettings, setDocSettings] = useState<Settings | null>(null);

  useEffect(() => {
    if (tab !== "protocol") return;
    listDevices()
      .then(setDocDevices)
      .catch(() => setDocDevices([]));
    getSettings()
      .then(setDocSettings)
      .catch(() => setDocSettings(null));
  }, [tab]);

  function toggle(id: string) {
    setOpenIds((s) => ({ ...s, [id]: !s[id] }));
  }

  const bridgeEnabled = docSettings?.bridge_enabled ?? false;

  return (
    <div className="p-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="mb-6 pb-4 border-b border-white/10">
        <h1 className="text-3xl font-light tracking-tight text-white mb-1">Docs</h1>
        <p className="text-zinc-400 text-sm">
          Setup walkthrough for new hardware, and a reference for every OSC address and HTTP
          endpoint the system speaks.
        </p>
      </div>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between border-b border-white/10 mb-6 pb-4">
        <div role="tablist" className="flex gap-1">
          {TABS.map((t) => {
            const isActive = t.id === tab;
            return (
              <button
                key={t.id}
                role="tab"
                aria-selected={isActive}
                onClick={() => setTab(t.id)}
                className={`px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${
                  isActive
                    ? "text-white border-sky-400"
                    : "text-zinc-400 border-transparent hover:text-zinc-200"
                }`}
              >
                {t.label}
              </button>
            );
          })}
        </div>
        {tab === "protocol" && (
          <button
            type="button"
            onClick={downloadOscTechnicalSheet}
            className="shrink-0 inline-flex items-center gap-2 self-start sm:self-auto rounded-lg border border-white/15 bg-white/[0.03] px-3 py-2 text-sm font-medium text-zinc-200 hover:bg-white/[0.06] hover:border-white/25 transition-colors"
          >
            <svg className="w-4 h-4 text-zinc-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 10v11m0-11l3 3m-3-3l-3 3M4 5h16" />
            </svg>
            Download OSC technical sheet (.md)
          </button>
        )}
      </div>

      {tab === "install" && <InstallGuide />}

      {tab === "protocol" && (
        <div className="space-y-3">
          {SECTIONS.map((s) => (
            <SectionBlock
              key={s.id}
              section={s}
              open={!!openIds[s.id]}
              onToggle={() => toggle(s.id)}
              devices={docDevices}
              bridgeEnabled={bridgeEnabled}
            />
          ))}
          <p className="mt-8 text-[11px] text-zinc-600 font-mono">
            Source of truth: <code>rpi-controller/controllers/*.py</code>,{" "}
            <code>rpi-controller/gpio_osc.py</code>, <code>admin/backend/api/*.py</code>,{" "}
            <code>admin/backend/engine/osc_receiver.py</code>.
          </p>
        </div>
      )}
    </div>
  );
}
