import { NavLink as RouterNavLink } from "react-router";

interface Props {
  to: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}

export default function NavLink({ to, icon, children }: Props) {
  return (
    <RouterNavLink
      to={to}
      className={({ isActive }) =>
        `group flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-300 relative overflow-hidden ${
          isActive
            ? "text-orange-400 bg-orange-500/10 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05),0_0_15px_rgba(249,115,22,0.1)] border border-orange-500/20"
            : "text-zinc-400 border border-transparent hover:bg-white/5 hover:text-zinc-200"
        }`
      }
    >
      {({ isActive }) => (
        <>
          <span className="relative z-10 flex items-center gap-3 w-full group-hover:translate-x-1 transition-transform duration-300">
            <span className="opacity-80 group-hover:opacity-100 transition-opacity duration-300">
              {icon}
            </span>
            <span>{children}</span>
          </span>
          {isActive && (
            <span className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-3/5 bg-orange-500 rounded-r-full shadow-[0_0_12px_rgba(249,115,22,0.8)]" />
          )}
        </>
      )}
    </RouterNavLink>
  );
}
