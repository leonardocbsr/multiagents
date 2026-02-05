import { useMemo } from "react";
import type { Components } from "react-markdown";
import Markdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import { Card, CardContent, CardFooter, CardHeader } from "./ui";

/** Color config for known XML tag families. */
const TAG_STYLES: Record<string, { border: string; bg: string; text: string; pill: string; pillBg: string }> = {
  system: { border: "border-ui-info-soft", bg: "bg-ui-info-soft", text: "text-ui-info", pill: "text-ui-info", pillBg: "bg-ui-info-soft" },
  thinking: { border: "border-ui-violet-soft", bg: "bg-ui-violet-soft", text: "text-ui-violet", pill: "text-ui-violet", pillBg: "bg-ui-violet-soft" },
  antThinking: { border: "border-ui-violet-soft", bg: "bg-ui-violet-soft", text: "text-ui-violet", pill: "text-ui-violet", pillBg: "bg-ui-violet-soft" },
  result: { border: "border-ui-success-soft", bg: "bg-ui-success-soft", text: "text-ui-success", pill: "text-ui-success", pillBg: "bg-ui-success-soft" },
  error: { border: "border-ui-danger-soft", bg: "bg-ui-danger-soft", text: "text-ui-danger", pill: "text-ui-danger", pillBg: "bg-ui-danger-soft" },
  tool_use: { border: "border-ui-warn-soft", bg: "bg-ui-warn-soft", text: "text-ui-warn", pill: "text-ui-warn", pillBg: "bg-ui-warn-soft" },
  tool_call: { border: "border-ui-warn-soft", bg: "bg-ui-warn-soft", text: "text-ui-warn", pill: "text-ui-warn", pillBg: "bg-ui-warn-soft" },
  tool_result: { border: "border-ui-warn-soft", bg: "bg-ui-warn-soft", text: "text-ui-warn", pill: "text-ui-warn", pillBg: "bg-ui-warn-soft" },
  search_results: { border: "border-ui-info-soft", bg: "bg-ui-info-soft", text: "text-ui-info", pill: "text-ui-info", pillBg: "bg-ui-info-soft" },
  artifact: { border: "border-ui-violet-soft", bg: "bg-ui-violet-soft", text: "text-ui-violet", pill: "text-ui-violet", pillBg: "bg-ui-violet-soft" },
  tool_output: { border: "border-ui-soft", bg: "bg-ui-soft", text: "text-ui-subtle", pill: "text-ui-subtle", pillBg: "bg-ui-soft" },
  "system-reminder": { border: "border-ui-info-soft", bg: "bg-ui-info-soft", text: "text-ui-info", pill: "text-ui-info", pillBg: "bg-ui-info-soft" },
};

const DEFAULT_STYLE = { border: "border-ui-soft", bg: "bg-ui-soft", text: "text-ui-muted", pill: "text-ui-muted", pillBg: "bg-ui-soft" };

type Segment =
  | { kind: "text"; content: string }
  | { kind: "tag"; tag: string; content: string };

/**
 * Split text into plain-text and XML-tagged segments.
 * Handles both complete `<tag>...</tag>` and unclosed `<tag>...` at end-of-string (streaming).
 */
