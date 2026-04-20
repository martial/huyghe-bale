export default function DeviceCardSkeleton() {
  return (
    <div className="p-5 rounded-xl border border-zinc-800/50 bg-zinc-900/80 shadow-sm animate-pulse">
      <div className="flex items-start justify-between">
        <div className="flex-1 space-y-2">
          <div className="flex items-center gap-2">
            <div className="h-4 w-32 rounded bg-zinc-800/80" />
            <div className="h-4 w-10 rounded bg-zinc-800/60" />
          </div>
          <div className="h-3 w-40 rounded bg-zinc-800/60" />
          <div className="h-2 w-24 rounded bg-zinc-800/40" />
        </div>
        <div className="w-2 h-2 rounded-full bg-zinc-700" />
      </div>

      <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-2 rounded bg-zinc-800/40" style={{ width: `${50 + (i * 7) % 40}%` }} />
        ))}
      </div>

      <div className="flex gap-3 mt-4">
        <div className="h-3 w-8 rounded bg-zinc-800/60" />
        <div className="h-3 w-10 rounded bg-zinc-800/40" />
      </div>
    </div>
  );
}
