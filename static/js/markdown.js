function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function urlContinuationAfterSpace(tail) {
  if (!tail || tail[0] === " ") return false;
  if (/^[\u3000-\u9fff\uff00-\uffef(（]/.test(tail)) return false;
  const head = tail.match(/^[a-zA-Z0-9._~:/?#[\]@!$&'()*+,;=%\-]+/);
  if (!head) return false;
  const chunk = head[0];
  if (/[\.\/:]/.test(chunk)) return true;
  if (/^\d{2,5}\b/.test(tail)) return true;
  return /nextvps\.online|networking\.|\.gw\.|sekirei\.|jp-osk|lnd\./i.test(chunk);
}

function normalizeUrlLikeStrings(text) {
  if (!text) return text;
  let result = "";
  let i = 0;
  while (i < text.length) {
    const slice = text.slice(i);
    const proto = slice.match(/^https?:\/\//i);
    if (!proto) {
      result += text[i];
      i += 1;
      continue;
    }
    const start = i;
    i += proto[0].length;
    while (i < text.length) {
      const c = text[i];
      if (/[A-Za-z0-9._~:/?#[\]@!$&'()*+,;=%\-]/.test(c)) {
        i += 1;
        continue;
      }
      if (c === " ") {
        if (urlContinuationAfterSpace(text.slice(i + 1))) {
          i += 1;
          continue;
        }
        break;
      }
      break;
    }
    const raw = text.slice(start, i);
    result += raw.includes(" ") ? raw.replace(/\s+/g, "") : raw;
  }
  return result;
}

function repairBrokenInlineLinks(text) {
  if (!text) return text;
  return text.replace(
    /\[([^\]]+?)\((https?:\/\/[^\s)）]+)\)/g,
    "[$1]($2)"
  );
}

function normalizeMultilineMarkdownLinks(text) {
  if (!text) return text;
  const { work, fences } = protectMarkdownFences(text);
  const out = work.replace(
    /(!?)\[([\s\S]*?)\]\(\s*([^)\n]+?)(?:\s+["']([^"']*)["'])?\s*\)/g,
    (match, bang, label, url, title) => {
      const cleanLabel = String(label).replace(/\s+/g, " ").trim();
      const cleanUrl = String(url).replace(/\s+/g, "");
      const hasTitle = title !== undefined;
      const titlePart = hasTitle ? ` "${String(title).trim()}"` : "";
      if (label === cleanLabel && url === cleanUrl && !hasTitle) return match;
      return `${bang}[${cleanLabel}](${cleanUrl}${titlePart})`;
    }
  );
  return restoreMarkdownFences(out, fences);
}

function normalizeMarkdownImages(text) {
  if (!text) return text;
  let out = text.replace(/!\s+\[/g, "![").replace(/!\[([^\]]*)\]\s*\(/g, "![$1](");
  out = out.replace(
    /!\[([^\]]*)\]\(\s*([^)\n]+?)(?:\s+["']([^"']*)["'])?\s*\)/g,
    (match, alt, url, title) => {
      const cleanUrl = String(url).replace(/\s+/g, "");
      const hasTitle = title !== undefined;
      const titlePart = hasTitle ? ` "${String(title).trim()}"` : "";
      if (url === cleanUrl && !hasTitle) return match;
      return `![${alt}](${cleanUrl}${titlePart})`;
    }
  );
  return out;
}

function dedupeMarkdownImages(text) {
  if (!text) return text;
  const re = /!\[([^\]]*)\]\(([^)]+)\)/g;
  const spans = [];
  let m;
  while ((m = re.exec(text)) !== null) {
    spans.push({
      start: m.index,
      end: m.index + m[0].length,
      key: String(m[2]).replace(/\s+/g, ""),
    });
  }
  if (spans.length <= 1) return text;
  const lastByKey = new Map();
  spans.forEach((span, index) => {
    if (span.key) lastByKey.set(span.key, index);
  });
  let out = "";
  let cursor = 0;
  for (let i = 0; i < spans.length; i += 1) {
    const span = spans[i];
    out += text.slice(cursor, span.start);
    if (lastByKey.get(span.key) === i) {
      out += text.slice(span.start, span.end);
    }
    cursor = span.end;
  }
  out += text.slice(cursor);
  return out;
}

const GENERATED_IMAGE_PATH_RE = /\/api\/generated-images\/[a-f0-9]{32}/i;

function stripOtherGeneratedImageMarkdown(text, keepUrl = "") {
  if (!text) return text;
  const keepKey = String(keepUrl || "").replace(/\s+/g, "");
  return text.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (match, _alt, url) => {
    const key = String(url).replace(/\s+/g, "");
    if (!GENERATED_IMAGE_PATH_RE.test(key)) return match;
    if (keepKey && key === keepKey) return match;
    return "";
  });
}

