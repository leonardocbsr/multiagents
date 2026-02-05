import { useCallback, useEffect, useMemo, useState } from "react";
import { RefreshCcw, RotateCcw, Search, Trash2 } from "lucide-react";
import {
  fetchMemoryEpisodes,
  fetchMemoryPatterns,
  fetchMemoryProfiles,
  forgetMemoryEpisode,
  forgetMemoryEpisodesBySession,
  forgetMemoryPattern,
  forgetMemoryProfile,
  resetAllMemory,
  resetMemoryProfiles,
} from "../api";
import type { MemoryEpisode, MemoryPattern, MemoryProfile } from "../types";
import { Badge, Button, Input, Panel } from "./ui";

interface Props {
  active: boolean;
}

const MAX_LIMIT = 500;

function formatTimestamp(value: string): string {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return "unknown";
  return new Date(parsed).toLocaleString();
}

function toErrorMessage(err: unknown): string {
  if (err instanceof Error && err.message) return err.message;
  return "Request failed";
}

function summarizeRoles(roleScores: Record<string, number> | undefined): string {
  if (!roleScores) return "";
  const ranked = Object.entries(roleScores)
    .filter(([, score]) => Number.isFinite(score))
    .sort((a, b) => b[1] - a[1])
    .slice(0, 2)
    .map(([role, score]) => `${role}:${score.toFixed(2)}`);
  return ranked.join(" · ");
}

