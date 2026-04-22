import { useState } from "react";
import { Outlet } from "react-router";
import NavLink from "./NavLink";
import DeviceHeartbeat from "./DeviceHeartbeat";
import PlaybackControls from "../playback/PlaybackControls";
import ToastContainer from "./ToastContainer";
import SystemWarnings from "./SystemWarnings";
import { usePlaybackStore } from "../../stores/playback-store";
import { useDeviceStore } from "../../stores/device-store";
import { sendTestValue } from "../../api/devices";

export default function AppLayout() {
  const stop = usePlaybackStore((s) => s.stop);
  const devices = useDeviceStore((s) => s.list);
  const fetchDevices = useDeviceStore((s) => s.fetchList);
  const [allOffBusy, setAllOffBusy] = useState(false);

  async function handleAllOff() {
    setAllOffBusy(true);
    try {
      await stop();
      let devs = devices;
      if (devs.length === 0) {
        await fetchDevices();
        devs = useDeviceStore.getState().list;
      }
      if (devs.length > 0) {
        const ids = devs.map((d) => d.id);
        await sendTestValue(ids, 0, 0, "osc");
      }
    } catch (e) {
      console.error("[ALL OFF] error:", e);
    } finally {
      setAllOffBusy(false);
    }
  }

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
            to="/trolleys"
            icon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 10h18M5 10v10h14V10M9 6h6a2 2 0 012 2v2H7V8a2 2 0 012-2z" />
                <circle cx="8" cy="19" r="1.5" strokeWidth={1.5} />
                <circle cx="16" cy="19" r="1.5" strokeWidth={1.5} />
              </svg>
            }
          >
            Trolleys
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

        {/* Settings & About links */}
        <div className="p-4 pt-0 space-y-1">
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
          <NavLink
            to="/faq"
            icon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.879 7.519c1.171-1.025 3.071-1.025 4.242 0 1.172 1.025 1.172 2.687 0 3.712-.203.179-.43.326-.67.442-.745.361-1.45.999-1.45 1.827v.75M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9 5.25h.008v.008H12v-.008z" />
              </svg>
            }
          >
            FAQ
          </NavLink>
          <NavLink
            to="/docs"
            icon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
            }
          >
            Docs
          </NavLink>
          <NavLink
            to="/about"
            icon={
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
              </svg>
            }
          >
            About
          </NavLink>
        </div>

        {/* Device heartbeat */}
        <div className="px-3 pb-2">
          <DeviceHeartbeat />
        </div>

        {/* ALL OFF */}
        <div className="px-3 pb-2">
          <button
            onClick={handleAllOff}
            disabled={allOffBusy}
            className="w-full px-3 py-2.5 bg-red-700/80 hover:bg-red-600 disabled:opacity-50 rounded-lg text-sm font-bold uppercase tracking-wider transition-all duration-200"
          >
            {allOffBusy ? "Stopping..." : "All Off"}
          </button>
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
          <div className="relative z-10 h-full">
            <Outlet />
          </div>
        </div>
      </main>
      
      <ToastContainer />
    </div>
  );
}
