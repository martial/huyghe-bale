import { useState } from "react";

interface FAQItem {
  category: string;
  question: string;
  answer: string;
}

const faqItems: FAQItem[] = [
  // General
  {
    category: "General",
    question: 'A device shows "offline" in the panel',
    answer:
      "Make sure the Raspberry Pi is powered on and connected to the same network. Check that the IP address configured for the device matches the Pi's actual address. On the Devices page, try Scan to rediscover Pis on your subnet — each Pi replies with its type and hardware id. If the Pi was recently restarted, it may take a moment to reconnect.",
  },
  {
    category: "General",
    question: "How do I update the Pi software?",
    answer:
      "Once a Pi is registered in the admin, click Update on its device card — it pulls the latest code and restarts the service over the network (no SSH needed). The same update flow also runs automatically on every reboot via the systemd unit, so the Pi stays aligned with main after power cycles.",
  },
  {
    category: "General",
    question: "Device CPU temperature is showing high",
    answer:
      "The device card shows the Pi's CPU temperature. If it stays above 80\u00b0C, check that the Pi has adequate ventilation. Running fans at high PWM for extended periods is normal and should not overheat the Pi itself — high temperatures usually indicate an enclosure issue.",
  },
  // Devices & network
  {
    category: "Devices & network",
    question: "How does the admin find Pis on the network?",
    answer:
      "Use Scan on the Devices page: it probes the subnet and discovers Pis that respond. The admin sends /sys/ping; each Pi replies with /sys/pong carrying its IP, device type, and hardware id so the admin knows whether it is a vents or trolley controller before you add it.",
  },
  {
    category: "Devices & network",
    question: "What's a hardware id?",
    answer:
      "A stable identifier in the form {type}_{8 hex chars}, persisted on the Pi at ~/.config/gpio-osc/device.json. It stays the same when the LAN IP changes, so you can rely on it for routing and recognition across reboots.",
  },
  {
    category: "Devices & network",
    question: "Can two devices share the same name?",
    answer:
      "Yes — names are not enforced unique. If two devices share a name, OSC Bridge targeting via /to/<name>/… resolves to the first match in store order. Use an IP address or hardware id in the path when you need an unambiguous target.",
  },
  // Vents devices
  {
    category: "Vents devices",
    question: "What does a vents timeline actually control?",
    answer:
      "Lanes A and B drive the two PWM fans only: lane A maps to /vents/fan/1 and lane B to /vents/fan/2 (duty cycle 0–1). Auto temperature regulation uses Peltiers only toward /vents/target; timelines never drive Peltiers or target/max — set those on the vents device panel.",
  },
  {
    category: "Vents devices",
    question: "What's the difference between raw and auto mode?",
    answer:
      "Peltier modules always have a cold side and a hot side when powered; the cold-side fan and hot-side fan vent those paths (see Docs). In raw mode you control cells and fans manually (including timeline fan lanes). In auto, the Pi compares the average of the two temperature probes to /vents/target (±0.5°C): too cold → all cells on (thermoelectric pumping on), too warm but under max → all off, in between → hold. Auto does not PWM fans for that loop — switching to auto zeros fans once. Max (Settings or /vents/max_temp) is a separate safety ceiling. Sending /vents/fan/* or other raw overrides switches back to raw mode.",
  },
  {
    category: "Vents devices",
    question: "Can the fans reverse direction?",
    answer:
      "No — each fan is a single PWM output. Timelines control duty cycle from 0 to 1, not spin direction.",
  },
  // Trolley devices
  {
    category: "Trolley devices",
    question: "What does a trolley timeline control?",
    answer:
      "A single position lane from 0 (home / limit switch end) to 1 (far end). Points are sent as discrete /trolley/position commands; the Pi runs a smooth follow loop toward each target, so playback does not spam OSC every tick.",
  },
  {
    category: "Trolley devices",
    question: "What does \"not homed\" mean and how do I fix it?",
    answer:
      "After boot the controller does not know the carriage position until it hits the home limit switch. Use Home from the trolley panel (or send /trolley/home) — it drives toward home until the limit trips, then position is 0 and homed becomes true.",
  },
  {
    category: "Trolley devices",
    question: "The trolley stopped mid-move",
    answer:
      "Any new /trolley/* command cancels an in-progress burst or position follow. Hitting the limit switch during motion also stops the move. This is intentional so you can always preempt or recover from an unexpected stop.",
  },
  // Timelines & orchestrations
  {
    category: "Timelines & orchestrations",
    question: "Playback is running but nothing happens on the device",
    answer:
      "Check that the orchestration has at least one device assigned. Each device must be linked for it to receive OSC during playback. For a vents timeline, put points on lanes A and B as needed. For a trolley timeline, ensure position points exist on the lane. Wrong device type (e.g. vents timeline to trolley-only step) will not do what you expect — match timeline flavour to device type.",
  },
  {
    category: "Timelines & orchestrations",
    question: "How do curve types work?",
    answer:
      'The curve type on a point defines the interpolation arriving at that point from the previous one. For example, setting "ease-in" on a point means the transition from the previous point will start slow and accelerate. Available types: linear, step, ease-in, ease-out, ease-in-out, sine, exponential, and bezier.',
  },
  {
    category: "Timelines & orchestrations",
    question: "Can I assign the same timeline to multiple devices?",
    answer:
      "Yes. In an orchestration you can assign one timeline to several devices; they all receive the same OSC during that step. Use it only for devices that understand that timeline: vents timelines for vents units, trolley timelines for trolley units.",
  },
  {
    category: "Timelines & orchestrations",
    question: "How fast does the playback engine update?",
    answer:
      "The playback engine runs at about 30 updates per second. Each tick interpolates the current value from the timeline and sends OSC to all targeted devices (vents fan lanes; trolley position events are fired on their own schedule).",
  },
  {
    category: "Timelines & orchestrations",
    question: "What happens if I edit a timeline during playback?",
    answer:
      "Changes to a timeline take effect on the next playback cycle. You can safely edit points while an orchestration is playing — the engine will pick up the new curve shape.",
  },
  {
    category: "Timelines & orchestrations",
    question: "What is delay_before in an orchestration step?",
    answer:
      "Each step can include a delay_before in seconds before that step's timeline runs. During that wait, lane values hold at the last value emitted from the previous step — they do not reset to zero.",
  },
  // External control (OSC Bridge)
  {
    category: "External control (OSC Bridge)",
    question: "What is the Bridge for?",
    answer:
      "The Bridge listens on the admin host for OSC from an external source (e.g. Max, TouchDesigner, or a show controller). Messages can be forwarded to connected devices according to Settings \u2192 OSC Bridge routing: type-match (default, by address prefix), passthrough (every message to every device), or none (log only). Open the Bridge page for a live feed of recent messages.",
  },
  {
    category: "External control (OSC Bridge)",
    question: "How do I target a specific device from the Bridge?",
    answer:
      "Prefix the real OSC address with /to/<identifier>/ where identifier is the device's id, name, IP address, or hardware id (exact match, case-sensitive). The admin unwraps that prefix and forwards only to that device. If the name is ambiguous, use IP or hardware id.",
  },
];

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      className={`w-4 h-4 text-zinc-500 transition-transform duration-200 ${open ? "rotate-90" : ""}`}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={1.5}
        d="M8.25 4.5l7.5 7.5-7.5 7.5"
      />
    </svg>
  );
}

