import { useMemo } from "react";
import type { Components } from "react-markdown";
import Markdown from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

/** Color config for known XML tag families. */
const TAG_STYLES: Record<string, { border: string; bg: string; text: string; pill: string; pillBg: string }> = {
  system:          { border: "border-cyan-500/20",    bg: "bg-cyan-500/5",    text: "text-cyan-400/70",    pill: "text-cyan-400",    pillBg: "bg-cyan-500/15" },
  thinking:        { border: "border-purple-500/20",  bg: "bg-purple-500/5",  text: "text-purple-400/70",  pill: "text-purple-400",  pillBg: "bg-purple-500/15" },
  antThinking:     { border: "border-purple-500/20",  bg: "bg-purple-500/5",  text: "text-purple-400/70",  pill: "text-purple-400",  pillBg: "bg-purple-500/15" },
  result:          { border: "border-emerald-500/20", bg: "bg-emerald-500/5", text: "text-emerald-400/70", pill: "text-emerald-400", pillBg: "bg-emerald-500/15" },
  error:           { border: "border-red-500/20",     bg: "bg-red-500/5",     text: "text-red-400/70",     pill: "text-red-400",     pillBg: "bg-red-500/15" },
  tool_use:        { border: "border-amber-500/20",   bg: "bg-amber-500/5",   text: "text-amber-400/70",   pill: "text-amber-400",   pillBg: "bg-amber-500/15" },
  tool_call:       { border: "border-amber-500/20",   bg: "bg-amber-500/5",   text: "text-amber-400/70",   pill: "text-amber-400",   pillBg: "bg-amber-500/15" },
  tool_result:     { border: "border-amber-500/20",   bg: "bg-amber-500/5",   text: "text-amber-400/70",   pill: "text-amber-400",   pillBg: "bg-amber-500/15" },
  search_results:  { border: "border-blue-500/20",    bg: "bg-blue-500/5",    text: "text-blue-400/70",    pill: "text-blue-400",    pillBg: "bg-blue-500/15" },
  artifact:        { border: "border-indigo-500/20",  bg: "bg-indigo-500/5",  text: "text-indigo-400/70",  pill: "text-indigo-400",  pillBg: "bg-indigo-500/15" },
  "system-reminder":{ border: "border-cyan-500/20",   bg: "bg-cyan-500/5",    text: "text-cyan-400/70",    pill: "text-cyan-400",    pillBg: "bg-cyan-500/15" },
};

const DEFAULT_STYLE = { border: "border-zinc-600/20", bg: "bg-zinc-500/5", text: "text-zinc-400/70", pill: "text-zinc-400", pillBg: "bg-zinc-500/15" };

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

  return segments;
}

/** Compact inline badge for tool use events (Read, Update, Run, etc.) */
function ToolBadge({ content }: { content: string }) {
  const trimmed = content.trim();
  const spaceIdx = trimmed.indexOf(" ");
  const action = spaceIdx > 0 ? trimmed.slice(0, spaceIdx) : trimmed;
  const detail = spaceIdx > 0 ? trimmed.slice(spaceIdx + 1) : "";

  return (
    <div className="my-0.5 flex items-start gap-1.5 text-[11px] min-w-0">
      <span className="inline-flex items-center gap-1 font-medium text-amber-400 bg-amber-500/10 border border-amber-500/20 px-1.5 py-0.5 rounded-md font-mono shrink-0">
        {action}
      </span>
      {detail && (
        <span className="text-zinc-500 font-mono break-all">{detail}</span>
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
      <summary className="flex items-center gap-1.5 cursor-pointer text-[11px] text-purple-400/60 hover:text-purple-400/80 transition-colors select-none list-none">
        <span className="inline-flex items-center font-medium bg-purple-500/10 border border-purple-500/20 px-1.5 py-0.5 rounded-md font-mono shrink-0">
          Thinking
        </span>
        <span className="text-zinc-600 italic truncate">{summary}{hasMore ? " ..." : ""}</span>
      </summary>
      <div className="thinking-expanded mt-1 ml-1 border-l-2 border-purple-500/15 pl-2.5 text-[11px] text-purple-300/40 break-words leading-relaxed">
        <Markdown remarkPlugins={remarkPlugins} components={mdComponents}>{trimmed}</Markdown>
      </div>
    </details>
  );
}

/** Status badge colors */
const STATUS_COLORS: Record<string, string> = {
  EXPLORE: "bg-blue-500/30 text-blue-200 border-blue-500/40",
  DECISION: "bg-emerald-500/30 text-emerald-200 border-emerald-500/40",
  BLOCKED: "bg-red-500/30 text-red-200 border-red-500/40",
  DONE: "bg-green-500/30 text-green-200 border-green-500/40",
  TODO: "bg-amber-500/30 text-amber-200 border-amber-500/40",
  QUESTION: "bg-purple-500/30 text-purple-200 border-purple-500/40",
  READY: "bg-cyan-500/30 text-cyan-200 border-cyan-500/40",
  "IN PROGRESS": "bg-sky-500/30 text-sky-200 border-sky-500/40",
};
const DEFAULT_STATUS_COLOR = "bg-zinc-500/30 text-zinc-200 border-zinc-500/40";

const STATUS_TAG_RE = /(?:\[(EXPLORE|DECISION|BLOCKED|DONE|TODO|QUESTION)\]|\[STATUS:\s*([^\]\n]+)\])/i;
const STATUS_TAG_RE_GLOBAL = /(?:\[(EXPLORE|DECISION|BLOCKED|DONE|TODO|QUESTION)\]|\[STATUS:\s*([^\]\n]+)\])/gi;

