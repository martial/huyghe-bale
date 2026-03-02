<script setup lang="ts">
import { onMounted } from "vue";
import { usePlaybackStore } from "../../stores/playbackStore";
import PlaybackMonitor from "./PlaybackMonitor.vue";

const playback = usePlaybackStore();

onMounted(() => playback.fetchStatus());
</script>

<template>
  <div class="p-3">
    <div v-if="playback.status.playing" class="space-y-2">
      <PlaybackMonitor :status="playback.status" />
      <button
        @click="playback.stop()"
        class="w-full px-3 py-1.5 bg-red-600/80 hover:bg-red-500 rounded text-xs font-medium transition-colors"
      >
        Stop
      </button>
    </div>
    <div v-else class="text-xs text-zinc-600 text-center py-2">
      Not playing
    </div>
  </div>
</template>
