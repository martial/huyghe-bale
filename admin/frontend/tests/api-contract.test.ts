/**
 * Frontend → backend contract tests.
 *
 * The backend matrix (admin/backend/tests/test_osc_surfaces.py) proves
 * "given a request body, the right OSC leaves the process". These
 * tests close the other gap: that every UI-facing API helper builds
 * exactly the request body that the backend route expects. A divergence
 * between the two is what produced the recent "No valid devices" /
 * silent-fail bugs — those didn't show up in either suite.
 *
 * Strategy: mock global `fetch`, call each public api helper, assert
 * the captured (path, method, body) match the documented contract.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as ventsApi from "../src/api/vents";
import * as trolleyApi from "../src/api/trolley";
import * as devicesApi from "../src/api/devices";
import * as protocolTestApi from "../src/api/protocol-test";
import * as playbackApi from "../src/api/playback";
import * as bridgeApi from "../src/api/bridge";

type FetchCall = { url: string; method: string; body: unknown };
let calls: FetchCall[];

beforeEach(() => {
  calls = [];
  globalThis.fetch = vi.fn(async (url: any, init?: any) => {
    const body = init?.body ? JSON.parse(init.body) : undefined;
    calls.push({
      url: String(url),
      method: (init?.method ?? "GET").toUpperCase(),
      body,
    });
    return new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as any;
});

afterEach(() => {
  vi.restoreAllMocks();
});

const DEV_VENTS = "dev_vents_1";
const DEV_TROLLEY = "dev_trolley_1";

// ── Vents test panel ─────────────────────────────────────────────────────

describe("vents api helpers", () => {
  it("setVentsPeltier(1, true) → POST /vents-control/:id/command {peltier 1 1}", async () => {
    await ventsApi.setVentsPeltier(DEV_VENTS, 1, true);
    expect(calls).toEqual([{
      url: `/api/v1/vents-control/${DEV_VENTS}/command`,
      method: "POST",
      body: { command: "peltier", index: 1, value: 1 },
    }]);
  });

  it("setVentsPeltier(2, false) → value 0", async () => {
    await ventsApi.setVentsPeltier(DEV_VENTS, 2, false);
    expect(calls[0].body).toEqual({ command: "peltier", index: 2, value: 0 });
  });

  it("setVentsPeltier(3, true)", async () => {
    await ventsApi.setVentsPeltier(DEV_VENTS, 3, true);
    expect(calls[0].body).toEqual({ command: "peltier", index: 3, value: 1 });
  });

  it("setVentsFan(1, 0.5) → POST {fan 1 0.5}", async () => {
    await ventsApi.setVentsFan(DEV_VENTS, 1, 0.5);
    expect(calls[0].body).toEqual({ command: "fan", index: 1, value: 0.5 });
  });

  it("setVentsFan(2, 0.8)", async () => {
    await ventsApi.setVentsFan(DEV_VENTS, 2, 0.8);
    expect(calls[0].body).toEqual({ command: "fan", index: 2, value: 0.8 });
  });

  it("setVentsMode(raw)", async () => {
    await ventsApi.setVentsMode(DEV_VENTS, "raw");
    expect(calls[0].body).toEqual({ command: "mode", value: "raw" });
  });

  it("setVentsMode(auto)", async () => {
    await ventsApi.setVentsMode(DEV_VENTS, "auto");
    expect(calls[0].body).toEqual({ command: "mode", value: "auto" });
  });

  it("setVentsTarget(22.5)", async () => {
    await ventsApi.setVentsTarget(DEV_VENTS, 22.5);
    expect(calls[0].body).toEqual({ command: "target", value: 22.5 });
  });

  it("sendVentsCommand peltier_mask 7", async () => {
    await ventsApi.sendVentsCommand(DEV_VENTS, { command: "peltier_mask", value: 7 });
    expect(calls[0].body).toEqual({ command: "peltier_mask", value: 7 });
  });

  it("sendVentsCommand max_temp 80", async () => {
    await ventsApi.sendVentsCommand(DEV_VENTS, { command: "max_temp", value: 80 });
    expect(calls[0].body).toEqual({ command: "max_temp", value: 80 });
  });

  it("fetchVentsStatus → GET /vents-control/:id/status", async () => {
    await ventsApi.fetchVentsStatus(DEV_VENTS);
    expect(calls[0]).toEqual({
      url: `/api/v1/vents-control/${DEV_VENTS}/status`,
      method: "GET",
      body: undefined,
    });
  });
});

// ── Trolley test panel ────────────────────────────────────────────────────

describe("trolley api helpers", () => {
  it("sendTrolleyCommand enable 1", async () => {
    await trolleyApi.sendTrolleyCommand(DEV_TROLLEY, "enable", 1);
    expect(calls[0]).toEqual({
      url: `/api/v1/trolley-control/${DEV_TROLLEY}/command`,
      method: "POST",
      body: { command: "enable", value: 1 },
    });
  });

  it("sendTrolleyCommand enable 0", async () => {
    await trolleyApi.sendTrolleyCommand(DEV_TROLLEY, "enable", 0);
    expect(calls[0].body).toEqual({ command: "enable", value: 0 });
  });

  it("sendTrolleyCommand dir 1", async () => {
    await trolleyApi.sendTrolleyCommand(DEV_TROLLEY, "dir", 1);
    expect(calls[0].body).toEqual({ command: "dir", value: 1 });
  });

  it("sendTrolleyCommand speed 0.5", async () => {
    await trolleyApi.sendTrolleyCommand(DEV_TROLLEY, "speed", 0.5);
    expect(calls[0].body).toEqual({ command: "speed", value: 0.5 });
  });

  it("sendTrolleyCommand step 1000", async () => {
    await trolleyApi.sendTrolleyCommand(DEV_TROLLEY, "step", 1000);
    expect(calls[0].body).toEqual({ command: "step", value: 1000 });
  });

  it("sendTrolleyCommand stop (no value) → defaults to 0", async () => {
    await trolleyApi.sendTrolleyCommand(DEV_TROLLEY, "stop");
    expect(calls[0].body).toEqual({ command: "stop", value: 0 });
  });

  it("sendTrolleyCommand home (no value) → defaults to 0", async () => {
    await trolleyApi.sendTrolleyCommand(DEV_TROLLEY, "home");
    expect(calls[0].body).toEqual({ command: "home", value: 0 });
  });

  it("sendTrolleyCommand position 0.25", async () => {
    await trolleyApi.sendTrolleyCommand(DEV_TROLLEY, "position", 0.25);
    expect(calls[0].body).toEqual({ command: "position", value: 0.25 });
  });

  it("fetchTrolleyStatus → GET /trolley-control/:id/status", async () => {
    await trolleyApi.fetchTrolleyStatus(DEV_TROLLEY);
    expect(calls[0]).toEqual({
      url: `/api/v1/trolley-control/${DEV_TROLLEY}/status`,
      method: "GET",
      body: undefined,
    });
  });
});

// ── Playback start / stop / seek ─────────────────────────────────────────

describe("playback api helpers", () => {
  it("startPlayback timeline → POST /playback/start", async () => {
    await playbackApi.startPlayback({
      type: "timeline",
      id: "tl_x",
      device_ids: [DEV_VENTS],
    });
    expect(calls[0]).toEqual({
      url: "/api/v1/playback/start",
      method: "POST",
      body: { type: "timeline", id: "tl_x", device_ids: [DEV_VENTS] },
    });
  });

  it("startPlayback trolley-timeline routes the right type", async () => {
    await playbackApi.startPlayback({
      type: "trolley-timeline",
      id: "trtl_x",
      device_ids: [DEV_TROLLEY],
    });
    expect(calls[0].body).toEqual({
      type: "trolley-timeline",
      id: "trtl_x",
      device_ids: [DEV_TROLLEY],
    });
  });

  it("stopPlayback → POST /playback/stop", async () => {
    await playbackApi.stopPlayback();
    expect(calls[0]).toMatchObject({
      url: "/api/v1/playback/stop",
      method: "POST",
    });
  });

  it("pausePlayback / resumePlayback / seekPlayback hit the right paths", async () => {
    await playbackApi.pausePlayback();
    await playbackApi.resumePlayback();
    await playbackApi.seekPlayback(12.5);
    expect(calls.map((c) => [c.method, c.url])).toEqual([
      ["POST", "/api/v1/playback/pause"],
      ["POST", "/api/v1/playback/resume"],
      ["POST", "/api/v1/playback/seek"],
    ]);
    expect(calls[2].body).toEqual({ elapsed: 12.5 });
  });

  it("getPlaybackStatus → GET /playback/status", async () => {
    await playbackApi.getPlaybackStatus();
    expect(calls[0]).toEqual({
      url: "/api/v1/playback/status",
      method: "GET",
      body: undefined,
    });
  });
});

// ── Devices list / create / update / delete ──────────────────────────────

describe("devices api helpers", () => {
  it("listDevices → GET /devices", async () => {
    await devicesApi.listDevices();
    expect(calls[0]).toEqual({
      url: "/api/v1/devices",
      method: "GET",
      body: undefined,
    });
  });

  it("createDevice → POST /devices with payload", async () => {
    await devicesApi.createDevice({
      name: "v1", ip_address: "10.0.0.1", osc_port: 9000, type: "vents",
    });
    expect(calls[0]).toEqual({
      url: "/api/v1/devices",
      method: "POST",
      body: { name: "v1", ip_address: "10.0.0.1", osc_port: 9000, type: "vents" },
    });
  });

  it("updateDevice → PUT /devices/:id", async () => {
    await devicesApi.updateDevice(DEV_VENTS, {
      id: DEV_VENTS, name: "v1-renamed", ip_address: "10.0.0.1",
      osc_port: 9000, type: "vents",
    });
    expect(calls[0].url).toBe(`/api/v1/devices/${DEV_VENTS}`);
    expect(calls[0].method).toBe("PUT");
    expect(calls[0].body).toMatchObject({ name: "v1-renamed" });
  });

  it("deleteDevice → DELETE /devices/:id", async () => {
    await devicesApi.deleteDevice(DEV_VENTS);
    expect(calls[0]).toEqual({
      url: `/api/v1/devices/${DEV_VENTS}`,
      method: "DELETE",
      body: undefined,
    });
  });

  it("sendTestValue → POST /devices/test-send", async () => {
    await devicesApi.sendTestValue([DEV_VENTS], 0.7, 0.3, "osc");
    expect(calls[0]).toEqual({
      url: "/api/v1/devices/test-send",
      method: "POST",
      body: { device_ids: [DEV_VENTS], value_a: 0.7, value_b: 0.3, method: "osc" },
    });
  });
});

// ── Docs Quick Test ──────────────────────────────────────────────────────

describe("protocol-test api helpers", () => {
  it("protocolTestOsc body shape", async () => {
    await protocolTestApi.protocolTestOsc({
      device_id: DEV_VENTS,
      address: "/vents/fan/1",
      values: [0.5],
    });
    expect(calls[0]).toEqual({
      url: "/api/v1/protocol-test/osc",
      method: "POST",
      body: { device_id: DEV_VENTS, address: "/vents/fan/1", values: [0.5] },
    });
  });

  it("protocolTestHttp body shape", async () => {
    await protocolTestApi.protocolTestHttp({
      device_id: DEV_VENTS, method: "GET", path: "/status",
    });
    expect(calls[0].body).toEqual({
      device_id: DEV_VENTS, method: "GET", path: "/status",
    });
  });

  it("protocolTestBridge body shape", async () => {
    await protocolTestApi.protocolTestBridge({
      address: "/vents/fan/1", values: [0.5],
    });
    expect(calls[0].body).toEqual({
      address: "/vents/fan/1", values: [0.5],
    });
  });
});

// ── OSC Bridge state / clear ─────────────────────────────────────────────

describe("bridge api helpers", () => {
  it("getBridgeState → GET /bridge/state", async () => {
    await bridgeApi.getBridgeState();
    expect(calls[0]).toEqual({
      url: "/api/v1/bridge/state",
      method: "GET",
      body: undefined,
    });
  });

  it("clearBridgeEvents → POST /bridge/clear", async () => {
    await bridgeApi.clearBridgeEvents();
    expect(calls[0]).toEqual({
      url: "/api/v1/bridge/clear",
      method: "POST",
      body: undefined,
    });
  });
});