export default function MemoryManagementPanel({ active }: Props) {
  const [episodes, setEpisodes] = useState<MemoryEpisode[]>([]);
  const [profiles, setProfiles] = useState<MemoryProfile[]>([]);
  const [patterns, setPatterns] = useState<MemoryPattern[]>([]);

  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [limitInput, setLimitInput] = useState("20");
  const [limit, setLimit] = useState(20);
  const [categoryInput, setCategoryInput] = useState("combo");
  const [category, setCategory] = useState("combo");

  const [loading, setLoading] = useState(false);
  const [actionKey, setActionKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!active) return;
    setLoading(true);
    setError(null);
    try {
      const [episodeRows, profileRows, patternRows] = await Promise.all([
        fetchMemoryEpisodes({ q: query, limit }),
        fetchMemoryProfiles(),
        fetchMemoryPatterns(category),
      ]);
      setEpisodes(episodeRows);
      setProfiles(profileRows);
      setPatterns(patternRows);
    } catch (err) {
      setError(toErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [active, category, limit, query]);

  useEffect(() => {
    void load();
  }, [load]);

  const busy = loading || actionKey !== null;

  const runAction = useCallback(
    async (key: string, successMessage: string, fn: () => Promise<void>) => {
      setActionKey(key);
      setNotice(null);
      setError(null);
      try {
        await fn();
        setNotice(successMessage);
        await load();
      } catch (err) {
        setError(toErrorMessage(err));
      } finally {
        setActionKey(null);
      }
    },
    [load],
  );

  const applySearch = useCallback(() => {
    setQuery(queryInput.trim());
  }, [queryInput]);

  const clearSearch = useCallback(() => {
    setQueryInput("");
    setQuery("");
  }, []);

  const applyLimit = useCallback(() => {
    const parsed = Number(limitInput);
    if (!Number.isFinite(parsed) || parsed <= 0 || parsed > MAX_LIMIT) {
      setError(`Limit must be between 1 and ${MAX_LIMIT}.`);
      return;
    }
    setLimit(Math.floor(parsed));
  }, [limitInput]);

  const applyCategory = useCallback(() => {
    const next = categoryInput.trim();
    if (!next) {
      setError("Category is required.");
      return;
    }
    setCategory(next);
  }, [categoryInput]);

  const groupedSessions = useMemo(() => {
    const set = new Set<string>();
    for (const row of episodes) {
      if (row.session_id) set.add(row.session_id);
    }
    return set;
  }, [episodes]);

  return (
    <div className="space-y-3">
      {(error || notice) && (
        <Panel className="bg-ui-elevated">
          {error && <p className="text-xs text-ui-danger">{error}</p>}
          {notice && <p className="text-xs text-ui-success">{notice}</p>}
        </Panel>
      )}

      <Panel className="space-y-3 bg-ui-elevated">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <p className="text-xs font-medium text-ui">Episodes</p>
            <Badge tone="neutral">{episodes.length}</Badge>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => void load()}
            disabled={busy}
            icon={<RefreshCcw size={12} />}
            title="Reload memory"
          >
            Reload
          </Button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-[1fr_88px_auto_auto] gap-2">
          <Input
            type="text"
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            placeholder="Search episodes"
            className="text-xs"
          />
          <Input
            type="number"
            min={1}
            max={MAX_LIMIT}
            value={limitInput}
            onChange={(e) => setLimitInput(e.target.value)}
            className="text-xs text-right"
            title={`Max ${MAX_LIMIT}`}
          />
          <Button size="sm" variant="secondary" onClick={applyLimit} disabled={busy}>
            Apply Limit
          </Button>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="secondary" onClick={applySearch} disabled={busy} icon={<Search size={12} />}>
              Search
            </Button>
            <Button size="sm" variant="ghost" onClick={clearSearch} disabled={busy}>
              Clear
            </Button>
          </div>
        </div>

        <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
          {loading && <p className="text-xs text-ui-subtle">Loading memory data...</p>}
          {!loading && episodes.length === 0 && <p className="text-xs text-ui-subtle">No episodes found.</p>}

          {!loading && episodes.map((ep) => (
            <div key={ep.id} className="rounded-md border border-ui p-2 bg-ui-surface space-y-2">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs text-ui font-medium truncate">{ep.query || "(empty query)"}</p>
                  <p className="text-[11px] text-ui-muted leading-relaxed break-words">{ep.summary || "No summary"}</p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      if (!window.confirm(`Forget episode ${ep.id}?`)) return;
                      void runAction(`episode:${ep.id}`, "Episode forgotten.", () => forgetMemoryEpisode(ep.id));
                    }}
                    disabled={busy}
                    icon={<Trash2 size={12} />}
                    title="Forget episode"
                  >
                    Forget
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      if (!window.confirm(`Forget all episodes for session ${ep.session_id}?`)) return;
                      void runAction(`session:${ep.session_id}`, "Session episodes forgotten.", () => forgetMemoryEpisodesBySession(ep.session_id));
                    }}
                    disabled={busy || !ep.session_id}
                    icon={<Trash2 size={12} />}
                    title="Forget session episodes"
                  >
                    Session
                  </Button>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone={ep.converged ? "success" : "warn"}>{ep.converged ? "converged" : "open"}</Badge>
                <Badge tone="neutral">{ep.session_id || "no-session"}</Badge>
                <span className="text-[10px] text-ui-faint">{formatTimestamp(ep.created_at)}</span>
              </div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel className="space-y-3 bg-ui-elevated">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <p className="text-xs font-medium text-ui">Agent Profiles</p>
            <Badge tone="neutral">{profiles.length}</Badge>
          </div>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              if (!window.confirm("Reset all agent profiles?")) return;
              void runAction("profiles:reset", "Agent profiles reset.", () => resetMemoryProfiles());
            }}
            disabled={busy}
            icon={<RotateCcw size={12} />}
          >
            Reset Profiles
          </Button>
        </div>

        <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
          {!loading && profiles.length === 0 && <p className="text-xs text-ui-subtle">No agent profiles found.</p>}
          {!loading && profiles.map((profile) => (
            <div key={profile.agent_name} className="rounded-md border border-ui p-2 bg-ui-surface space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs font-medium text-ui capitalize">{profile.agent_name}</p>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    if (!window.confirm(`Forget profile for ${profile.agent_name}?`)) return;
                    void runAction(`profile:${profile.agent_name}`, "Profile forgotten.", () => forgetMemoryProfile(profile.agent_name));
                  }}
                  disabled={busy}
                  icon={<Trash2 size={12} />}
                >
                  Forget
                </Button>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone="accent">{profile.best_role || "unassigned"}</Badge>
                <Badge tone="neutral">sessions:{profile.total_sessions}</Badge>
                <span className="text-[10px] text-ui-faint">{summarizeRoles(profile.role_scores)}</span>
              </div>
              {profile.strengths.length > 0 && (
                <p className="text-[11px] text-ui-muted">{profile.strengths.slice(0, 2).join(" · ")}</p>
              )}
            </div>
          ))}
        </div>
      </Panel>

      <Panel className="space-y-3 bg-ui-elevated">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <p className="text-xs font-medium text-ui">Ensemble Patterns</p>
            <Badge tone="neutral">{patterns.length}</Badge>
          </div>
          <div className="flex items-center gap-2">
            <Input
              type="text"
              value={categoryInput}
              onChange={(e) => setCategoryInput(e.target.value)}
              placeholder="category"
              className="w-24 text-xs"
            />
            <Button size="sm" variant="secondary" onClick={applyCategory} disabled={busy}>
              Apply
            </Button>
          </div>
        </div>

        <div className="space-y-2 max-h-52 overflow-y-auto pr-1">
          {!loading && patterns.length === 0 && <p className="text-xs text-ui-subtle">No patterns found.</p>}
          {!loading && patterns.map((pattern) => (
            <div key={pattern.key} className="rounded-md border border-ui p-2 bg-ui-surface space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs text-ui font-medium truncate">{pattern.key}</p>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    if (!window.confirm(`Forget pattern ${pattern.key}?`)) return;
                    void runAction(`pattern:${pattern.key}`, "Pattern forgotten.", () => forgetMemoryPattern(pattern.key));
                  }}
                  disabled={busy}
                  icon={<Trash2 size={12} />}
                >
                  Forget
                </Button>
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone="neutral">{pattern.category}</Badge>
                <span className="text-[10px] text-ui-faint">{formatTimestamp(pattern.updated_at)}</span>
              </div>
              <pre className="text-[10px] text-ui-muted whitespace-pre-wrap break-words bg-ui-soft border border-ui-soft rounded px-2 py-1">
                {typeof pattern.value === "string" ? pattern.value : JSON.stringify(pattern.value, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      </Panel>

      <Panel className="space-y-2 border-ui-strong bg-ui-danger-soft">
        <p className="text-xs font-medium text-ui-danger">Danger Zone</p>
        <p className="text-[11px] text-ui-subtle">Reset clears episodes, profiles, and patterns.</p>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="danger"
            onClick={() => {
              if (!window.confirm("Reset all memory data? This cannot be undone.")) return;
              void runAction("memory:reset", "All memory data reset.", () => resetAllMemory());
            }}
            disabled={busy}
            icon={<RotateCcw size={12} />}
          >
            Reset All Memory
          </Button>
          <span className="text-[10px] text-ui-faint">Tracked sessions: {groupedSessions.size}</span>
        </div>
      </Panel>
    </div>
  );
}
