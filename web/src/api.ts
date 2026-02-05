import type { AgentInfo, Settings } from "./types";

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export interface ServerSession {
  id: string;
  title: string;
  agent_names: (string | AgentInfo)[];
  updated_at: string;
}

export interface SessionStatus {
  is_running: boolean;
  is_paused: boolean;
  current_round: number;
  last_event_time: string;
}

export function fetchSessions(): Promise<ServerSession[]> {
  return fetchJson("/api/sessions");
}

export function fetchSession(id: string): Promise<ServerSession> {
  return fetchJson(`/api/sessions/${id}`);
}

export function fetchSessionStatus(id: string): Promise<SessionStatus> {
  return fetchJson(`/api/sessions/${id}/status`);
}

export async function deleteSession(id: string): Promise<void> {
  const res = await fetch(`/api/sessions/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export interface DirectoryListing {
  path: string;
  parent: string | null;
  directories: string[];
}

export function fetchDirectories(path?: string): Promise<DirectoryListing> {
  const params = path ? `?path=${encodeURIComponent(path)}` : "";
  return fetchJson(`/api/filesystem/list${params}`);
}

export function fetchSettings(): Promise<Settings> {
  return fetchJson("/api/settings");
}

export async function updateSettings(updates: Partial<Settings>): Promise<Settings> {
  const res = await fetch("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function resetSetting(key: string): Promise<void> {
  const res = await fetch(`/api/settings/${key}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}