function looksLikeLatexContent(inner) {
  const t = String(inner || "").trim();
  if (!t) return false;
  if (/\\[a-zA-Z]+/.test(t)) return true;
  if (/[_^{}]/.test(t) && /[=+\-*/]/.test(t)) return true;
  if (/[A-Za-z]_[{A-Za-z0-9-]/.test(t)) return true;
  return false;
}

function normalizeLooseLatexMath(work) {
  return work.replace(/\(\s*([^()\n]+?)\s*\)/g, (match, inner) => {
    if (!looksLikeLatexContent(inner)) return match;
    return `$${inner.trim()}$`;
  });
}

function normalizeInlineCodeFences(text) {
  if (!text || !/```[a-zA-Z]/.test(text)) return text;
  let work = text;
  work = work.replace(/([^\n`]+?)```([a-zA-Z][\w+-]*)\b/g, (_match, prefix, lang) => {
    const lead = String(prefix).replace(/\s+$/, "");
    if (!lead) return `\n\`\`\`${lang}\n`;
    return `${lead}\n\n\`\`\`${lang}\n`;
  });
  work = work.replace(/([^\n])\n(```[a-zA-Z][\w+-]*\s*$)/gm, "$1\n\n$2");
  return work.replace(/\n{3,}/g, "\n\n");
}

function normalizeInlineDiagramFences(text) {
  return normalizeInlineCodeFences(text);
}

const FLOW_DEF_LINE_RE =
  /^[a-zA-Z][\w]*=>(?:start|end|operation|condition|inputoutput|subroutine):/;
const FLOW_LINK_LINE_RE = /^[a-zA-Z][\w]*(?:\([^)]*\))?->/;
const DIAGRAM_TITLE_LINE_RE = /^Title:\s*.+/i;
const SEQ_META_LINE_RE = /^(?:Title:|participant\s+|note\s+(?:left|right|over)\s+)/i;
const SEQ_ARROW_LINE_RE = /^[^\n]+?(?:->>|-->|-+>)[^\n]+?:/;
const SEQ_SECTION_LINE_RE = /^-{3,}(?:\s*[^\n-].*?\s*)?-{3,}$|^-{3,}$/;

function isSequenceDiagramContentLine(trimmed) {
  if (SEQ_SECTION_LINE_RE.test(trimmed)) {
    const inner = trimmed.match(/^-{3,}\s*(.+?)\s*-{3,}$/);
    return Boolean(inner && inner[1].trim());
  }
  return SEQ_META_LINE_RE.test(trimmed) || SEQ_ARROW_LINE_RE.test(trimmed);
}

function isFlowLabelContinuationLine(line, previousLines) {
  const trimmed = String(line || "").trim();
  if (!trimmed) return false;
  if (
    DIAGRAM_TITLE_LINE_RE.test(trimmed) ||
    FLOW_DEF_LINE_RE.test(trimmed) ||
    FLOW_LINK_LINE_RE.test(trimmed)
  ) {
    return false;
  }
  if (/^[-*+]\s/.test(trimmed) || /^#{1,6}\s/.test(trimmed) || /^\d+\.\s/.test(trimmed)) {
    return false;
  }
  const prev = [];
  for (let i = previousLines.length - 1; i >= 0; i -= 1) {
    const value = String(previousLines[i] || "").trim();
    if (value) prev.push(value);
    if (prev.length >= 8) break;
  }
  if (!prev.length) return false;
  if (FLOW_DEF_LINE_RE.test(prev[0])) return true;
  for (const value of prev) {
    if (FLOW_LINK_LINE_RE.test(value) || DIAGRAM_TITLE_LINE_RE.test(value)) return false;
    if (FLOW_DEF_LINE_RE.test(value)) return true;
  }
  return !FLOW_LINK_LINE_RE.test(prev[0]) && !DIAGRAM_TITLE_LINE_RE.test(prev[0]);
}

function isMermaidContentLine(line) {
  const trimmed = String(line || "").trim();
  if (!trimmed) return true;
  if (/^[-*+]\s/.test(trimmed) || /^#{1,6}\s/.test(trimmed)) return false;
  return true;
}

function isDiagramContentLine(line, kind, previousLines = []) {
  const trimmed = String(line || "").trim();
  if (!trimmed) return true;
  if (/^[-*+]\s/.test(trimmed) || /^#{1,6}\s/.test(trimmed)) return false;
  if (kind === "mermaid") return isMermaidContentLine(line);
  if (kind === "flow") {
    if (
      DIAGRAM_TITLE_LINE_RE.test(trimmed) ||
      FLOW_DEF_LINE_RE.test(trimmed) ||
      FLOW_LINK_LINE_RE.test(trimmed)
    ) {
      return true;
    }
    return isFlowLabelContinuationLine(line, previousLines);
  }
  return isSequenceDiagramContentLine(trimmed);
}

function repairDiagramMarkdown(text) {
  if (!text || !/```(?:mermaid|flow|sequence)/i.test(text)) return text;
  const lines = text.split("\n");
  const out = [];
  let inDiagram = false;
  let diagramKind = null;
  let diagramLines = [];

  const closeDiagram = () => {
    if (!inDiagram) return;
    out.push("```");
    inDiagram = false;
    diagramKind = null;
    diagramLines = [];
  };

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const trimmed = line.trim();
    const inlineOpen = line.match(/^(.*)```(mermaid|flow|sequence)\s*$/i);
    const openMatch = trimmed.match(/^```(mermaid|flow|sequence)\s*$/i);
    const isClose = /^```\s*$/.test(trimmed);
    const isHeading = /^#{1,6}\s+/.test(trimmed);

    if (inlineOpen && !openMatch && !inDiagram) {
      const lead = inlineOpen[1].replace(/\s+$/, "");
      const kind = inlineOpen[2].toLowerCase();
      if (lead) out.push(lead);
      out.push(`\`\`\`${kind}`);
      inDiagram = true;
      diagramKind = kind;
      diagramLines = [];
      continue;
    }

    if (openMatch) {
      const kind = openMatch[1].toLowerCase();
      if (inDiagram && out[out.length - 1]?.trim() === trimmed) {
        continue;
      }
      if (inDiagram) closeDiagram();
      out.push(`\`\`\`${kind}`);
      inDiagram = true;
      diagramKind = kind;
      diagramLines = [];
      continue;
    }

    if (isClose) {
      if (inDiagram) closeDiagram();
      else out.push(line);
      continue;
    }

    if (inDiagram) {
      if (isHeading) {
        closeDiagram();
        out.push(line);
        continue;
      }
      if (!isDiagramContentLine(line, diagramKind, diagramLines)) {
        closeDiagram();
        out.push(line);
        continue;
      }
      diagramLines.push(line);
    }

    out.push(line);
  }

  closeDiagram();
  return out.join("\n");
}

