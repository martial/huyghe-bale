import { useState } from "react";

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
    "3 Peltier cells (digital on/off) + 2 PWM fans + 4 tachos + 2 DS18B20 temperature probes. Auto-regulation is bang-bang with hysteresis around a target temperature.",
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
          description: "Cell 1 on/off (BCM GPIO 26, active HIGH). Sending any value forces mode=raw.",
        },
        {
          address: "/vents/peltier/2",
          direction: "admin-to-pi",
          args: "int 0|1",
          description: "Cell 2 on/off (BCM GPIO 25, active HIGH). Forces mode=raw.",
        },
        {
          address: "/vents/peltier/3",
          direction: "admin-to-pi",
          args: "int 0|1",
          description: "Cell 3 on/off (BCM GPIO 24, active HIGH). Forces mode=raw.",
        },
        {
          address: "/vents/peltier",
          direction: "admin-to-pi",
          args: "int mask 0..7",
          description:
            "Set all three cells at once as a bitmask (bit 0 = P1, bit 1 = P2, bit 2 = P3). Forces mode=raw.",
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
          address: "/vents/mode",
          direction: "admin-to-pi",
          args: "string raw|auto",
          description:
            "'raw' = manual control via the addresses above. 'auto' = bang-bang loop drives peltiers + fans toward /vents/target.",
        },
        {
          address: "/vents/target",
          direction: "admin-to-pi",
          args: "float °C",
          description:
            "Target temperature for auto mode. Hysteresis ±0.5°C: above → peltiers on + fans high, below → peltiers off + fans low, deadband → hold.",
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
            "float temp1_c, float temp2_c, float fan1, float fan2, int peltier_mask, int rpm1A, int rpm1B, int rpm2A, int rpm2B, float target_c, string mode, string state",
          description:
            "Broadcast at 5 Hz to the last admin that pinged. Missing DS18B20 sensors report -1.0. state ∈ {idle, cooling, holding, coasting, sensor_error}. Exposed via GET /api/v1/vents-control/<id>/status.",
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
            '{command: "peltier"|"peltier_mask"|"fan"|"mode"|"target", index?: 1..3, value: …}',
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

const SECTIONS: Section[] = [VENTS, TROLLEY, SYSTEM];

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

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard?.writeText(text).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1200);
        });
      }}
      className="opacity-0 group-hover:opacity-100 text-[10px] text-zinc-500 hover:text-zinc-200 transition-all"
      title="Copy address"
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}

