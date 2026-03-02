import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      redirect: "/timelines",
    },
    {
      path: "/timelines",
      name: "timelines",
      component: () => import("../views/TimelinesView.vue"),
    },
    {
      path: "/timelines/:id",
      name: "timeline-edit",
      component: () => import("../views/TimelineEditView.vue"),
      props: true,
    },
    {
      path: "/devices",
      name: "devices",
      component: () => import("../views/DevicesView.vue"),
    },
    {
      path: "/orchestrations",
      name: "orchestrations",
      component: () => import("../views/OrchestrationsView.vue"),
    },
    {
      path: "/orchestrations/:id",
      name: "orchestration-edit",
      component: () => import("../views/OrchestrationEditView.vue"),
      props: true,
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import("../views/SettingsView.vue"),
    },
  ],
});

export default router;