export default function FAQPage() {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  const sections: { title: string; items: FAQItem[]; startIndex: number }[] = [];
  let idx = 0;
  for (const item of faqItems) {
    const last = sections[sections.length - 1];
    if (!last || last.title !== item.category) {
      sections.push({ title: item.category, items: [item], startIndex: idx });
    } else {
      last.items.push(item);
    }
    idx += 1;
  }

  return (
    <div className="p-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="mb-10 pb-4 border-b border-white/10">
        <h1 className="text-3xl font-light tracking-tight text-white mb-1">FAQ</h1>
        <p className="text-zinc-400 text-sm">
          Common issues and troubleshooting
        </p>
      </div>

      <div className="space-y-8">
        {sections.map((section, sectionIdx) => (
          <div key={`${section.title}-${sectionIdx}`}>
            <h2 className="text-[11px] uppercase tracking-wider font-semibold text-zinc-500 mb-3">
              {section.title}
            </h2>
            <div className="space-y-2">
              {section.items.map((item, innerIdx) => {
                const i = section.startIndex + innerIdx;
                const isOpen = openIndex === i;
                return (
                  <div
                    key={`${section.title}-${innerIdx}-${item.question}`}
                    className="rounded-2xl border border-white/5 bg-zinc-900/40 backdrop-blur-sm overflow-hidden animate-in fade-in slide-in-from-bottom-4 fill-mode-both"
                    style={{ animationDelay: `${i * 50}ms` }}
                  >
                    <button
                      type="button"
                      onClick={() => setOpenIndex(isOpen ? null : i)}
                      className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-white/5 transition-all duration-300 rounded-2xl"
                    >
                      <ChevronIcon open={isOpen} />
                      <span className="text-sm font-medium text-zinc-200">
                        {item.question}
                      </span>
                    </button>
                    {isOpen && (
                      <div className="px-4 pb-4 pl-11">
                        <p className="text-sm text-zinc-400 leading-relaxed whitespace-pre-line">
                          {item.answer}
                        </p>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

