export default function AboutPage() {
  return (
    <div className="h-full flex items-center justify-center p-8">
      <div className="max-w-lg w-full text-center space-y-12">
        {/* Title */}
        <div className="space-y-3">
          <h1 className="text-4xl font-bold tracking-wider uppercase text-white font-[var(--font-display)]">
            Pierre Huyghe
          </h1>
          <p className="text-2xl tracking-[0.35em] font-semibold text-orange-400/90 font-[var(--font-display)]">
            BALE
          </p>
        </div>

        {/* Divider */}
        <div className="flex items-center justify-center gap-4">
          <div className="h-px w-16 bg-gradient-to-r from-transparent to-white/20" />
          <div className="w-1.5 h-1.5 rounded-full bg-orange-500/60" />
          <div className="h-px w-16 bg-gradient-to-l from-transparent to-white/20" />
        </div>

        {/* Credits */}
        <div className="space-y-6">
          <p className="text-xs tracking-[0.25em] uppercase text-zinc-600">
            Designed &amp; built by
          </p>
          <div className="flex items-center justify-center gap-8">
            <span className="text-lg font-medium text-zinc-300 font-[var(--font-display)]">
              Martial
            </span>
            <span className="text-zinc-700">&amp;</span>
            <span className="text-lg font-medium text-zinc-300 font-[var(--font-display)]">
              Michel
            </span>
          </div>

          {/* screen-club link */}
          <a
            href="https://screen-club.com"
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 group"
          >
            <span className="text-sm font-medium tracking-wider text-zinc-400 group-hover:text-orange-400 transition-colors duration-300">
              screen-club.com
            </span>
            <svg
              className="w-3.5 h-3.5 text-zinc-600 group-hover:text-orange-400 transition-all duration-300 group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25"
              />
            </svg>
          </a>
        </div>

        {/* GitHub */}
        <a
          href="https://github.com/martial/huyghe-bale"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-block text-zinc-600 hover:text-zinc-300 transition-colors duration-300"
          title="GitHub"
        >
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
          </svg>
        </a>

        {/* Version */}
        <p className="text-[10px] text-zinc-700 tracking-wider">
          2025
        </p>
      </div>
    </div>
  );
}
