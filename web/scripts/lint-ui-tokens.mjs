import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const ROOT = process.cwd();
const SRC_DIR = join(ROOT, "src");
const EXCLUDED_FILES = new Set(["main.css"]);

const RULES = [
  {
    name: "Tailwind palette colors",
    regex: /\b(?:bg|text|border|ring|from|to|via|shadow)-(?:slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-[0-9]{2,3}(?:\/[0-9]{1,3})?\b/g,
    hint: "Use semantic classes (`text-ui-*`, `bg-ui-*`, `border-ui-*`, `badge-*`, `dot-status-*`, `agent-*`).",
  },
  {
    name: "Raw black/white color utilities",
    regex: /\b(?:bg|text|border|ring|from|to|via|shadow)-(?:black|white|current|transparent)(?:\/[0-9]{1,3})?\b/g,
    hint: "Use semantic classes instead of raw color utilities.",
  },
  {
    name: "Arbitrary color utilities",
    regex: /\b(?:bg|text|border|ring|from|to|via|shadow)-\[(?:#[^\]]+|var\([^)]+\)|oklch\([^)]+\)|rgb[a]?\([^)]+\)|hsl[a]?\([^)]+\))\]/g,
    hint: "Define a semantic class in `src/main.css` and consume that class.",
  },
  {
    name: "Direct zinc token usage outside theme layer",
    regex: /--color-zinc-[0-9]+/g,
    hint: "Use semantic classes; keep raw theme tokens confined to `src/main.css`.",
  },
];

function walk(dir) {
  const entries = readdirSync(dir);
  const files = [];
  for (const entry of entries) {
    const abs = join(dir, entry);
    const st = statSync(abs);
    if (st.isDirectory()) {
      files.push(...walk(abs));
      continue;
    }
    if (!/\.(ts|tsx|css)$/.test(entry)) continue;
    if (EXCLUDED_FILES.has(entry)) continue;
    files.push(abs);
  }
  return files;
}

function lineForIndex(text, index) {
  let line = 1;
  for (let i = 0; i < index; i++) {
    if (text.charCodeAt(i) === 10) line++;
  }
  return line;
}

function main() {
  const files = walk(SRC_DIR);
  const violations = [];

  for (const file of files) {
    const content = readFileSync(file, "utf8");
    for (const rule of RULES) {
      rule.regex.lastIndex = 0;
      for (const match of content.matchAll(rule.regex)) {
        const index = match.index ?? 0;
        const line = lineForIndex(content, index);
        violations.push({
          file: relative(ROOT, file),
          line,
          token: match[0],
          rule: rule.name,
          hint: rule.hint,
        });
      }
    }
  }

  if (violations.length === 0) {
    console.log("ui-token-lint: ok");
    return;
  }

  console.error(`ui-token-lint: ${violations.length} violation(s) found`);
  for (const v of violations) {
    console.error(`- ${v.file}:${v.line} [${v.rule}] ${v.token}`);
    console.error(`  ${v.hint}`);
  }
  process.exit(1);
}

main();
