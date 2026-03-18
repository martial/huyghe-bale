import { Outlet } from "react-router";
import NavLink from "./NavLink";
import DeviceHeartbeat from "./DeviceHeartbeat";
import PlaybackControls from "../playback/PlaybackControls";
import ToastContainer from "./ToastContainer";
import SystemWarnings from "./SystemWarnings";

export default function AppLayout() {
  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-200 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-zinc-900 via-zinc-950 to-zinc-950">
      {/* Sidebar */}
      <nav className="w-64 glass-panel flex flex-col z-10 shadow-2xl shadow-black/50">
        <div className="p-6 border-b border-white/5 bg-gradient-to-b from-white/5 to-transparent">
          <h1 className="text-sm font-bold tracking-widest uppercase text-white drop-shadow-md">
            Pierre Huyghe
          </h1>
          <p className="text-[11px] text-orange-400/80 mt-1 tracking-[0.2em] font-medium">BALE</p>
        </div>

        <div className="flex-1 p-3 space-y-1">
          <NavLink
            to="/timelines"
            icon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            }
          >
            Timelines
          </NavLink>

          <NavLink
            to="/devices"
            icon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            }
          >
            Devices
          </NavLink>

          <NavLink
            to="/orchestrations"
            icon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 6h16M4 12h16M4 18h7" />
              </svg>
            }
          >
            Orchestrations
          </NavLink>
        </div>

        {/* Settings link */}
        <div className="p-4 pt-0">
          <NavLink
            to="/settings"
            icon={
              <svg className="w-4 h-4 transition-transform group-hover:rotate-90 duration-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
            }
          >
            Settings
          </NavLink>
        </div>

        {/* Device heartbeat */}
        <div className="px-3 pb-2">
          <DeviceHeartbeat />
        </div>

        {/* Playback controls at bottom */}
        <div className="border-t border-white/5 bg-black/20 backdrop-blur-md">
          <PlaybackControls />
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-auto relative z-0 flex flex-col">
        <SystemWarnings />
        <div className="flex-1 relative">
          <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20 mix-blend-overlay pointer-events-none"></div>
          <div className="relative z-10 h-full">
            <Outlet />
          </div>
        </div>
      </main>
      
      <ToastContainer />
    </div>
  );
}
