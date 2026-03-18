<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";
import { RouterLink, RouterView } from "vue-router";
import PlaybackControls from "../playback/PlaybackControls.vue";
import DeviceHeartbeat from "./DeviceHeartbeat.vue";
</script>

<template>
  <div class="flex h-screen bg-zinc-950 text-zinc-100">
    <!-- Sidebar -->
    <nav class="w-56 border-r border-zinc-800 flex flex-col">
      <div class="p-4 border-b border-zinc-800">
        <h1 class="text-sm font-semibold tracking-wide uppercase text-zinc-400">
          Pierre Huyghe
        </h1>
        <p class="text-xs text-zinc-600 mt-0.5">BALE</p>
      </div>

      <div class="flex-1 p-3 space-y-1">
        <RouterLink
          to="/timelines"
          class="flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors hover:bg-zinc-800/60"
          active-class="bg-zinc-800 text-white"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
          Timelines
        </RouterLink>

        <RouterLink
          to="/devices"
          class="flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors hover:bg-zinc-800/60"
          active-class="bg-zinc-800 text-white"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
          Devices
        </RouterLink>

        <RouterLink
          to="/orchestrations"
          class="flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors hover:bg-zinc-800/60"
          active-class="bg-zinc-800 text-white"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 6h16M4 12h16M4 18h7" />
          </svg>
          Orchestrations
        </RouterLink>
      </div>

      <!-- Settings link -->
      <div class="p-3 pt-0">
        <DeviceHeartbeat />
      </div>

      <!-- Settings link -->
      <div class="p-3 pt-0">
        <RouterLink
          to="/settings"
          class="flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors hover:bg-zinc-800/60"
          active-class="bg-zinc-800 text-white"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          Settings
        </RouterLink>
      </div>

      <!-- Playback controls at bottom of sidebar -->
      <div class="border-t border-zinc-800">
        <PlaybackControls />
      </div>
    </nav>

    <!-- Main content -->
    <main class="flex-1 overflow-auto">
      <RouterView />
    </main>
  </div>
</template>