function parseSegments(input: string): Segment[] {
  // Match <tagname>content</tagname> or unclosed <tagname>content at end
  const re = /<([\w][\w.-]*?)>([\s\S]*?)(?:<\/\1>|$)/g;
  const segments: Segment[] = [];
  let lastIndex = 0;

  for (const match of input.matchAll(re)) {
    const offset = match.index!;
    if (offset > lastIndex) {
      segments.push({ kind: "text", content: input.slice(lastIndex, offset) });
    }
    segments.push({ kind: "tag", tag: match[1], content: match[2] });
    lastIndex = offset + match[0].length;
  }

  if (lastIndex < input.length) {
    segments.push({ kind: "text", content: input.slice(lastIndex) });
  }

  // Merge consecutive same-tag segments (e.g. multiple <thinking> deltas from streaming)
  // so they render as one block instead of many separate badges.
  const merged: Segment[] = [];
  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    // Skip whitespace-only text between two tag segments with the same tag name
    if (
      seg.kind === "text" &&
      seg.content.trim() === "" &&
      merged.length > 0 &&
      merged[merged.length - 1].kind === "tag"
    ) {
      const next = segments[i + 1];
      if (next?.kind === "tag" && next.tag === (merged[merged.length - 1] as { tag: string }).tag) {
        continue; // drop the whitespace, next iteration will merge the tags
      }
    }
    const prev = merged[merged.length - 1];
    if (seg.kind === "tag" && prev?.kind === "tag" && prev.tag === seg.tag) {
      prev.content += seg.content;
    } else {
      merged.push(seg);
    }
  }

  return merged;
}

/** Compact inline badge for tool use events (Read, Update, Run, etc.) */
function ToolBadge({ content }: { content: string }) {
  const trimmed = content.trim();
  const spaceIdx = trimmed.indexOf(" ");
  const action = spaceIdx > 0 ? trimmed.slice(0, spaceIdx) : trimmed;
  const detail = spaceIdx > 0 ? trimmed.slice(spaceIdx + 1) : "";

  return (
    <div className="my-0.5 flex items-start gap-1.5 text-[11px] min-w-0">
      <span className="inline-flex items-center gap-1 font-medium text-ui-warn bg-ui-warn-soft border border-ui-warn-soft px-1.5 py-0.5 rounded-md font-mono shrink-0">
        {action}
      </span>
      {detail && (
        <span className="text-ui-subtle font-mono break-all">{detail}</span>
      )}
    </div>
  );
}

/** Strip markdown formatting for plain-text summary previews. */
function stripMarkdown(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, "$1")  // bold
    .replace(/\*(.+?)\*/g, "$1")      // italic
    .replace(/__(.+?)__/g, "$1")      // bold alt
    .replace(/_(.+?)_/g, "$1")        // italic alt
    .replace(/`(.+?)`/g, "$1")        // inline code
    .replace(/^#+\s+/gm, "")          // headings
    .replace(/\[(.+?)\]\(.+?\)/g, "$1"); // links
}

/** Collapsible thinking/reasoning block */
function ThinkingBlock({ content }: { content: string }) {
  const trimmed = content.trim();
  // Show a short summary line — first sentence or first 120 chars
  const plain = stripMarkdown(trimmed);
  const endIdx = plain.search(/[.!?\n]/);
  const summary = endIdx > 0 && endIdx < 120 ? plain.slice(0, endIdx + 1) : plain.slice(0, 120);
  const hasMore = trimmed.length > summary.length;

  return (
    <details className="my-0.5 group">
      <summary className="flex items-center gap-1.5 cursor-pointer text-[11px] text-ui-violet transition-colors select-none list-none">
        <span className="inline-flex items-center font-medium bg-ui-violet-soft border border-ui-violet-soft px-1.5 py-0.5 rounded-md font-mono shrink-0">
          Thinking
        </span>
        <span className="text-ui-faint italic truncate">{summary}{hasMore ? " ..." : ""}</span>
      </summary>
      <div className="thinking-expanded mt-1 ml-1 border-l-2 border-ui-violet-soft pl-2.5 text-[11px] text-ui-violet break-words leading-relaxed">
        <Markdown remarkPlugins={remarkPlugins} components={mdComponents}>{trimmed}</Markdown>
      </div>
    </details>
  );
}

