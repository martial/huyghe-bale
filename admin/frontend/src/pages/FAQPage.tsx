import { useState } from "react";

interface FAQItem {
  question: string;
  answer: string;
}

const faqItems: FAQItem[] = [
  {
    question: 'A device shows "offline" in the panel',
    answer:
      "Make sure the Raspberry Pi is powered on and connected to the same network. Check that the IP address configured for the device matches the Pi's actual address. If the Pi was recently restarted, it may take a moment to reconnect.",
  },
  {
    question: "Playback is running but nothing happens on the device",
    answer:
      "Check that the orchestration has at least one device assigned to it. Each device must be linked in the orchestration for it to receive OSC messages during playback. Also verify the timeline has points on the channels (A/B) you expect output on.",
  },
  {
    question: "What are channels A and B?",
    answer:
      "Each timeline has two channels: A and B. These correspond to two independent PWM outputs on the Raspberry Pi, each controlling a motor driver. You can draw different curves on each channel to control two motors independently.",
  },
  {
    question: "How do curve types work?",
    answer:
      "The curve type on a point defines the interpolation arriving at that point from the previous one. For example, setting \"ease-in\" on a point means the transition from the previous point will start slow and accelerate. Available types: linear, step, ease-in, ease-out, ease-in-out, sine, exponential, and bezier.",
  },
  {
    question: "Can I assign the same timeline to multiple devices?",
    answer:
      "Yes. In an orchestration, you can assign one timeline to multiple devices. All assigned devices will receive the same PWM values during playback.",
  },
  {
    question: "The motors only spin in one direction",
    answer:
      "The direction pins are fixed in the current configuration. The timeline controls the speed (PWM duty cycle) from 0% to 100%, not the direction. If you need reverse, the direction pins must be changed at the hardware/software level on the Pi.",
  },
  {
    question: "How fast does the playback engine update?",
    answer:
      "The playback engine runs at approximately 30 updates per second. This provides smooth transitions for most motor applications. Each update interpolates the current value from the timeline curve and sends it via OSC to all targeted devices.",
  },
  {
    question: "What happens if I edit a timeline during playback?",
    answer:
      "Changes to a timeline take effect on the next playback cycle. You can safely edit points while an orchestration is playing — the engine will pick up the new curve shape.",
  },
  {
    question: "Device CPU temperature is showing high",
    answer:
      "The device status page shows the Pi's CPU temperature. If it stays above 80\u00b0C, check that the Pi has adequate ventilation. Running motors at high PWM for extended periods is normal and should not overheat the Pi itself — high temperatures usually indicate an enclosure issue.",
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

  return (
    <div className="p-10 animate-in fade-in slide-in-from-bottom-4 duration-700">
      <div className="mb-10 pb-4 border-b border-white/10">
        <h1 className="text-3xl font-light tracking-tight text-white mb-1">FAQ</h1>
        <p className="text-zinc-400 text-sm">
          Common issues and troubleshooting
        </p>
      </div>

      <div className="space-y-2">
        {faqItems.map((item, i) => {
          const isOpen = openIndex === i;
          return (
            <div
              key={i}
              className="rounded-2xl border border-white/5 bg-zinc-900/40 backdrop-blur-sm overflow-hidden animate-in fade-in slide-in-from-bottom-4 fill-mode-both"
              style={{ animationDelay: `${i * 50}ms` }}
            >
              <button
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
  );
}