function scanCodeFenceState(text) {
  let open = false;
  let kind = null;
  for (const line of String(text || "").split("\n")) {
    const trimmed = line.trim();
    const openMatch = trimmed.match(/^```(\w*)\s*$/i);
    if (!open && openMatch) {
      open = true;
      kind = (openMatch[1] || "").toLowerCase() || null;
      continue;
    }
    if (open && /^```\s*$/.test(trimmed)) {
      open = false;
      kind = null;
    }
  }
  return { open, kind };
}

function scanDiagramFenceState(text) {
  return scanCodeFenceState(text);
}

function closeUnclosedCodeFences(text) {
  if (!text) return text;
  const state = scanCodeFenceState(text);
  if (!state.open) return text;
  return `${text.replace(/\s*$/, "")}\n\`\`\`\n`;
}

function closeUnclosedDiagramFences(text) {
  return closeUnclosedCodeFences(text);
}

function peekUnfencedDiagramKind(lines, start) {
  for (let i = start; i < lines.length; i += 1) {
    const trimmed = String(lines[i] || "").trim();
    if (!trimmed || /^```/.test(trimmed)) break;
    if (FLOW_DEF_LINE_RE.test(trimmed) || FLOW_LINK_LINE_RE.test(trimmed)) return "flow";
    if (
      SEQ_ARROW_LINE_RE.test(trimmed) ||
      /^participant\s+/i.test(trimmed) ||
      SEQ_SECTION_LINE_RE.test(trimmed)
    ) {
      return "sequence";
    }
    if (DIAGRAM_TITLE_LINE_RE.test(trimmed)) continue;
    break;
  }
  return null;
}

function wrapUnfencedDiagramBlocks(work) {
  if (window.__USER__?.expression_extension_enabled !== true) return work;
  if (scanDiagramFenceState(work).open) return work;
  const lines = work.split("\n");
  const out = [];
  let i = 0;
  let inFence = false;

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (/^```/.test(trimmed)) {
      inFence = !inFence;
      out.push(line);
      i += 1;
      continue;
    }
    if (inFence) {
      out.push(line);
      i += 1;
      continue;
    }

    const isFlow = FLOW_DEF_LINE_RE.test(line) || FLOW_LINK_LINE_RE.test(line);
    const isSeq =
      isSequenceDiagramContentLine(trimmed) &&
      !FLOW_DEF_LINE_RE.test(line) &&
      !FLOW_LINK_LINE_RE.test(line);
    if (!isFlow && !isSeq) {
      out.push(line);
      i += 1;
      continue;
    }

    let kind = isFlow ? "flow" : "sequence";
    if (DIAGRAM_TITLE_LINE_RE.test(trimmed) && !isFlow) {
      kind = peekUnfencedDiagramKind(lines, i) || "sequence";
    }
    const matchLine = (value) => {
      const current = String(value || "").trim();
      if (kind === "flow") {
        return (
          DIAGRAM_TITLE_LINE_RE.test(current) ||
          FLOW_DEF_LINE_RE.test(current) ||
          FLOW_LINK_LINE_RE.test(current)
        );
      }
      return isSequenceDiagramContentLine(current);
    };

    const chunk = [];
    let j = i;
    while (j < lines.length) {
      const current = lines[j];
      if (/^```/.test(current.trim())) break;
      if (current.trim() === "") {
        const next = chunk.length && j + 1 < lines.length ? lines[j + 1] : "";
        if (
          next &&
          (matchLine(next) || (kind === "flow" && isFlowLabelContinuationLine(next, chunk)))
        ) {
          j += 1;
          continue;
        }
        break;
      }
      if (
        !matchLine(current) &&
        !(kind === "flow" && isFlowLabelContinuationLine(current, chunk))
      ) {
        break;
      }
      chunk.push(current);
      j += 1;
    }

    if (chunk.length) {
      if (kind === "sequence") {
        const hasArrow = chunk.some((row) => SEQ_ARROW_LINE_RE.test(String(row || "").trim()));
        if (!hasArrow) {
          out.push(line);
          i += 1;
          continue;
        }
      }
      out.push("```" + kind);
      out.push(...chunk);
      out.push("```");
      i = j;
      continue;
    }

    out.push(line);
    i += 1;
  }

  return out.join("\n");
}

function protectMarkdownFences(text) {
  const fences = [];
  let work = text.replace(/```[\s\S]*?```/g, (block) => {
    const token = `\x00FENCE${fences.length}\x00`;
    fences.push(block);
    return token;
  });
  work = work.replace(/```(\w*)\s*\r?\n([\s\S]*)$/i, (block) => {
    const token = `\x00FENCE${fences.length}\x00`;
    fences.push(block);
    return token;
  });
  return { work, fences };
}

function restoreMarkdownFences(work, fences) {
  let out = work;
  fences.forEach((block, index) => {
    out = out.replace(`\x00FENCE${index}\x00`, () => block);
  });
  return out;
}

function normalizeDecimalSpacing(text) {
  return text.replace(/(\d)\.\s+(\d)/g, "$1.$2");
}

function collapseDotSpacedInString(text) {
  if (!text || !text.includes(". ")) return text;
  let out = text.replace(/(?<=[a-z0-9_-])\. (?=[a-z0-9])/gi, ".");
  out = out.replace(/(?<=\\)\. (?=[a-zA-Z0-9_$\\])/g, ".");
  out = out.replace(/(?<=%)\. (?=[a-zA-Z0-9_\\])/g, ".");
  return out;
}

function collapseDotSpacedCodeFence(block) {
  if (!block || !block.startsWith("```") || !block.includes(". ")) return block;
  const close = block.lastIndexOf("```");
  if (close <= 3) return collapseDotSpacedInString(block);
  const headEnd = block.indexOf("\n");
  if (headEnd < 0) return collapseDotSpacedInString(block);
  const head = block.slice(0, headEnd + 1);
  const body = block.slice(headEnd + 1, close);
  const tail = block.slice(close);
  return head + collapseDotSpacedInString(body) + tail;
}

function collapseDotSpacedLiterals(text) {
  if (!text || !text.includes(". ")) return text;
  const { work, fences } = protectMarkdownFences(text);
  const collapsedFences = fences.map(collapseDotSpacedCodeFence);
  const inlineSlots = [];
  let body = work.replace(/`[^`\n]+`/g, (span) => {
    const token = `\x00INLINE${inlineSlots.length}\x00`;
    inlineSlots.push("`" + collapseDotSpacedInString(span.slice(1, -1)) + "`");
    return token;
  });
  body = collapseDotSpacedInString(body);
  inlineSlots.forEach((fixed, index) => {
    body = body.replace(`\x00INLINE${index}\x00`, () => fixed);
  });
  return restoreMarkdownFences(body, collapsedFences);
}

function splitMarkdownTableRow(line) {
  const trimmed = line.trim();
  if (!trimmed.includes("|")) return line;
  const rowRe = /\|(?:[^|\n]+?\|)+/g;
  const rows = trimmed.match(rowRe);
  if (!rows || rows.length <= 1) return line;
  const normalized = rows.map((row) => row.trim());
  const pipeCounts = normalized.map((row) => (row.match(/\|/g) || []).length);
  if (!pipeCounts.every((count) => count >= 2)) return line;
  const hasSeparator = normalized.some((row) => /---/.test(row));
  if (!hasSeparator && rows.length < 2) return line;
  const looksLikeGluedRows = pipeCounts.every((count) => count >= 3);
  if (hasSeparator || looksLikeGluedRows) {
    return normalized.join("\n");
  }
  return line;
}

function normalizeMarkdownTables(text) {
  if (!text) return text;
  const { work: protectedText, fences } = protectMarkdownFences(text);
  let work = normalizeDecimalSpacing(protectedText);

  work = work.replace(
    /([。．!?！？:：])[ \t]*(?=\|[^\n]+\|)/g,
    "$1\n\n"
  );

  work = work
    .split("\n")
    .map((line) => splitMarkdownTableRow(line))
    .join("\n");

  return restoreMarkdownFences(work, fences);
}

const LIST_LINE_RE = /^\s*(?:[-*+]|\d{1,3}\.)\s+/;
const BLOCK_START_RE = /^\s*(?:#{1,6}\s+|>\s*|```)/;

function normalizeMarkdownIndent(text) {
  const { work, fences } = protectMarkdownFences(text);
  const normalized = work.replace(/^\t+/gm, (tabs) => "    ".repeat(tabs.length));
  return restoreMarkdownFences(normalized, fences);
}

function normalizeMarkdownLists(text) {
  const { work, fences } = protectMarkdownFences(text);
  const lines = work.split("\n");
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!LIST_LINE_RE.test(line)) {
      out.push(line);
      continue;
    }
    const prev = out[out.length - 1];
    if (!prev || prev.trim() === "") {
      out.push(line);
      continue;
    }
    if (LIST_LINE_RE.test(prev) || BLOCK_START_RE.test(prev)) {
      out.push(line);
      continue;
    }
    out.push("");
    out.push(line);
  }
  return restoreMarkdownFences(out.join("\n"), fences);
}