/** Collapsible monospace block for tool output (collapsed by default) */
function ToolOutputBlock({ content }: { content: string }) {
  const trimmed = content.trim();
  const lines = trimmed.split("\n");
  const preview = lines[0]?.slice(0, 120) ?? "";
  const hasMore = lines.length > 1 || trimmed.length > 120;

  return (
    <details className="my-0.5 group">
      <summary className="flex items-center gap-1.5 cursor-pointer text-[11px] text-ui-subtle transition-colors select-none list-none">
        <span className="inline-flex items-center font-medium bg-ui-soft border border-ui-soft px-1.5 py-0.5 rounded-md font-mono shrink-0">
          Output
        </span>
        <span className="text-ui-faint font-mono truncate">{preview}{hasMore ? " ..." : ""}</span>
      </summary>
      <div className="mt-1 ml-1 border-l-2 border-ui-soft pl-2.5 text-[11px] text-ui-subtle font-mono whitespace-pre-wrap break-words leading-relaxed max-h-64 overflow-y-auto">
        {trimmed}
      </div>
    </details>
  );
}

/** Status badge colors */
const STATUS_COLORS: Record<string, string> = {
  EXPLORE: "badge-info",
  DECISION: "badge-success",
  BLOCKED: "badge-danger",
  DONE: "badge-success",
  TODO: "badge-warn",
  QUESTION: "badge-violet",
  READY: "badge-cyan",
  "IN PROGRESS": "badge-info",
};
const DEFAULT_STATUS_COLOR = "badge-info";

const STATUS_TAG_RE_GLOBAL = /(?:\[(EXPLORE|DECISION|BLOCKED|DONE|TODO|QUESTION)\]|\[STATUS:\s*([^\]\n]+)\])/gi;
const HANDOFF_RE_GLOBAL = /\[HANDOFF:(\w+)\]/gi;

function normalizeStatus(status: string): string {
  return status.trim().replace(/\s+/g, " ").toUpperCase();
}

function extractStatuses(text: string): string[] {
  STATUS_TAG_RE_GLOBAL.lastIndex = 0;
  const found: string[] = [];
  let match: RegExpExecArray | null;
  while ((match = STATUS_TAG_RE_GLOBAL.exec(text)) !== null) {
    found.push(normalizeStatus(match[1] ?? match[2] ?? ""));
  }
  return found;
}

function extractHandoffs(text: string): string[] {
  HANDOFF_RE_GLOBAL.lastIndex = 0;
  const found: string[] = [];
  let match: RegExpExecArray | null;
  while ((match = HANDOFF_RE_GLOBAL.exec(text)) !== null) {
    const agent = match[1];
    if (!found.some(h => h.toLowerCase() === agent.toLowerCase())) {
      found.push(agent);
    }
  }
  return found;
}

function stripStatusTags(text: string): string {
  STATUS_TAG_RE_GLOBAL.lastIndex = 0;
  HANDOFF_RE_GLOBAL.lastIndex = 0;
  return text
    .replace(STATUS_TAG_RE_GLOBAL, "")
    .replace(HANDOFF_RE_GLOBAL, "")
    .replace(/[ \t]+$/gm, "")
    .replace(/^\n+/, "")
    .trim();
}

/** Process Share block content to highlight coordination patterns */
function ShareBlock({ content, header }: { content: string; header?: string | null }) {
  const statuses = extractStatuses(content);
  const handoffs = extractHandoffs(content);
  const markdownContent = stripStatusTags(content);
  const showHeader = header !== null && header !== "";

  return (
    <Card className="my-1.5 share-card">
      {showHeader && (
        <CardHeader className="flex items-center gap-1.5 px-2.5 py-1.5 surface-share-header">
          <svg className="w-3 h-3 text-ui-subtle opacity-70" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
          </svg>
          <span className="text-[10px] font-medium text-ui-subtle uppercase tracking-[0.06em]">
            {header ?? "Shared with agents"}
          </span>
        </CardHeader>
      )}
      <CardContent className="share-card-content px-3 py-2 text-share-body break-words space-y-1">
        {markdownContent && (
          <Markdown remarkPlugins={remarkPlugins} components={mdComponents}>
            {balanceCodeFences(markdownContent)}
          </Markdown>
        )}
      </CardContent>
      {(statuses.length > 0 || handoffs.length > 0) && (
        <CardFooter className="share-card-footer px-3 py-2 overflow-x-auto">
          <div className="flex flex-nowrap gap-1.5 whitespace-nowrap pb-0.5">
            {statuses.map((status, i) => (
              <span key={`${status}-${i}`} className={`badge share-status-badge shrink-0 ${STATUS_COLORS[status] || DEFAULT_STATUS_COLOR}`}>
                {status}
              </span>
            ))}
            {handoffs.map((agent, i) => (
              <span key={`handoff-${i}`} className="badge share-status-badge badge-violet shrink-0">
                → {agent}
              </span>
            ))}
          </div>
        </CardFooter>
      )}
    </Card>
  );
}