function EndpointRow({ item }: { item: Endpoint }) {
  const isHttp = item.direction === "http";
  const addrCls = isHttp
    ? "text-emerald-200/90"
    : item.direction === "pi-to-admin"
    ? "text-sky-200/90"
    : "text-orange-200/90";
  return (
    <div className="group p-3 rounded-xl border border-white/5 bg-zinc-950/40 hover:bg-zinc-950/70 transition-colors">
      <div className="flex items-center gap-3 flex-wrap">
        <code className={`text-sm font-mono bg-black/40 border border-white/5 rounded px-2 py-0.5 ${addrCls}`}>
          {item.address}
        </code>
        {!isHttp && (
          <span
            className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium border ${DIR_BADGE[item.direction].cls}`}
          >
            {DIR_BADGE[item.direction].label}
          </span>
        )}
        {item.args && (
          <code className="text-[11px] font-mono text-zinc-400">{item.args}</code>
        )}
        <CopyButton text={item.address} />
      </div>
      <p className="mt-2 text-xs text-zinc-400 leading-relaxed">{item.description}</p>
      {item.example && (
        <pre className="mt-2 p-2 rounded bg-black/50 border border-white/5 text-[11px] text-zinc-400 font-mono overflow-x-auto">
          {item.example}
        </pre>
      )}
    </div>
  );
}

function SectionBlock({
  section,
  open,
  onToggle,
}: {
  section: Section;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="rounded-2xl border border-white/5 bg-zinc-900/40 backdrop-blur-sm overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-start gap-3 px-5 py-4 text-left hover:bg-white/5 transition-all"
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
                  <div className="rounded-xl border border-orange-500/20 bg-orange-500/[0.03] border-l-4 border-l-orange-400/60 overflow-hidden">
                    <div className="flex items-center gap-2 px-4 py-2 border-b border-orange-500/10 bg-orange-500/[0.04]">
                      <svg className="w-3.5 h-3.5 text-orange-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
                      </svg>
                      <span className="text-[11px] uppercase tracking-wider font-semibold text-orange-300">
                        OSC
                      </span>
                      {section.transport.osc && (
                        <span className="text-[10px] font-mono text-orange-300/60">· {section.transport.osc}</span>
                      )}
                    </div>
                    <div className="p-4 space-y-4">
                      {oscGroups.map((g) => (
                        <div key={g.label}>
                          <h4 className="text-[10px] uppercase tracking-wider font-medium text-zinc-500 mb-2">
                            {g.label}
                          </h4>
                          <div className="space-y-2">
                            {g.items.map((item) => (
                              <EndpointRow key={item.address} item={item} />
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {httpGroups.length > 0 && (
                  <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/[0.03] border-l-4 border-l-emerald-400/60 overflow-hidden">
                    <div className="flex items-center gap-2 px-4 py-2 border-b border-emerald-500/10 bg-emerald-500/[0.04]">
                      <svg className="w-3.5 h-3.5 text-emerald-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0zM3.6 9h16.8M3.6 15h16.8M11.5 3a17 17 0 000 18M12.5 3a17 17 0 010 18" />
                      </svg>
                      <span className="text-[11px] uppercase tracking-wider font-semibold text-emerald-300">
                        HTTP
                      </span>
                      {section.transport.http && (
                        <span className="text-[10px] font-mono text-emerald-300/60">· {section.transport.http}</span>
                      )}
                    </div>
                    <div className="p-4 space-y-4">
                      {httpGroups.map((g) => (
                        <div key={g.label}>
                          <h4 className="text-[10px] uppercase tracking-wider font-medium text-zinc-500 mb-2">
                            {g.label}
                          </h4>
                          <div className="space-y-2">
                            {g.items.map((item) => (
                              <EndpointRow key={item.address} item={item} />
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
  code?: string;
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
    code:
      "# vents device (L298N fan driver)\ncurl -sSL https://storage.googleapis.com/apps-screen-club/huyghe-bale/install.sh \\\n  | sudo bash -s -- --type=vents\n\n# trolley device (stepper + limit switch)\ncurl -sSL https://storage.googleapis.com/apps-screen-club/huyghe-bale/install.sh \\\n  | sudo bash -s -- --type=trolley",
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
      <div className="px-6 py-4 border-b border-white/10 bg-white/[0.02]">
        <div className="flex items-center gap-3">
          <svg className="w-5 h-5 text-sky-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17v-2a4 4 0 014-4h3m0 0l-3-3m3 3l-3 3M5 19.5v-15A1.5 1.5 0 016.5 3h11A1.5 1.5 0 0119 4.5v15a1.5 1.5 0 01-1.5 1.5h-11A1.5 1.5 0 015 19.5z" />
          </svg>
          <h2 className="text-xl font-medium text-white">Install on a Raspberry Pi</h2>
        </div>
        <p className="text-sm text-zinc-400 mt-2">
          Start-to-finish steps for turning a fresh Pi into a vents or trolley device. Assumes the
          Pi already has Raspberry Pi OS installed and is reachable over SSH.
        </p>
      </div>

      <ol className="p-6 space-y-4">
        {INSTALL_STEPS.map((step, i) => (
          <li key={step.title} className="flex gap-4">
            <div className="flex-shrink-0">
              <div className="w-7 h-7 rounded-full bg-sky-500/20 border border-sky-400/40 text-sky-300 text-xs font-semibold flex items-center justify-center">
                {i + 1}
              </div>
            </div>
            <div className="flex-1 min-w-0 pb-1">
              <h3 className="text-sm font-semibold text-white mb-1">{step.title}</h3>
              <p className="text-sm text-zinc-400 leading-relaxed">{step.body}</p>
              {step.code && (
                <div className="group relative mt-2">
                  <pre className="p-3 rounded-lg bg-black/60 border border-white/5 text-[12px] text-zinc-300 font-mono overflow-x-auto whitespace-pre pr-14">
                    {step.code}
                  </pre>
                  <div className="absolute top-2 right-2">
                    <CopyButton text={step.code} />
                  </div>
                </div>
              )}
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

export default function DocsPage() {
  const [openIds, setOpenIds] = useState<Record<string, boolean>>({
    vents: true,
    trolley: true,
    system: false,
  });

  function toggle(id: string) {
    setOpenIds((s) => ({ ...s, [id]: !s[id] }));
  }

  return (
    <div className="p-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="mb-8 pb-4 border-b border-white/10">
        <h1 className="text-3xl font-light tracking-tight text-white mb-1">Protocol docs</h1>
        <p className="text-zinc-400 text-sm">
          Every OSC address and HTTP endpoint the system speaks, grouped by device type. The admin
          sends OSC on port 9000; Pis reply on port 9001. Each Pi also exposes an HTTP status/test
          server on <span className="font-mono">:9001</span>.
        </p>
      </div>

      <div className="mb-6">
        <InstallGuide />
      </div>

      <h2 className="text-xs uppercase tracking-[0.2em] font-semibold text-zinc-500 mb-3 mt-10">
        Protocol reference
      </h2>
      <div className="space-y-3">
        {SECTIONS.map((s) => (
          <SectionBlock
            key={s.id}
            section={s}
            open={!!openIds[s.id]}
            onToggle={() => toggle(s.id)}
          />
        ))}
      </div>

      <p className="mt-8 text-[11px] text-zinc-600 font-mono">
        Source of truth: <code>rpi-controller/controllers/*.py</code>,{" "}
        <code>rpi-controller/gpio_osc.py</code>, <code>admin/backend/api/*.py</code>,{" "}
        <code>admin/backend/engine/osc_receiver.py</code>.
      </p>
    </div>
  );
}