function normalizeMarkdownBlockBreaks(text) {
  if (!text) return text;
  const { work: protectedText, fences } = protectMarkdownFences(text);
  let work = protectedText;

  work = work.replace(/([^\n#])[ \t]+(#{1,6}\s+)/g, "$1\n\n$2");
  work = work.replace(/([。．!?！？:：])[ \t]*(#{1,6}\s+)/g, "$1\n\n$2");

  work = work.replace(/([。．!?！？\n])[ \t]*(\n-{3,}\s*(?=\n|$))/g, "$1\n\n$2");
  work = work.replace(/([^\n-*])[ \t]+(\n-{3,}\s*(?=\n|$))/g, "$1\n\n$2");

  work = work.replace(/([。．!?！？\n])[ \t]*(-\s+(?![\[(]))/g, "$1\n\n$2");
  work = work.replace(/([。．!?！？\n])[ \t]*([*+]\s+)/g, "$1\n\n$2");
  work = work.replace(/([。．!?！？\n])[ \t]*((?:\d{1,3})\.\s+)/g, "$1\n\n$2");

  work = work.replace(/([。．!?！？\n])[ \t]*(>\s+)/g, "$1\n\n$2");

  return restoreMarkdownFences(work, fences);
}

const INLINE_SOURCE_CITATION_NEXT_RE = /）\s*（(?=\[[^\]]+\]\()/g;
const INLINE_SOURCE_CITATION_AFTER_PUNCT_RE =
  /([。．!?！？:：])\s*（(?=\[[^\]]+\]\()/g;
const INLINE_SOURCE_CITATION_AFTER_TEXT_RE =
  /([^\n\s])\s+（(?=\[[^\]]+\]\()/g;

function isMarkdownTableLine(line) {
  const trimmed = (line || "").trim();
  return trimmed.startsWith("|") && trimmed.includes("|");
}

function splitInlineSourceCitationsInLine(line) {
  if (!line || !line.includes("（[")) return line;
  const joiner = isMarkdownTableLine(line) ? "<br>" : "\n";
  let out = line.replace(INLINE_SOURCE_CITATION_NEXT_RE, `）${joiner}（`);
  if (!isMarkdownTableLine(line)) {
    out = out
      .replace(INLINE_SOURCE_CITATION_AFTER_PUNCT_RE, "$1\n（")
      .replace(INLINE_SOURCE_CITATION_AFTER_TEXT_RE, "$1\n（");
  }
  return out;
}

function normalizeInlineSourceCitations(text) {
  if (!text || !text.includes("（[")) return text;
  const { work, fences } = protectMarkdownFences(text);
  const out = work
    .split("\n")
    .map((line) => splitInlineSourceCitationsInLine(line))
    .join("\n");
  return restoreMarkdownFences(out, fences);
}

function normalizeHorizontalRules(text) {
  if (!text) return text;
  const { work, fences } = protectMarkdownFences(text);
  const hrOnly = /^(-{3,}|\*{3,}|_{3,})$/;
  const lines = work.split("\n");
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.includes("|") && /^\s*\|?.+\|/.test(line)) {
      out.push(line);
      continue;
    }
    const inline = line.match(/^(.*?)[ \t]+(-{3,}|\*{3,}|_{3,})\s*$/);
    if (inline && inline[1].trim()) {
      out.push(inline[1].trimEnd());
      out.push("");
      out.push(inline[2]);
      continue;
    }
    const trimmed = line.trim();
    if (hrOnly.test(trimmed)) {
      if (out.length && out[out.length - 1].trim() !== "") out.push("");
      out.push(trimmed);
      if (i + 1 < lines.length && lines[i + 1].trim() !== "") out.push("");
      continue;
    }
    out.push(line);
  }
  return restoreMarkdownFences(out.join("\n"), fences);
}

function prepareDiagramMarkdown(text, { streaming = false } = {}) {
  if (!text) return text;
  let work = streaming ? text : repairDiagramMarkdown(text);
  if (!streaming) {
    work = closeUnclosedDiagramFences(work);
  }
  if (!streaming && !scanDiagramFenceState(work).open) {
    work = wrapUnfencedDiagramBlocks(work);
  }
  return work;
}

function polishAssistantMarkdown(text, options = {}) {
  if (!text) return text;
  const streaming = options.streaming === true;
  let work = normalizeInlineCodeFences(text);
  work = prepareDiagramMarkdown(work, { streaming });
  const { work: fenced, fences } = protectMarkdownFences(work);
  let out = normalizeLooseLatexMath(fenced);
  out = repairBrokenInlineLinks(out);
  out = normalizeInlineSourceCitations(out);
  out = restoreMarkdownFences(out, fences);
  out = collapseDotSpacedLiterals(out);
  out = normalizeMultilineMarkdownLinks(out);
  out = normalizeMarkdownIndent(out);
  out = normalizeMarkdownLists(out);
  out = normalizeMarkdownBlockBreaks(out);
  out = normalizeHorizontalRules(out);
  out = normalizeMarkdownTables(out);
  out = normalizeUrlLikeStrings(out);
  out = normalizeMarkdownImages(out);
  out = dedupeMarkdownImages(out);
  const model = window.getSelectedModel?.();
  const profile = model?.agent_profile || "deepseek";
  if (profile === "deepseek") {
    return out.replace(/\n{3,}/g, "\n\n").trim();
  }
  out = out.replace(/\s*\[\d+\](?:\[\d+\])*/g, "");
  out = out.replace(/\n{3,}/g, "\n\n");
  return out.trim();
}

const MARKDOWN_HTML_CACHE = new Map();
const MARKDOWN_CACHE_MAX = 256;
let markedConfigured = false;

function markdownCacheKey(text, options = {}) {
  const model = window.getSelectedModel?.();
  const profile = model?.agent_profile || "deepseek";
  const ext = window.__USER__?.expression_extension_enabled === true ? "1" : "0";
  const streaming = options.streaming === true ? "s" : "f";
  return `${ext}|${profile}|${streaming}|${text}`;
}

function bumpMarkdownGeneration(element) {
  if (!element) return 0;
  const next = (parseInt(element.dataset.markdownGeneration, 10) || 0) + 1;
  element.dataset.markdownGeneration = String(next);
  return next;
}

function sanitizeMarkdownHtml(html) {
  if (typeof DOMPurify === "undefined") {
    return escapeHtml(String(html || "").replace(/<[^>]*>/g, ""));
  }
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    ADD_ATTR: ["target", "rel", "class", "style", "aria-hidden", "xmlns", "viewBox"],
    ADD_TAGS: [
      "math",
      "semantics",
      "mrow",
      "mi",
      "mo",
      "mn",
      "msup",
      "msub",
      "mfrac",
      "annotation",
    ],
  });
}

function splitDiagramMarkdownParts(polished) {
  if (!polished || !/```(?:mermaid|flow|sequence)/i.test(polished)) {
    return [{ kind: "markdown", text: polished || "" }];
  }
  const parts = [];
  const re = /```(mermaid|flow|sequence)\s*\r?\n([\s\S]*?)```/gi;
  let last = 0;
  let match;
  while ((match = re.exec(polished)) !== null) {
    if (match.index > last) {
      const chunk = polished.slice(last, match.index);
      if (chunk.trim()) parts.push({ kind: "markdown", text: chunk });
    }
    parts.push({
      kind: String(match[1] || "").toLowerCase(),
      source: String(match[2] || "").replace(/\n$/, ""),
    });
    last = match.index + match[0].length;
  }
  if (last < polished.length) {
    const tail = polished.slice(last);
    if (tail.trim()) parts.push({ kind: "markdown", text: tail });
  }
  if (!parts.length) parts.push({ kind: "markdown", text: polished });
  return parts;
}

function buildMarkdownHtmlWithDiagramSlots(polished, options = {}) {
  const streaming = options.streaming === true;
  return splitDiagramMarkdownParts(polished)
    .map((part) => {
      if (part.kind === "markdown") {
        return renderPolishedMarkdown(part.text);
      }
      if (
        streaming &&
        window.isClosedDiagramSource &&
        !window.isClosedDiagramSource(part.source, part.kind, polished)
      ) {
        return renderPolishedMarkdown(
          "```" + part.kind + "\n" + part.source + "\n```"
        );
      }
      const diagramReady =
        window.isDiagramSourceReady && window.isDiagramSourceReady(part.kind, part.source);
      if (!diagramReady) {
        return renderPolishedMarkdown(
          "```" + part.kind + "\n" + part.source + "\n```"
        );
      }
      const enc = window.encodeDiagramSource
        ? window.encodeDiagramSource(part.source || "")
        : encodeURIComponent(part.source || "");
      return (
        `<div class="md-diagram md-diagram-${part.kind}" data-diagram-kind="${part.kind}">` +
        `<div class="md-diagram-inner" data-diagram-source="${enc}"></div></div>`
      );
    })
    .join("");
}

async function renderMarkdownDiagrams(element, polished, options = {}) {
  if (!element) return;
  const diagramOptions = {
    ...options,
    generation: options.generation,
    root: options.root || element,
  };
  if (window.hydrateDiagramPlaceholders) {
    await window.hydrateDiagramPlaceholders(element, diagramOptions);
  }
  if (window.enhanceDiagramBlocksInElement) {
    await window.enhanceDiagramBlocksInElement(element, polished, diagramOptions);
  }
}

function ensureMarkedConfigured() {
  if (markedConfigured || typeof marked === "undefined") return;
  const options = {
    gfm: true,
    breaks: true,
    headerIds: false,
    mangle: false,
  };
  if (typeof marked.use === "function") {
    marked.use(options);
  } else if (typeof marked.setOptions === "function") {
    marked.setOptions(options);
  }
  markedConfigured = true;
}

function renderPolishedMarkdown(polished) {
  if (!polished) return "";
  if (typeof marked === "undefined") {
    return escapeHtml(polished);
  }
  const mathParts = window.protectMathSegments?.(polished) || { work: polished, segments: [] };
  ensureMarkedConfigured();
  let html = sanitizeMarkdownHtml(marked.parse(mathParts.work));
  if (mathParts.segments.length && window.injectRenderedMath) {
    html = window.injectRenderedMath(html, mathParts.segments);
    html = sanitizeMarkdownHtml(html);
  }
  return html;
}

function buildAssistantMarkdownHtml(text, options = {}) {
  const source = polishAssistantMarkdown(text, options);
  if (/```(?:mermaid|flow|sequence)/i.test(source)) {
    return buildMarkdownHtmlWithDiagramSlots(source, options);
  }
  return renderPolishedMarkdown(source);
}

function renderMarkdown(text, options = {}) {
  if (!text) return "";
  if (typeof marked === "undefined") {
    return escapeHtml(text);
  }

  const cacheKey = options.streaming ? null : markdownCacheKey(text, options);
  if (cacheKey) {
    const cached = MARKDOWN_HTML_CACHE.get(cacheKey);
    if (cached !== undefined) return cached;
  }

  const html = buildAssistantMarkdownHtml(text, options);

  if (cacheKey) {
    if (MARKDOWN_HTML_CACHE.size >= MARKDOWN_CACHE_MAX) {
      const oldest = MARKDOWN_HTML_CACHE.keys().next().value;
      MARKDOWN_HTML_CACHE.delete(oldest);
    }
    MARKDOWN_HTML_CACHE.set(cacheKey, html);
  }
  return html;
}

let streamMdJob = null;
let streamMdRaf = 0;
let streamApplyChain = Promise.resolve();

function cancelStreamingMarkdown(element) {
  if (streamMdRaf) {
    cancelAnimationFrame(streamMdRaf);
    streamMdRaf = 0;
  }
  if (element) {
    if (streamMdJob?.element === element) streamMdJob = null;
    bumpMarkdownGeneration(element);
  } else {
    streamMdJob = null;
  }
}

function scheduleStreamingMarkdown(element, markdownText) {
  if (!element) return;
  streamMdJob = { element, markdownText: markdownText || "" };
  if (streamMdRaf) return;
  const tick = () => {
    streamMdRaf = 0;
    const job = streamMdJob;
    if (!job?.element) return;
    const el = job.element;
    const textAtRender = job.markdownText;
    streamApplyChain = streamApplyChain.then(async () => {
      if (streamMdJob?.element !== el || streamMdJob?.markdownText !== textAtRender) return;
      await applyMarkdownContent(el, textAtRender, { streaming: true });
      window._onStreamingMarkdownApplied?.();
      if (
        streamMdJob &&
        streamMdJob.element === el &&
        streamMdJob.markdownText !== textAtRender
      ) {
        streamMdRaf = requestAnimationFrame(tick);
      } else if (streamMdJob?.element === el) {
        streamMdJob = null;
      }
    });
  };
  streamMdRaf = requestAnimationFrame(tick);
}

function flushStreamingMarkdown() {
  if (streamMdRaf) {
    cancelAnimationFrame(streamMdRaf);
    streamMdRaf = 0;
  }
  const job = streamMdJob;
  streamMdJob = null;
  if (job?.element) {
    void applyMarkdownContent(job.element, job.markdownText || "", { finalize: true });
  }
}

function normalizeUserMessageContent(content) {
  if (Array.isArray(content)) return content;
  if (typeof content !== "string") return content;
  const trimmed = content.trim();
  if (!trimmed.startsWith("[")) return content;
  try {
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed)) return parsed;
  } catch (_) {}
  return content;
}

function populateUserMessageContent(container, content) {
  if (!container) return;
  container.innerHTML = "";
  const parts = normalizeUserMessageContent(content);
  if (typeof parts === "string") {
    if (!parts) return;
    container.innerHTML = escapeHtml(parts).replace(/\n/g, "<br>");
    return;
  }
  if (!Array.isArray(parts)) {
    container.textContent = String(parts ?? "");
    return;
  }
  for (const part of parts) {
    if (!part || typeof part !== "object") continue;
    if (part.type === "text") {
      const text = String(part.text || "");
      if (!text.trim()) continue;
      const div = document.createElement("div");
      div.className = "message-user-text";
      div.innerHTML = escapeHtml(text).replace(/\n/g, "<br>");
      container.appendChild(div);
      continue;
    }
    if (part.type === "image_url") {
      const url = part.image_url?.url || "";
      if (!url) continue;
      const fig = document.createElement("figure");
      fig.className = "message-user-image";
      const img = document.createElement("img");
      img.src = url;
      img.alt = "";
      img.loading = "lazy";
      fig.appendChild(img);
      container.appendChild(fig);
      continue;
    }
    if (part.type === "pdf_url") {
      const label = document.createElement("p");
      label.className = "message-user-attachment-label";
      label.textContent = "[PDF 添付]";
      container.appendChild(label);
    }
  }
  window.enhanceChatImagesInElement?.(container);
}

function formatUserMessageHtml(content) {
  const wrap = document.createElement("div");
  populateUserMessageContent(wrap, content);
  return wrap.innerHTML;
}

window.normalizeUserMessageContent = normalizeUserMessageContent;
window.populateUserMessageContent = populateUserMessageContent;

function formatMessageHtml(role, content) {
  if (role === "assistant") {
    return renderMarkdown(content);
  }
  return formatUserMessageHtml(content);
}

const CODE_COPY_ICON =
  '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z"/></svg>';

function codeCopyLabel() {
  return window.t?.("codeCopyLabel") || "コードをコピー";
}

function codeCopiedLabel() {
  return window.t?.("codeCopiedLabel") || "コピーしました";
}

function extractPreText(pre) {
  const code = pre.querySelector("code");
  const source = code || pre;
  const clone = source.cloneNode(true);
  clone.querySelectorAll(".code-copy-btn").forEach((el) => el.remove());
  return (clone.textContent ?? "").replace(/\n$/, "");
}

async function copyCodeBlockText(text, btn) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    btn.classList.add("is-copied");
    btn.setAttribute("aria-label", codeCopiedLabel());
    setTimeout(() => {
      btn.classList.remove("is-copied");
      btn.setAttribute("aria-label", codeCopyLabel());
    }, 2000);
  } catch (e) {}
}