/**
 * Post-process segments: extract <Share> blocks nested inside thinking segments
 * so they render as visible ShareBlocks instead of being buried in collapsed thinking.
 */
function liftShareFromThinking(segments: Segment[]): Segment[] {
  const shareRe = /<Share>([\s\S]*?)(?:<\/Share>|$)/gi;
  const result: Segment[] = [];

  for (const seg of segments) {
    if (seg.kind === "tag" && (seg.tag === "thinking" || seg.tag === "antThinking") && /<Share>/i.test(seg.content)) {
      let lastIndex = 0;
      for (const match of seg.content.matchAll(shareRe)) {
        const offset = match.index!;
        if (offset > lastIndex) {
          const before = seg.content.slice(lastIndex, offset).trim();
          if (before) result.push({ kind: "tag", tag: seg.tag, content: before });
        }
        result.push({ kind: "tag", tag: "Share", content: match[1] });
        lastIndex = offset + match[0].length;
      }
      const after = seg.content.slice(lastIndex).trim();
      if (after) result.push({ kind: "tag", tag: seg.tag, content: after });
    } else {
      result.push(seg);
    }
  }
  return result;
}

function TagBlock({ tag, content, shareHeader }: { tag: string; content: string; shareHeader?: string | null }) {
  if (tag === "tool") return <ToolBadge content={content} />;
  if (tag === "tool_output") return <ToolOutputBlock content={content} />;
  if (tag === "thinking" || tag === "antThinking") return <ThinkingBlock content={content} />;
  // Share tags indicate content shared with other agents - style distinctly
  if (tag.toLowerCase() === "share") {
    return <ShareBlock content={content} header={shareHeader} />;
  }
  const style = TAG_STYLES[tag] ?? DEFAULT_STYLE;
  const trimmed = content.trim();
  return (
    <div className={`my-1.5 border-l-2 ${style.border} ${style.bg} rounded-r px-2.5 py-1.5`}>
      <span className={`inline-block text-[10px] font-mono font-medium ${style.pill} ${style.pillBg} px-1.5 py-0.5 rounded-full mb-1`}>
        {tag}
      </span>
      {trimmed && (
        <div className={`text-xs ${style.text} whitespace-pre-wrap break-words`}>
          {trimmed}
        </div>
      )}
    </div>
  );
}

/**
 * Ensure code fences are balanced so react-markdown doesn't swallow the rest
 * of the content into an unclosed code block. If the segment has an odd number
 * of triple-backtick fences, append a closing fence.
 */
