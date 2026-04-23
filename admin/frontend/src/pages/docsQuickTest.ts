/** Resolved quick-test action for Docs protocol rows (null = no UI). */
export type QuickTestSpec =
  | {
      kind: "osc";
      values: (number | string | boolean)[];
    }
  | {
      kind: "http";
      method: "GET" | "POST";
      path: string;
      json?: Record<string, unknown>;
    }
  | {
      kind: "bridge";
      variant: "direct";
      address: string;
      values: (number | string | boolean)[];
    }
  | {
      kind: "bridge";
      variant: "to";
      innerAddress: string;
      values: (number | string | boolean)[];
    };

function oscDefaults(address: string): (number | string | boolean)[] | undefined {
  if (address === "/vents/peltier") return [5];
  if (address.startsWith("/vents/peltier/")) return [1];
  if (address.startsWith("/vents/fan/")) return [0.5];
  if (address === "/vents/mode") return ["raw"];
  if (address === "/vents/target") return [22.0];
  if (address === "/trolley/enable") return [1];
  if (address === "/trolley/dir") return [1];
  if (address === "/trolley/speed") return [0.3];
  if (address === "/trolley/step") return [100];
  if (address === "/trolley/stop" || address === "/trolley/home") return [];
  if (address === "/trolley/position") return [0.25];
  if (address === "/sys/ping") return [9001];
  return undefined;
}

function parseHttpAddress(raw: string): { method: "GET" | "POST"; path: string } | null {
  const m = raw.trim().match(/^(GET|POST)\s+(\/\S+)/i);
  if (!m) return null;
  return { method: m[1].toUpperCase() as "GET" | "POST", path: m[2] };
}

export function resolveQuickTest(
  sectionId: string,
  direction: "admin-to-pi" | "pi-to-admin" | "http",
  address: string,
): QuickTestSpec | null {
  if (direction === "pi-to-admin") return null;

  if (direction === "http") {
    const parsed = parseHttpAddress(address);
    if (!parsed) return null;
    if (parsed.method === "GET" && parsed.path === "/status") {
      return { kind: "http", method: "GET", path: "/status" };
    }
    if (parsed.method === "POST" && parsed.path === "/update") {
      return { kind: "http", method: "POST", path: "/update", json: {} };
    }
    if (parsed.method === "POST" && parsed.path === "/gpio/test") {
      if (sectionId === "trolley") {
        return {
          kind: "http",
          method: "POST",
          path: "/gpio/test",
          json: { command: "position", value: 0.5 },
        };
      }
      return {
        kind: "http",
        method: "POST",
        path: "/gpio/test",
        json: { command: "target", value: 22.0 },
      };
    }
    return null;
  }

  if (sectionId === "bridge") {
    if (address === "/<any-address>") {
      return {
        kind: "bridge",
        variant: "direct",
        address: "/vents/fan/1",
        values: [0.5],
      };
    }
    if (address === "/to/<identifier>/<real-address>") {
      return {
        kind: "bridge",
        variant: "to",
        innerAddress: "/vents/fan/1",
        values: [0.5],
      };
    }
    return null;
  }

  if (direction === "admin-to-pi") {
    const vals = oscDefaults(address);
    if (vals === undefined) return null;
    return { kind: "osc", values: vals };
  }

  return null;
}

/** Short human-readable preview of what “Send test” will transmit (for UI). */
export function formatQuickTestPreview(qt: QuickTestSpec): string {
  const fmtVals = (v: (number | string | boolean)[]) =>
    v.length === 0 ? "(no args)" : `[${v.map((x) => (typeof x === "string" ? JSON.stringify(x) : String(x))).join(", ")}]`;

  if (qt.kind === "osc") return fmtVals(qt.values);
  if (qt.kind === "http") {
    if (qt.method === "GET") return `${qt.method} ${qt.path}`;
    const body = qt.json !== undefined ? JSON.stringify(qt.json) : "{}";
    return `${qt.method} ${qt.path} ${body}`;
  }
  if (qt.kind === "bridge" && qt.variant === "direct") {
    return `${qt.address} ${fmtVals(qt.values)}`;
  }
  return `${qt.innerAddress} ${fmtVals(qt.values)} · wrapped as /to/<selected device>/…`;
}