function wrapPreWithCopyButton(pre) {
  if (!pre || pre.closest(".code-block-wrap")) return;
  const code = pre.querySelector("code");
  if (code && /\blanguage-(mermaid|sequence|flow)\b/i.test(code.className || "")) return;
  const wrap = document.createElement("div");
  wrap.className = "code-block-wrap";
  pre.parentNode.insertBefore(wrap, pre);
  wrap.appendChild(pre);
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "code-copy-btn";
  btn.setAttribute("aria-label", codeCopyLabel());
  btn.innerHTML = CODE_COPY_ICON;
  btn.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    void copyCodeBlockText(extractPreText(pre), btn);
  });
  wrap.appendChild(btn);
}

function enhanceCodeBlocksInElement(root) {
  if (!root) return;
  root.querySelectorAll("pre").forEach(wrapPreWithCopyButton);
}

function enhanceMarkdownTablesInElement(root) {
  if (!root) return;
  root.querySelectorAll("table").forEach((table) => {
    let wrap = table.closest(".md-table-wrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "md-table-wrap";
      const inner = document.createElement("div");
      inner.className = "md-table-inner";
      table.parentNode.insertBefore(wrap, table);
      inner.appendChild(table);
      wrap.appendChild(inner);
      const message = wrap.closest(".message.assistant");
      if (message) message.classList.add("message-has-table");
    }
    if (typeof window.ensureTableExportButtons === "function") {
      window.ensureTableExportButtons(wrap, table);
    }
  });
}

