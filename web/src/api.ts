import type {
  AgentInfo,
  MemoryEpisode,
  MemoryPattern,
  MemoryProfile,
  Settings,
} from "./types";

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

export interface MemoryEpisodesQuery {
  q?: string;
  limit?: number;
}

export function fetchMemoryEpisodes(query: MemoryEpisodesQuery = {}): Promise<MemoryEpisode[]> {
  const params = new URLSearchParams();
  if (query.q && query.q.trim() !== "") params.set("q", query.q.trim());
  if (query.limit && Number.isFinite(query.limit)) params.set("limit", String(query.limit));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return fetchJson(`/api/memory/episodes${suffix}`);
}

export async function forgetMemoryEpisode(id: string): Promise<void> {
  const res = await fetch(`/api/memory/episodes/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export async function forgetMemoryEpisodesBySession(sessionId: string): Promise<void> {
  const res = await fetch(`/api/memory/episodes?session_id=${encodeURIComponent(sessionId)}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export function fetchMemoryProfiles(): Promise<MemoryProfile[]> {
  return fetchJson("/api/memory/profiles");
}

export async function forgetMemoryProfile(agentName: string): Promise<void> {
  const res = await fetch(`/api/memory/profiles/${encodeURIComponent(agentName)}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export async function resetMemoryProfiles(): Promise<void> {
  const res = await fetch("/api/memory/profiles/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export function fetchMemoryPatterns(category = "combo"): Promise<MemoryPattern[]> {
  const suffix = category.trim() ? `?category=${encodeURIComponent(category.trim())}` : "";
  return fetchJson(`/api/memory/patterns${suffix}`);
}

export async function forgetMemoryPattern(key: string): Promise<void> {
  const res = await fetch(`/api/memory/patterns/${encodeURIComponent(key)}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export async function resetAllMemory(): Promise<void> {
  const res = await fetch("/api/memory/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ confirm: true }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}
