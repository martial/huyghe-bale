<script setup lang="ts">
import { useTimelineStore } from "../../stores/timelineStore";
import { useRouter } from "vue-router";
import TimelinePreview from "./TimelinePreview.vue";

const store = useTimelineStore();
const router = useRouter();

async function handleDuplicate(id: string) {
  const tl = await store.duplicate(id);
  router.push(`/timelines/${tl.id}`);
}
</script>

<template>
  <div class="space-y-2">
    <div
      v-for="tl in store.list"
      :key="tl.id"
      class="flex items-center gap-4 p-3 rounded-lg border border-zinc-800 hover:border-zinc-600 transition-colors cursor-pointer"
      @click="router.push(`/timelines/${tl.id}`)"
    >
      <TimelinePreview :timeline-id="tl.id" class="w-32 h-16 rounded overflow-hidden flex-shrink-0" />
      <div class="flex-1 min-w-0">
        <p class="font-medium truncate">{{ tl.name }}</p>
        <p class="text-xs text-zinc-500 mt-0.5">
          {{ tl.duration }}s &middot; {{ tl.lane_a_points + tl.lane_b_points }} points
        </p>
      </div>
      <div class="flex gap-2">
        <button
          @click.stop="handleDuplicate(tl.id)"
          class="text-xs text-zinc-400 hover:text-white px-2 py-1 transition-colors"
        >
          Duplicate
        </button>
        <button
          @click.stop="store.remove(tl.id)"
          class="text-xs text-red-400/60 hover:text-red-400 px-2 py-1 transition-colors"
        >
          Delete
        </button>
      </div>
    </div>

    <p v-if="!store.list.length" class="text-zinc-500 text-sm mt-8 text-center">
      No timelines yet. Create one to get started.
    </p>
  </div>
</template>