function enhanceMarkdownLinksInElement(root) {
  if (!root) return;
  root.querySelectorAll("a[href]").forEach((a) => {
    const href = a.getAttribute("href") || "";
    if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) {
      return;
    }
    if (a.target && a.target !== "_self") return;
    try {
      const url = new URL(href, location.origin);
      if (url.origin === location.origin) return;
    } catch (_) {
      return;
    }
    a.target = "_blank";
    a.rel = "noopener noreferrer";
  });
}

async function enhanceMarkdownBodyElement(root, fullMarkdown = "", options = {}) {
  enhanceCodeBlocksInElement(root);
  enhanceMarkdownTablesInElement(root);
  enhanceMarkdownLinksInElement(root);
  if (window.enhanceDiagramBlocksInElement) {
    await window.enhanceDiagramBlocksInElement(root, fullMarkdown, options);
  }
}

async function applyMarkdownContent(element, markdownText, options = {}) {
  if (!element) return;
  const finalize = options.finalize === true;
  const renderOptions = finalize ? { ...options, streaming: false } : options;
  const generation =
    renderOptions.streaming && !finalize
      ? parseInt(element.dataset.markdownGeneration, 10) || bumpMarkdownGeneration(element)
      : bumpMarkdownGeneration(element);
  const text = markdownText || "";
  const polished = polishAssistantMarkdown(text, renderOptions);
  element.innerHTML = buildMarkdownHtmlWithDiagramSlots(polished, renderOptions);
  enhanceCodeBlocksInElement(element);
  enhanceMarkdownTablesInElement(element);
  enhanceMarkdownLinksInElement(element);
  await renderMarkdownDiagrams(element, polished, {
    ...renderOptions,
    generation,
    root: element,
  });
}

window.enhanceCodeBlocksInElement = enhanceCodeBlocksInElement;
window.enhanceMarkdownTablesInElement = enhanceMarkdownTablesInElement;
window.enhanceMarkdownBodyElement = enhanceMarkdownBodyElement;
window.applyMarkdownContent = applyMarkdownContent;
window.renderMarkdown = renderMarkdown;
window.scheduleStreamingMarkdown = scheduleStreamingMarkdown;
window.cancelStreamingMarkdown = cancelStreamingMarkdown;
window.flushStreamingMarkdown = flushStreamingMarkdown;
window.bumpMarkdownGeneration = bumpMarkdownGeneration;
window.stripOtherGeneratedImageMarkdown = stripOtherGeneratedImageMarkdown;
