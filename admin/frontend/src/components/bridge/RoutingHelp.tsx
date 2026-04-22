/**
 * `?` icon next to the bridge Routing select that reveals a plain-language
 * tooltip on hover/focus. Shared between BridgePage and SettingsPage so the
 * copy stays consistent.
 */
export default function RoutingHelp() {
  return (
    <span className="relative group inline-flex items-center">
      <span
        tabIndex={0}
        role="button"
        aria-label="Routing modes"
        className="w-4 h-4 rounded-full bg-zinc-700 hover:bg-zinc-600 text-zinc-200 text-[10px] font-bold flex items-center justify-center transition-colors cursor-help select-none"
      >
        ?
      </span>
      <div className="pointer-events-none absolute top-full left-1/2 -translate-x-1/2 mt-2 w-80 p-3 rounded-lg bg-zinc-950 border border-white/10 text-[11px] text-zinc-300 shadow-xl opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity z-50 leading-relaxed">
        <p className="mb-2 text-zinc-400">Which devices receive each incoming message:</p>
        <div className="space-y-1.5">
          <div>
            <span className="font-mono text-sky-300">type-match</span>
            <span className="text-zinc-500"> — </span>
            <span>Smart: vents commands go to vents, trolley commands to trolley.</span>
          </div>
          <div>
            <span className="font-mono text-sky-300">passthrough</span>
            <span className="text-zinc-500"> — </span>
            <span>Send every message to every device.</span>
          </div>
          <div>
            <span className="font-mono text-sky-300">none</span>
            <span className="text-zinc-500"> — </span>
            <span>Just log, don't send anywhere. For debugging.</span>
          </div>
        </div>
        <p className="mt-3 pt-2 border-t border-white/10 text-zinc-400">
          <span className="text-zinc-500">Target one device:</span> prefix your address with{" "}
          <span className="font-mono text-sky-300">/to/&lt;name-or-ip&gt;/</span>. Works in any routing mode.
        </p>
      </div>
    </span>
  );
}