function normalizeStatus(status: string): string {
  return status.trim().replace(/\s+/g, " ").toUpperCase();
}

/** Render text with status tags highlighted as badges (supports [EXPLORE] and [STATUS: ...]) */
function TextWithStatusBadges({ text }: { text: string }) {
  STATUS_TAG_RE_GLOBAL.lastIndex = 0;
  const parts: React.ReactNode[] = [];
  let lastIndex = 0;
  let match;
  
  while ((match = STATUS_TAG_RE_GLOBAL.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    
    const status = normalizeStatus(match[1] ?? match[2] ?? "");
    parts.push(
      <span
        key={match.index}
        className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border ${STATUS_COLORS[status] || DEFAULT_STATUS_COLOR}`}
      >
        {status}
      </span>
    );
    
    lastIndex = match.index + match[0].length;
  }
  
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  
  return <>{parts.length > 0 ? parts : text}</>;
}

/** Check if text contains status tags (supports both [EXPLORE] and [STATUS: ...]) */
function hasStatusTags(text: string): boolean {
  return STATUS_TAG_RE.test(text);
}

/** Group Share block lines: consecutive non-status lines form a single markdown block. */
function groupShareLines(content: string): Array<{ kind: "status"; text: string } | { kind: "md"; text: string }> {
  const lines = content.trim().split('\n');
  const groups: Array<{ kind: "status"; text: string } | { kind: "md"; text: string }> = [];
  let mdBuffer: string[] = [];

  const flushMd = () => {
    if (mdBuffer.length > 0) {
      groups.push({ kind: "md", text: mdBuffer.join('\n') });
      mdBuffer = [];
    }
  };

  for (const line of lines) {
    if (hasStatusTags(line)) {
      flushMd();
      groups.push({ kind: "status", text: line });
    } else {
      mdBuffer.push(line);
    }
  }
  flushMd();
  return groups;
}

/** Process Share block content to highlight coordination patterns */
function ShareBlock({ content, header }: { content: string; header?: string | null }) {
  const groups = groupShareLines(content);
  const showHeader = header !== null && header !== "";

  return (
    <div className="my-1 border border-teal-500/20 bg-teal-500/5 rounded-md">
      {showHeader && (
        <div className="flex items-center gap-1.5 px-2 py-1 border-b border-teal-500/10 bg-teal-500/10">
          <svg className="w-3 h-3 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z" />
          </svg>
          <span className="text-[10px] font-medium text-teal-400 uppercase tracking-wide">
            {header ?? "Shared with agents"}
          </span>
        </div>
      )}
      <div className="px-2.5 py-2 text-xs text-teal-100/80 break-words space-y-1">
        {groups.map((group, i) => (
          <div key={i}>
            {group.kind === "status" ? (
              <TextWithStatusBadges text={group.text} />
            ) : (
              <Markdown remarkPlugins={remarkPlugins} components={mdComponents}>
                {balanceCodeFences(group.text)}
              </Markdown>
            )}
          </div>
        ))}
      </div>
    </div>
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
  pre({ children }) {
    return (
      <div className="relative my-2" style={{ maskImage: "linear-gradient(to right, black calc(100% - 16px), transparent)" }}>
        <pre className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 overflow-x-auto max-w-full text-[13px] leading-relaxed">
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
      <code className="bg-zinc-800 text-zinc-300 px-1 py-0.5 rounded text-[0.85em] font-mono">
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
      <thead className="bg-zinc-800/50">
        {children}
      </thead>
    );
  },
  tbody({ children }) {
    return (
      <tbody className="divide-y divide-zinc-800/50">
        {children}
      </tbody>
    );
  },
  tr({ children }) {
    return (
      <tr className="border-b border-zinc-800/50 last:border-b-0">
        {children}
      </tr>
    );
  },
  th({ children }) {
    return (
      <th className="px-3 py-2 text-left text-xs font-semibold text-zinc-300 border-b border-zinc-700/50">
        {children}
      </th>
    );
  },
  td({ children }) {
    return (
      <td className="px-3 py-2 text-xs text-zinc-400">
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
  const segments = useMemo(() => liftShareFromThinking(parseSegments(children)), [children]);

  // Fast path: no XML tags at all
  if (segments.length === 1 && segments[0].kind === "text") {
    return (
      <div className={`overflow-x-hidden ${className ?? ""}`}>
        <Markdown remarkPlugins={remarkPlugins} components={mdComponents}>{balanceCodeFences(children)}</Markdown>
      </div>
    );
  }

  return (
    <div className={`overflow-x-hidden ${className ?? ""}`}>
      {segments.map((seg, i) =>
        seg.kind === "text" ? (
          <Markdown key={i} remarkPlugins={remarkPlugins} components={mdComponents}>{balanceCodeFences(seg.content)}</Markdown>
        ) : (
          <div key={i} className="py-0.5 border-b border-zinc-800/25 last:border-0">
            <TagBlock tag={seg.tag} content={seg.content} shareHeader={shareHeader} />
          </div>
        ),
      )}
    </div>
  );
}
