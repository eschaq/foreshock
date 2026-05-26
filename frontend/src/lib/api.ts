import type { SystemStatus, VendorDetail, VendorOverview } from "../types";

const BASE = "/api";

export async function fetchVendors(): Promise<VendorOverview[]> {
  const res = await fetch(`${BASE}/vendors`);
  if (!res.ok) throw new Error(`vendors ${res.status}`);
  const data = await res.json();
  return data.vendors as VendorOverview[];
}

export async function fetchVendorDetail(
  name: string,
  refresh = false
): Promise<VendorDetail> {
  const qs = refresh ? "?refresh=true" : "";
  const res = await fetch(`${BASE}/vendors/${encodeURIComponent(name)}${qs}`);
  if (!res.ok) throw new Error(`vendor ${name} ${res.status}`);
  return (await res.json()) as VendorDetail;
}

export async function fetchStatus(): Promise<SystemStatus> {
  const res = await fetch(`${BASE}/status`);
  if (!res.ok) throw new Error(`status ${res.status}`);
  return (await res.json()) as SystemStatus;
}

export function livePullStreamUrl(mode: "live" | "seeded"): string {
  return `${BASE}/live-pull/stream?mode=${mode}`;
}