function balanceCodeFences(text: string): string {
  const fenceCount = (text.match(/^`{3,}/gm) ?? []).length;
  if (fenceCount % 2 !== 0) {
    return text + "\n```\n";
  }
  return text;
}

const remarkPlugins = [remarkGfm, remarkBreaks];

const mdComponents: Components = {
  p({ children }) {
    return (
      <p className="my-0.5 leading-[1.4] text-ui">
        {children}
      </p>
    );
  },
  ul({ children }) {
    return (
      <ul className="my-0.5 pl-5 space-y-0.5 list-disc">
        {children}
      </ul>
    );
  },
  ol({ children }) {
    return (
      <ol className="my-0.5 pl-5 space-y-0.5 list-decimal">
        {children}
      </ol>
    );
  },
  li({ children }) {
    return (
      <li className="leading-[1.35] text-ui">
        {children}
      </li>
    );
  },
  h1({ children }) {
    return (
      <h1 className="mt-2 mb-1 text-[1.45em] leading-tight font-semibold text-ui-strong">
        {children}
      </h1>
    );
  },
  h2({ children }) {
    return (
      <h2 className="mt-2 mb-1 text-[1.25em] leading-tight font-semibold text-ui-strong">
        {children}
      </h2>
    );
  },
  h3({ children }) {
    return (
      <h3 className="mt-1.5 mb-1 text-[1.1em] leading-tight font-semibold text-ui-strong">
        {children}
      </h3>
    );
  },
  blockquote({ children }) {
    return (
      <blockquote className="my-1 pl-3 border-l-2 border-ui-soft text-ui-muted">
        {children}
      </blockquote>
    );
  },
  pre({ children }) {
    return (
      <div className="relative my-2" style={{ maskImage: "linear-gradient(to right, black calc(100% - 16px), transparent)" }}>
        <pre className="bg-ui-canvas border border-ui rounded-lg p-3 overflow-x-auto max-w-full text-[13px] leading-relaxed">
          {children}
        </pre>
      </div>
    );
  },
  code({ className, children }) {
    if (className?.startsWith("language-")) {
      return <code className={`${className} font-mono`}>{children}</code>;
    }
    return (
      <code className="bg-ui-elevated text-ui px-1 py-0.5 rounded text-[0.85em] font-mono">
        {children}
      </code>
    );
  },
  table({ children }) {
    return (
      <div className="overflow-x-auto my-3" style={{ maskImage: "linear-gradient(to right, black calc(100% - 16px), transparent)" }}>
        <table className="w-full border-collapse text-sm">
          {children}
        </table>
      </div>
    );
  },
  thead({ children }) {
    return (
      <thead className="bg-ui-elevated">
        {children}
      </thead>
    );
  },
  tbody({ children }) {
    return (
      <tbody className="divide-y divide-ui-soft">
        {children}
      </tbody>
    );
  },
  tr({ children }) {
    return (
      <tr className="border-b border-ui last:border-b-0">
        {children}
      </tr>
    );
  },
  th({ children }) {
    return (
      <th className="px-3 py-2 text-left text-xs font-semibold text-ui border-b border-ui-soft">
        {children}
      </th>
    );
  },
  td({ children }) {
    return (
      <td className="px-3 py-2 text-xs text-ui-muted">
        {children}
      </td>
    );
  },
  img({ src, alt }) {
    return (
      <img src={src} alt={alt || ""} className="max-w-full h-auto rounded my-2" loading="lazy" />
    );
  },
};

interface Props {
  children: string;
  className?: string;
  shareHeader?: string | null;
}

export default function StyledMarkdown({ children, className, shareHeader }: Props) {
  const normalized = useMemo(() => children.replace(/^\n+/, ""), [children]);
  const segments = useMemo(() => liftShareFromThinking(parseSegments(normalized)), [normalized]);
  const wrapperClass = `overflow-x-hidden [&>*:first-child]:mt-0 [&>*:last-child]:mb-0 ${className ?? ""}`;

  // Fast path: no XML tags at all
  if (segments.length === 1 && segments[0].kind === "text") {
    return (
      <div className={wrapperClass}>
        <Markdown remarkPlugins={remarkPlugins} components={mdComponents}>{balanceCodeFences(normalized)}</Markdown>
      </div>
    );
  }

  return (
    <div className={wrapperClass}>
      {segments.map((seg, i) =>
        seg.kind === "text" ? (
          <Markdown key={i} remarkPlugins={remarkPlugins} components={mdComponents}>{balanceCodeFences(seg.content)}</Markdown>
        ) : (
          <div key={i} className="py-0.5 border-b border-ui-soft last:border-0">
            <TagBlock tag={seg.tag} content={seg.content} shareHeader={shareHeader} />
          </div>
        ),
      )}
    </div>
  );
}
