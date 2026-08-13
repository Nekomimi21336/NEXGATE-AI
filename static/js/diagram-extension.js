(function () {
  function diagramAssetUrl(file) {
    const base = window.__STATIC_JS_BASE__ || "/static/js/";
    const normalized = base.endsWith("/") ? base : `${base}/`;
    return `${normalized}vendor/diagram/${file}`;
  }

  const MERMAID_SCRIPT = diagramAssetUrl("mermaid.min.js");

  let libsPromise = null;
  let mermaidInitialized = false;
  let mermaidRenderCounter = 0;
  const diagramSvgCacheByRoot = new WeakMap();

  function diagramCacheKey(kind, source) {
    return `${kind}|${source}`;
  }

  function getRootDiagramCache(root) {
    if (!root) return null;
    let cache = diagramSvgCacheByRoot.get(root);
    if (!cache) {
      cache = new Map();
      diagramSvgCacheByRoot.set(root, cache);
    }
    return cache;
  }

  function storeDiagramCache(root, kind, source, inner) {
    const cache = getRootDiagramCache(root);
    if (!cache || !inner) return;
    const wrap = inner.closest(".md-diagram");
    cache.set(diagramCacheKey(kind, source), {
      innerHTML: inner.innerHTML,
      diagramKind: wrap?.dataset?.diagramKind || kind,
      wrapClassName: wrap?.className || "",
    });
  }

  function restoreDiagramCache(root, inner, kind, source) {
    const cache = getRootDiagramCache(root);
    const cached = cache?.get(diagramCacheKey(kind, source));
    if (!cached?.innerHTML) return false;
    inner.innerHTML = cached.innerHTML;
    const wrap = inner.closest(".md-diagram");
    if (wrap) {
      if (cached.wrapClassName) wrap.className = cached.wrapClassName;
      if (cached.diagramKind) wrap.dataset.diagramKind = cached.diagramKind;
      markMessageHasDiagram(wrap);
      ensureDiagramDownloadButton(wrap);
    }
    inner.dataset.diagramReady = "1";
    inner.dataset.diagramLoading = "0";
    inner.removeAttribute("data-diagram-source");
    return true;
  }
  let mermaidRenderQueue = Promise.resolve();
  let mermaidThemeObserverBound = false;

  const DIAGRAM_FONT =
    'ui-sans-serif, system-ui, -apple-system, "Segoe UI", "Hiragino Sans", "Noto Sans JP", sans-serif';

  const FLOW_DEF_RE =
    /^[a-zA-Z][\w]*=>(?:start|end|operation|condition|inputoutput|subroutine):/;
  const FLOW_LINK_RE = /^[a-zA-Z][\w]*(?:\([^)]*\))?->/;
  const DIAGRAM_TITLE_RE = /^Title:\s*(.+)$/i;
  const SEQ_LINE_RE =
    /^(?:Title:|participant\s+|note\s+(?:left|right|over)\s+|[^\n]+?(?:->>|-->|-+>)[^\n]+?:)/i;
  const SEQ_SECTION_LINE_RE = /^-{3,}(?:\s*[^\n-].*?\s*)?-{3,}$|^-{3,}$/;
  const MERMAID_HEAD_RE =
    /^(?:flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|erDiagram|gantt|pie(?:\s+showData)?|mindmap|timeline|gitGraph|journey|quadrantChart|requirementDiagram|sankey-beta|xychart-beta|block-beta|architecture-beta|kanban|C4Context|C4Container|C4Component|C4Dynamic|C4Deployment|packet-beta|radar)\b/i;

  function stripMermaidFrontmatter(text) {
    return String(text || "")
      .replace(/^---[\s\S]*?\r?\n---\s*(?:\r?\n)?/m, "")
      .trim();
  }

  function mermaidDiagramBody(source) {
    return stripMermaidFrontmatter(String(source || "").trim());
  }

  function diagramLibrariesReady() {
    return typeof mermaid !== "undefined";
  }

  function loadScript(url) {
    return new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[data-diagram-src="${url}"]`);
      if (existing) {
        if (existing.dataset.loaded === "1") resolve();
        else existing.addEventListener("load", () => resolve(), { once: true });
        return;
      }
      const el = document.createElement("script");
      el.src = url;
      el.async = false;
      el.dataset.diagramSrc = url;
      el.onload = () => {
        el.dataset.loaded = "1";
        resolve();
      };
      el.onerror = () => reject(new Error(`diagram script failed: ${url}`));
      document.head.appendChild(el);
    });
  }

  function loadDiagramLibraries() {
    if (libsPromise) return libsPromise;
    if (diagramLibrariesReady()) {
      libsPromise = Promise.resolve();
      return libsPromise;
    }
    libsPromise = loadScript(MERMAID_SCRIPT);
    return libsPromise;
  }

  let diagramColorProbe = null;

  function getDiagramColorProbe() {
    if (!diagramColorProbe && document.documentElement) {
      diagramColorProbe = document.createElement("div");
      diagramColorProbe.setAttribute("aria-hidden", "true");
      diagramColorProbe.style.cssText =
        "position:absolute;left:-9999px;top:-9999px;width:0;height:0;opacity:0;pointer-events:none;";
      document.documentElement.appendChild(diagramColorProbe);
    }
    return diagramColorProbe;
  }

  function isMermaidSafeColor(value) {
    const v = String(value || "").trim();
    if (!v || /color-mix|var\(/i.test(v)) return false;
    if (/^#([0-9a-f]{3,8})$/i.test(v)) return true;
    return /^rgba?\(/i.test(v);
  }

  function resolveCssColor(value, fallback) {
    const fb = String(fallback || "#000000").trim();
    const raw = String(value || "").trim();
    if (!raw) return fb;
    if (isMermaidSafeColor(raw)) return raw;

    const probe = getDiagramColorProbe();
    if (!probe) return fb;

    probe.style.backgroundColor = "";
    probe.style.backgroundColor = raw;
    let computed = getComputedStyle(probe).backgroundColor;
    if (computed && computed !== "rgba(0, 0, 0, 0)" && isMermaidSafeColor(computed)) {
      return computed;
    }

    probe.style.color = "";
    probe.style.color = raw;
    computed = getComputedStyle(probe).color;
    if (computed && isMermaidSafeColor(computed)) return computed;

    return fb;
  }

  function readDiagramCssVar(name, fallback) {
    const fb = String(fallback || "#000000").trim();
    const probe = getDiagramColorProbe();
    if (!probe) return fb;

    probe.style.backgroundColor = "";
    probe.style.backgroundColor = `var(${name}, ${fb})`;
    const computed = getComputedStyle(probe).backgroundColor;
    if (computed && computed !== "rgba(0, 0, 0, 0)" && isMermaidSafeColor(computed)) {
      return computed;
    }
    return resolveCssColor(fb, fb);
  }

  function encodeDiagramSource(source) {
    const bytes = new TextEncoder().encode(String(source || ""));
    let binary = "";
    bytes.forEach((byte) => {
      binary += String.fromCharCode(byte);
    });
    return `b64:${btoa(binary)}`;
  }

  function decodeDiagramSource(encoded) {
    const raw = String(encoded || "");
    if (raw.startsWith("b64:")) {
      try {
        const binary = atob(raw.slice(4));
        const bytes = Uint8Array.from(binary, (ch) => ch.charCodeAt(0));
        return new TextDecoder().decode(bytes);
      } catch {
        return raw.slice(4);
      }
    }
    try {
      return decodeURIComponent(raw);
    } catch {
      return raw;
    }
  }

  function enqueueMermaidRender(task) {
    const run = mermaidRenderQueue.then(task, task);
    mermaidRenderQueue = run.catch(() => {});
    return run;
  }

  function isRenderContextCurrent(renderContext, container) {
    const root = renderContext?.root;
    const generation = renderContext?.generation;
    if (!container?.isConnected) return false;
    if (root && generation != null) {
      return root.dataset.markdownGeneration === String(generation);
    }
    return true;
  }

  function splitCollapsedMermaidBody(body) {
    return String(body || "")
      .trim()
      .replace(/\s{2,}(title\s+)/gi, "\n$1")
      .replace(/\s{2,}(participant\s+)/gi, "\n$1")
      .replace(/\s{2,}(Note\s+)/gi, "\n$1")
      .replace(/\s{2,}([A-Za-z_][\w-]*\s*-->)/g, "\n$1")
      .replace(/\s{2,}([A-Za-z_][\w-]*\s*[\(\[\{\/])/g, "\n$1");
  }

  function restoreMermaidNewlines(text) {
    const headRe =
      /^(flowchart\s+(?:TB|TD|BT|RL|LR)|graph\s+(?:TB|TD|BT|RL|LR)|sequenceDiagram)/i;
    const lines = String(text || "")
      .replace(/\r\n/g, "\n")
      .split("\n");
    const out = [];

    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed) {
        out.push("");
        continue;
      }
      const head = trimmed.match(headRe);
      if (head && trimmed.length > head[0].length + 4) {
        const body = splitCollapsedMermaidBody(trimmed.slice(head[0].length));
        out.push(head[0]);
        body.split("\n").forEach((part) => {
          if (part.trim()) out.push(`    ${part.trim()}`);
        });
        continue;
      }
      if (
        /\s{3,}(title\s+|participant\s+|Note\s+|[A-Za-z_][\w-]*\s*(-->|[\(\[\{\/]))/i.test(
          trimmed
        )
      ) {
        splitCollapsedMermaidBody(trimmed)
          .split("\n")
          .forEach((part) => {
            if (part.trim()) out.push(`    ${part.trim()}`);
          });
        continue;
      }
      out.push(line);
    }
    return out.join("\n");
  }

  function yamlQuoteTitle(title) {
    const value = String(title || "").trim();
    if (!value) return '""';
    if (/[^\x00-\x7F]/.test(value) || /[:#\s]/.test(value)) {
      return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
    }
    return value;
  }

  function fixFlowchartTitle(text) {
    if (!/^\s*(flowchart|graph)\s/im.test(text)) return text;
    if (/^---[\s\S]*?\n---\s*\n/im.test(text)) return text;

    const lines = text.split("\n");
    let title = "";
    const body = [];
    for (const line of lines) {
      const match = line.match(/^\s*title\s+(.+)$/i);
      if (match && !title) {
        title = match[1].trim().replace(/^["']|["']$/g, "");
        continue;
      }
      body.push(line);
    }
    if (!title) return text;
    return `---\ntitle: ${yamlQuoteTitle(title)}\n---\n${body.join("\n")}`;
  }

  function normalizeMermaidSource(text) {
    let out = restoreMermaidNewlines(String(text || "").replace(/\r\n/g, "\n").trim());
    out = fixFlowchartTitle(out);
    return out.trim();
  }

  function unescapeDiagramLineBreaks(text) {
    const token = "\uE000";
    return String(text || "")
      .replace(/\\\\n/g, token)
      .replace(/\\n/g, "\n")
      .split(token)
      .join("\\n");
  }

  function mermaidLabel(text) {
    return unescapeDiagramLineBreaks(text)
      .replace(/"/g, "#quot;")
      .replace(/\n/g, "<br/>");
  }

  function extractDiagramTitle(source) {
    for (const line of String(source || "").split("\n")) {
      const match = String(line || "").trim().match(DIAGRAM_TITLE_RE);
      if (match) return unescapeDiagramLineBreaks(match[1].trim());
    }
    const mermaidTitle = String(source || "").match(/^\s*title\s+(.+)$/im);
    if (mermaidTitle) return mermaidTitle[1].trim();
    return "";
  }

  function isSequenceSectionLine(line) {
    return SEQ_SECTION_LINE_RE.test(String(line || "").trim());
  }

  function firstSequenceParticipant(lines) {
    for (const line of lines) {
      const arrow = String(line || "").trim().match(/^([^\-]+?)(?:->>|-->|-+>)/);
      if (arrow) return arrow[1].trim();
      const match = String(line || "").trim().match(/^participant\s+(.+)/i);
      if (match) return match[1].trim();
    }
    return "";
  }

  function normalizeFlowRow(line) {
    const trimmed = String(line || "").trim();
    if (!trimmed) return trimmed;
    if (DIAGRAM_TITLE_RE.test(trimmed)) {
      const match = trimmed.match(/^(Title:\s*)(.*)$/i);
      return match ? match[1] + unescapeDiagramLineBreaks(match[2]) : trimmed;
    }
    if (FLOW_DEF_RE.test(trimmed)) {
      const match = trimmed.match(
        /^([a-zA-Z][\w]*=>(?:start|end|operation|condition|inputoutput|subroutine):)(.*)$/
      );
      return match ? match[1] + unescapeDiagramLineBreaks(match[2]) : trimmed;
    }
    return trimmed;
  }

  function sanitizeFlowSource(source) {
    const rows = [];
    for (const raw of String(source || "").split("\n")) {
      const line = raw.trim();
      if (!line) continue;
      if (DIAGRAM_TITLE_RE.test(line)) {
        rows.push(line);
        continue;
      }
      if (FLOW_DEF_RE.test(line) || FLOW_LINK_RE.test(line)) {
        rows.push(line);
        continue;
      }
      if (!rows.length) continue;
      const last = rows[rows.length - 1];
      if (DIAGRAM_TITLE_RE.test(last) || FLOW_LINK_RE.test(last)) continue;
      rows[rows.length - 1] = `${last} ${line}`;
    }
    return rows.map(normalizeFlowRow).join("\n");
  }

  function normalizeSequenceRow(line) {
    const trimmed = String(line || "").trim();
    if (!trimmed) return trimmed;
    if (/^Title:\s*/i.test(trimmed)) {
      const match = trimmed.match(/^(Title:\s*)(.*)$/i);
      return match ? match[1] + unescapeDiagramLineBreaks(match[2]) : trimmed;
    }
    if (/^participant\s+/i.test(trimmed)) {
      const match = trimmed.match(/^(participant\s+)(.*)$/i);
      return match ? match[1] + unescapeDiagramLineBreaks(match[2]) : trimmed;
    }
    if (/^note\s+/i.test(trimmed)) {
      const match = trimmed.match(
        /^((?:note\s+(?:left|right)\s+of\s+[^:]+|note\s+over\s+[^:]+):)(.*)$/i
      );
      return match ? match[1] + unescapeDiagramLineBreaks(match[2]) : trimmed;
    }
    const arrow = trimmed.match(/^(.+?(?:->>|-->|-+>)[^:]+:)(.*)$/);
    if (arrow) return arrow[1] + unescapeDiagramLineBreaks(arrow[2]);
    return trimmed;
  }

  function isSequenceDiagramLine(line) {
    const trimmed = String(line || "").trim();
    if (!trimmed || /^[-*+]\s/.test(trimmed) || /^#{1,6}\s/.test(trimmed)) return false;
    return SEQ_LINE_RE.test(trimmed) || isSequenceSectionLine(trimmed);
  }

  function sanitizeSequenceSource(source) {
    const lines = String(source || "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    const noteTarget = firstSequenceParticipant(lines) || "participant";
    return lines
      .map((line) => {
        if (isSequenceSectionLine(line)) {
          const match = line.match(/^-{3,}\s*(.*?)\s*-{3,}$/);
          const label = match && match[1].trim() ? match[1].trim() : "—";
          return `note over ${noteTarget}: ${label}`;
        }
        return normalizeSequenceRow(line);
      })
      .filter((line) => isSequenceDiagramLine(line))
      .join("\n");
  }

  function parseFlowNodePart(part) {
    const match = String(part || "").trim().match(/^([a-zA-Z][\w]*)(?:\(([^)]*)\))?$/);
    if (!match) return null;
    let label = match[2] || null;
    if (label && label.includes(",")) label = label.split(",")[0].trim();
    return { id: match[1], label };
  }

  function flowNodeShape(type, id, label) {
    const text = mermaidLabel(label);
    switch (type) {
      case "start":
      case "end":
        return `${id}([${text}])`;
      case "condition":
        return `${id}{${text}}`;
      case "inputoutput":
        return `${id}[/${text}/]`;
      case "subroutine":
        return `${id}[[${text}]]`;
      default:
        return `${id}[${text}]`;
    }
  }

  function flowToMermaid(source) {
    const lines = sanitizeFlowSource(source).split("\n").filter(Boolean);
    const defs = new Map();
    const edges = [];
    let title = "";

    for (const line of lines) {
      const trimmed = line.trim();
      const titleMatch = trimmed.match(/^Title:\s*(.+)$/i);
      if (titleMatch) {
        title = unescapeDiagramLineBreaks(titleMatch[1]).trim();
        continue;
      }
      const defMatch = trimmed.match(
        /^([a-zA-Z][\w]*)=>(start|end|operation|condition|inputoutput|subroutine):\s*(.*)$/
      );
      if (defMatch) {
        defs.set(defMatch[1], { type: defMatch[2], label: defMatch[3] });
        continue;
      }
      if (!FLOW_LINK_RE.test(trimmed)) continue;
      const parts = trimmed.split("->");
      for (let i = 0; i < parts.length - 1; i += 1) {
        const from = parseFlowNodePart(parts[i]);
        const to = parseFlowNodePart(parts[i + 1]);
        if (!from || !to) continue;
        edges.push({ from: from.id, to: to.id, label: from.label });
      }
    }

    const out = [];
    if (title) out.push(`---\ntitle: ${yamlQuoteTitle(title)}\n---`);
    out.push("flowchart TD");
    defs.forEach((def, id) => {
      out.push(`    ${flowNodeShape(def.type, id, def.label)}`);
    });
    edges.forEach(({ from, to, label }) => {
      if (label) out.push(`    ${from} -->|${mermaidLabel(label)}| ${to}`);
      else out.push(`    ${from} --> ${to}`);
    });
    return out.join("\n");
  }

  function sequenceArrowType(token) {
    if (token === "-->") return "-->>";
    return "->>";
  }

  function sequenceToMermaid(source) {
    const lines = sanitizeSequenceSource(source).split("\n").filter(Boolean);
    const out = ["sequenceDiagram"];
    let title = "";

    for (const line of lines) {
      const trimmed = line.trim();
      const titleMatch = trimmed.match(/^Title:\s*(.+)$/i);
      if (titleMatch) {
        title = mermaidLabel(titleMatch[1]);
        continue;
      }
      const participantMatch = trimmed.match(/^participant\s+(.+)$/i);
      if (participantMatch) {
        const name = mermaidLabel(participantMatch[1]);
        out.push(`    participant ${name}`);
        continue;
      }
      const noteSide = trimmed.match(/^note\s+(left|right)\s+of\s+([^:]+):\s*(.*)$/i);
      if (noteSide) {
        out.push(`    Note ${noteSide[1]} of ${noteSide[2].trim()}: ${mermaidLabel(noteSide[3])}`);
        continue;
      }
      const noteOver = trimmed.match(/^note\s+over\s+([^:]+):\s*(.*)$/i);
      if (noteOver) {
        out.push(`    Note over ${noteOver[1].trim()}: ${mermaidLabel(noteOver[2])}`);
        continue;
      }
      const arrow = trimmed.match(/^(.+?)(->>|-->|-+>)\s*([^:]+):\s*(.*)$/);
      if (arrow) {
        const from = arrow[1].trim();
        const to = arrow[3].trim();
        const msg = mermaidLabel(arrow[4]);
        out.push(`    ${from}${sequenceArrowType(arrow[2])}${to}: ${msg}`);
      }
    }

    if (title) out.splice(1, 0, `    title: ${yamlQuoteTitle(title)}`);
    return out.join("\n");
  }

  function sourceToMermaid(kind, source) {
    const text = String(source || "").trim();
    if (!text) return "";
    let result = text;
    if (kind === "mermaid" || MERMAID_HEAD_RE.test(mermaidDiagramBody(text))) result = text;
    else if (kind === "flow") result = flowToMermaid(text);
    else if (kind === "sequence") result = sequenceToMermaid(text);
    else if (FLOW_DEF_RE.test(text) || text.split("\n").some((l) => FLOW_DEF_RE.test(l.trim()))) {
      result = flowToMermaid(text);
    } else if (isDiagramSourceReady("sequence", text)) result = sequenceToMermaid(text);
    return normalizeMermaidSource(result);
  }

  function mermaidVisualKind(source) {
    const text = mermaidDiagramBody(source);
    if (/sequenceDiagram/i.test(text)) return "sequence";
    if (/^(?:flowchart|graph)\b/i.test(text)) return "flow";
    return "mermaid";
  }

  function flowHasDefinitions(cleaned) {
    return String(cleaned || "")
      .split("\n")
      .some((line) => FLOW_DEF_RE.test(String(line || "").trim()));
  }

  function isMermaidSourceReady(source) {
    const text = mermaidDiagramBody(source);
    if (!text) return false;
    if (MERMAID_HEAD_RE.test(text)) {
      const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
      return lines.length >= 2;
    }
    return false;
  }

  function isDiagramSourceReady(kind, source) {
    const text = String(source || "").trim();
    if (!text) return false;
    if (kind === "mermaid") return isMermaidSourceReady(text);
    if (kind === "flow") return flowHasDefinitions(sanitizeFlowSource(text));
    if (kind === "sequence") {
      const cleaned = sanitizeSequenceSource(text);
      const lines = cleaned.split("\n").filter((line) => line.trim());
      return lines.length >= 2 && lines.some((line) => isSequenceDiagramLine(line));
    }
    if (isMermaidSourceReady(text)) return true;
    if (flowHasDefinitions(sanitizeFlowSource(text))) return true;
    const seq = sanitizeSequenceSource(text);
    return seq.split("\n").filter(Boolean).length >= 2;
  }

  function buildMermaidConfig() {
    return {
      startOnLoad: false,
      securityLevel: "strict",
      fontFamily: DIAGRAM_FONT,
      theme: "base",
      themeVariables: {
        fontFamily: DIAGRAM_FONT,
        fontSize: "12px",
        primaryColor: readDiagramCssVar("--diagram-flow-fill", "#303030"),
        primaryTextColor: readDiagramCssVar("--diagram-flow-text", "#ececec"),
        primaryBorderColor: readDiagramCssVar("--diagram-flow-stroke", "#9decff"),
        lineColor: readDiagramCssVar("--diagram-flow-line", "#b4b4b4"),
        secondaryColor: readDiagramCssVar("--diagram-note-fill", "#303030"),
        tertiaryColor: readDiagramCssVar("--diagram-surface", "#1e1e1e"),
        background: readDiagramCssVar("--bg-secondary", "#1e1e1e"),
        mainBkg: readDiagramCssVar("--diagram-actor-fill", "#303030"),
        nodeBorder: readDiagramCssVar("--diagram-flow-stroke", "#9decff"),
        clusterBkg: readDiagramCssVar("--diagram-flow-fill", "#303030"),
        titleColor: readDiagramCssVar("--diagram-title-fill", "#9decff"),
        edgeLabelBackground: readDiagramCssVar("--bg-secondary", "#1e1e1e"),
        actorBkg: readDiagramCssVar("--diagram-actor-fill", "#303030"),
        actorBorder: readDiagramCssVar("--diagram-actor-stroke", "#9decff"),
        actorTextColor: readDiagramCssVar("--diagram-text-fill", "#ececec"),
        actorLineColor: readDiagramCssVar("--diagram-lifeline-stroke", "#b4b4b4"),
        signalColor: readDiagramCssVar("--diagram-line-stroke", "#b4b4b4"),
        signalTextColor: readDiagramCssVar("--diagram-text-fill", "#ececec"),
        labelBoxBkgColor: readDiagramCssVar("--diagram-note-fill", "#303030"),
        labelBoxBorderColor: readDiagramCssVar("--diagram-note-stroke", "#b4b4b4"),
        labelTextColor: readDiagramCssVar("--diagram-text-fill", "#ececec"),
        noteBkgColor: readDiagramCssVar("--diagram-note-fill", "#303030"),
        noteBorderColor: readDiagramCssVar("--diagram-note-stroke", "#b4b4b4"),
        noteTextColor: readDiagramCssVar("--diagram-text-fill", "#ececec"),
        activationBkgColor: readDiagramCssVar("--diagram-flow-fill", "#303030"),
        activationBorderColor: readDiagramCssVar("--diagram-flow-stroke", "#9decff"),
        textColor: readDiagramCssVar("--diagram-text-fill", "#ececec"),
      },
      flowchart: {
        htmlLabels: true,
        curve: "basis",
        padding: 12,
        nodeSpacing: 40,
        rankSpacing: 45,
      },
      sequence: {
        useMaxWidth: true,
        mirrorActors: true,
      },
    };
  }

  function ensureMermaidReady() {
    if (!diagramLibrariesReady()) throw new Error("mermaid library missing");
    if (!mermaidInitialized) {
      mermaid.initialize(buildMermaidConfig());
      mermaidInitialized = true;
      bindMermaidThemeRefresh();
    }
  }

  function bindMermaidThemeRefresh() {
    if (mermaidThemeObserverBound || typeof MutationObserver === "undefined") return;
    mermaidThemeObserverBound = true;
    const observer = new MutationObserver(() => {
      if (!mermaidInitialized) return;
      mermaid.initialize(buildMermaidConfig());
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
  }

  function roundSvgRects(svg, radius) {
    svg.querySelectorAll("rect").forEach((rect) => {
      if (rect.closest(".title, .flowchartTitleText")) return;
      rect.setAttribute("rx", String(radius));
      rect.setAttribute("ry", String(radius));
    });
  }

  function flowMaxHeightPx() {
    const viewport = Math.max(window.innerHeight || 0, 480);
    return Math.min(720, Math.max(400, Math.floor(viewport * 0.72)));
  }

  function diagramViewBoxCenterX(svg) {
    const viewBox = (svg.getAttribute("viewBox") || "").trim().split(/\s+/).map(Number);
    if (viewBox.length === 4 && viewBox.every((n) => Number.isFinite(n))) {
      return viewBox[0] + viewBox[2] / 2;
    }
    const w = parseFloat(svg.getAttribute("width")) || 0;
    return w > 0 ? w / 2 : null;
  }

  function centerDiagramTitles(svg) {
    const centerX = diagramViewBoxCenterX(svg);
    if (centerX == null) return;
    const center = String(centerX);
    svg
      .querySelectorAll(
        ".titleText, .flowchartTitleText, .erTitleText, g.title > text, g.titleText > text"
      )
      .forEach((el) => {
        if (el.tagName.toLowerCase() !== "text") return;
        el.setAttribute("x", center);
        el.setAttribute("text-anchor", "middle");
        el.querySelectorAll("tspan").forEach((tspan, index) => {
          if (index === 0) tspan.setAttribute("x", center);
        });
      });
  }

  function normalizeDiagramSvg(container, kind) {
    const svg = container?.querySelector("svg");
    if (!svg) return;
    if (!kind) {
      const wrap = container.closest(".md-diagram");
      kind = wrap?.dataset?.diagramKind || "flow";
    }
    const pad = 14;
    let bbox = null;
    try {
      bbox = svg.getBBox();
    } catch (_) {}
    const attrW = parseFloat(svg.getAttribute("width")) || 0;
    const attrH = parseFloat(svg.getAttribute("height")) || 0;
    let vx = 0;
    let vy = 0;
    let vw = attrW;
    let vh = attrH;
    if (bbox && bbox.width > 0 && bbox.height > 0) {
      vx = bbox.x - pad;
      vy = bbox.y - pad;
      vw = bbox.width + pad * 2;
      vh = bbox.height + pad * 2;
    } else if (!attrW || !attrH) {
      return;
    } else {
      vx = -pad;
      vy = -pad;
      vw = attrW + pad * 2;
      vh = attrH + pad * 2;
    }
    svg.setAttribute("viewBox", `${vx} ${vy} ${vw} ${vh}`);
    centerDiagramTitles(svg);
    svg.dataset.diagramNaturalWidth = String(vw);
    svg.dataset.diagramNaturalHeight = String(vh);
    svg.style.display = "block";
    svg.style.overflow = "visible";
    if (kind === "sequence") {
      svg.setAttribute("width", String(vw));
      svg.removeAttribute("height");
      svg.style.width = "auto";
      svg.style.maxWidth = "100%";
      svg.style.height = "auto";
      container.style.width = "100%";
      container.style.maxWidth = "100%";
      container.style.minWidth = "0";
      fitSequenceDiagramWidth(container);
      return;
    }
    svg.setAttribute("width", String(vw));
    svg.removeAttribute("height");
    container.style.width = "100%";
    container.style.maxWidth = "100%";
    container.style.minWidth = "0";
    fitFlowchartSize(container);
  }

  function fitFlowchartSize(container) {
    const svg = container?.querySelector("svg");
    const wrap = container?.closest(".md-diagram-flow, .md-diagram");
    if (!svg || !wrap) return;
    const naturalW = parseFloat(svg.dataset.diagramNaturalWidth) || parseFloat(svg.getAttribute("width")) || 0;
    const naturalH = parseFloat(svg.dataset.diagramNaturalHeight) || 0;
    if (!naturalW || !naturalH) return;
    const availableW = Math.max(wrap.clientWidth - 24, 1);
    const maxH = flowMaxHeightPx();
    let scale = 1;
    if (naturalW > availableW) scale = availableW / naturalW;
    if (naturalH * scale > maxH) scale = maxH / naturalH;
    scale = Math.min(1, Math.max(scale, 0.42));
    const displayW = naturalW * scale;
    const displayH = naturalH * scale;
    svg.style.width = `${displayW}px`;
    svg.style.height = `${displayH}px`;
    svg.style.maxWidth = "100%";
    svg.dataset.diagramDisplayScale = String(scale);
    wrap.classList.toggle("md-diagram-flow-compact", scale < 0.98);
    if (scale < 1) {
      container.style.width = `${displayW}px`;
      container.style.maxWidth = "100%";
    } else {
      container.style.width = "";
      container.style.maxWidth = "";
    }
  }

  function fitSequenceDiagramWidth(container) {
    const svg = container?.querySelector("svg");
    const wrap = container?.closest(".md-diagram-sequence, .md-diagram");
    if (!svg || !wrap) return;
    const naturalW = parseFloat(svg.dataset.diagramNaturalWidth) || parseFloat(svg.getAttribute("width")) || 0;
    if (!naturalW) return;
    const available = Math.max(wrap.clientWidth - 24, 1);
    svg.style.width = naturalW > available ? `${available}px` : `${naturalW}px`;
    svg.style.height = "auto";
    svg.style.maxWidth = "100%";
  }

  let diagramResizeBound = false;

  function bindSequenceDiagramResize() {
    if (diagramResizeBound || typeof ResizeObserver === "undefined") return;
    diagramResizeBound = true;
    const observer = new ResizeObserver((entries) => {
      entries.forEach((entry) => {
        const wrap = entry.target;
        const inner = wrap.querySelector(".md-diagram-inner");
        if (!inner) return;
        if (wrap.classList.contains("md-diagram-flow")) fitFlowchartSize(inner);
        else fitSequenceDiagramWidth(inner);
      });
    });
    const watch = (root = document) => {
      root.querySelectorAll(".md-diagram-sequence, .md-diagram-flow").forEach((wrap) => {
        const key = wrap.classList.contains("md-diagram-flow")
          ? "flowResizeObserved"
          : "sequenceResizeObserved";
        if (wrap.dataset[key] === "1") return;
        wrap.dataset[key] = "1";
        observer.observe(wrap);
      });
    };
    watch();
    const messagesEl = document.getElementById("messages");
    if (messagesEl && typeof MutationObserver !== "undefined") {
      const mo = new MutationObserver(() => watch());
      mo.observe(messagesEl, { childList: true, subtree: true });
    }
  }

  function polishMermaidSequenceSvg(container, svg) {
    const viewBox = (svg.getAttribute("viewBox") || "").trim().split(/\s+/).map(Number);
    const attrW = parseFloat(svg.getAttribute("width")) || 0;
    const attrH = parseFloat(svg.getAttribute("height")) || 0;
    let vw = attrW;
    let vh = attrH;
    if (viewBox.length === 4 && viewBox.every((n) => Number.isFinite(n))) {
      vw = viewBox[2];
      vh = viewBox[3];
    }
    if (vw > 0) {
      svg.dataset.diagramNaturalWidth = String(vw);
      svg.dataset.diagramNaturalHeight = String(vh || attrH || vw);
    }
    svg.style.display = "block";
    svg.style.overflow = "visible";
    svg.style.maxWidth = "100%";
    svg.style.height = "auto";
    container.style.width = "100%";
    container.style.maxWidth = "100%";
    container.style.minWidth = "0";
    centerDiagramTitles(svg);
    fitSequenceDiagramWidth(container);
  }

  function polishMermaidSvg(container, kind) {
    const svg = container?.querySelector("svg");
    if (!svg) return;
    svg.classList.add("nexgate-mermaid");
    if (kind === "sequence") {
      roundSvgRects(svg, 6);
      polishMermaidSequenceSvg(container, svg);
    } else {
      roundSvgRects(svg, 8);
      normalizeDiagramSvg(container, kind);
    }
    bindSequenceDiagramResize();
  }

  const DIAGRAM_DOWNLOAD_ICON =
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>';

  const SVG_EXPORT_STYLE_PROPS = [
    "fill",
    "stroke",
    "stroke-width",
    "stroke-dasharray",
    "stroke-linecap",
    "stroke-linejoin",
    "opacity",
    "font-family",
    "font-size",
    "font-weight",
    "text-anchor",
    "dominant-baseline",
  ];

  function diagramDownloadLabel() {
    return window.t?.("diagramDownloadAria") || window.t?.("imageLightboxDownload") || "ダウンロード";
  }

  function getSvgExportDimensions(svg) {
    const viewBox = (svg.getAttribute("viewBox") || "").trim().split(/\s+/).map(Number);
    if (viewBox.length === 4 && viewBox.every((n) => Number.isFinite(n))) {
      return {
        x: viewBox[0],
        y: viewBox[1],
        width: Math.max(viewBox[2], 1),
        height: Math.max(viewBox[3], 1),
      };
    }
    const rect = svg.getBoundingClientRect();
    return {
      x: 0,
      y: 0,
      width: Math.max(rect.width || parseFloat(svg.getAttribute("width")) || 1, 1),
      height: Math.max(rect.height || parseFloat(svg.getAttribute("height")) || 1, 1),
    };
  }

  function inlineSvgComputedStyles(sourceRoot, targetRoot) {
    const walk = (src, tgt) => {
      if (src instanceof Element && tgt instanceof Element) {
        const cs = getComputedStyle(src);
        SVG_EXPORT_STYLE_PROPS.forEach((prop) => {
          const val = cs.getPropertyValue(prop);
          if (val) tgt.style.setProperty(prop, val);
        });
      }
      const srcChildren = [...src.children];
      const tgtChildren = [...tgt.children];
      srcChildren.forEach((child, index) => {
        if (tgtChildren[index]) walk(child, tgtChildren[index]);
      });
    };
    walk(sourceRoot, targetRoot);
  }

  function buildExportSvgClone(svg) {
    const clone = svg.cloneNode(true);
    clone.removeAttribute("style");
    const size = getSvgExportDimensions(svg);
    clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");
    clone.setAttribute("width", String(size.width));
    clone.setAttribute("height", String(size.height));
    if (!clone.getAttribute("viewBox")) {
      clone.setAttribute("viewBox", `${size.x} ${size.y} ${size.width} ${size.height}`);
    }
    inlineSvgComputedStyles(svg, clone);
    return { clone, size };
  }

  function diagramExportBackground(wrap) {
    const fromWrap = wrap ? getComputedStyle(wrap).backgroundColor : "";
    if (fromWrap && fromWrap !== "rgba(0, 0, 0, 0)" && fromWrap !== "transparent") {
      return fromWrap;
    }
    return readDiagramCssVar("--bg-secondary", "#1e1e1e");
  }

  function buildDiagramFilename(kind, svg) {
    const titleText =
      svg.querySelector(".titleText, .flowchartTitleText, .title text")?.textContent || "";
    const rawTitle = titleText.trim();
    const slug = rawTitle
      .replace(/[^\w\u3000-\u9fff-]+/gu, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 48);
    return `nexgate-${kind}${slug ? `-${slug}` : ""}.png`;
  }

  function loadSvgImage(svgString) {
    return new Promise((resolve, reject) => {
      const blob = new Blob([svgString], { type: "image/svg+xml;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const img = new Image();
      img.onload = () => {
        URL.revokeObjectURL(url);
        resolve(img);
      };
      img.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("svg image load failed"));
      };
      img.src = url;
    });
  }

  const DIAGRAM_EXPORT_WATERMARK_URL = "https://nexgate.space";

  function formatDiagramExportTimestamp(date = new Date()) {
    try {
      return new Intl.DateTimeFormat(undefined, {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(date);
    } catch (_) {
      return date.toISOString();
    }
  }

  function buildDiagramExportWatermark(date = new Date()) {
    return `Generated by NEXGATE AI - ${formatDiagramExportTimestamp(date)} | ${DIAGRAM_EXPORT_WATERMARK_URL}`;
  }

  const DIAGRAM_EXPORT_WATERMARK_FONT =
    '400 11px ui-sans-serif, system-ui, -apple-system, "Segoe UI", "Hiragino Sans", "Noto Sans JP", sans-serif';

  function measureDiagramExportWatermarkWidth(ctx) {
    const text = buildDiagramExportWatermark();
    ctx.save();
    ctx.font = DIAGRAM_EXPORT_WATERMARK_FONT;
    const width = ctx.measureText(text).width;
    ctx.restore();
    return width;
  }

  function drawDiagramExportWatermark(ctx, canvasWidth, canvasHeight) {
    const text = buildDiagramExportWatermark();
    ctx.save();
    ctx.font = DIAGRAM_EXPORT_WATERMARK_FONT;
    ctx.textBaseline = "bottom";
    ctx.textAlign = "left";
    ctx.fillStyle = "rgba(148, 148, 148, 0.42)";
    ctx.fillText(text, 12, canvasHeight - 8);
    ctx.restore();
  }

  async function svgToPngBlob(svg, wrap) {
    const { clone, size } = buildExportSvgClone(svg);
    const svgString = new XMLSerializer().serializeToString(clone);
    const img = await loadSvgImage(svgString);
    const padX = 16;
    const padTop = 16;
    const padBottom = 30;
    const scale = Math.min(3, Math.max(2, window.devicePixelRatio || 1));
    const drawW = img.naturalWidth || size.width;
    const drawH = img.naturalHeight || size.height;
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("canvas unsupported");
    const watermarkPadX = 12;
    const watermarkMinW =
      watermarkPadX + Math.ceil(measureDiagramExportWatermarkWidth(ctx)) + watermarkPadX;
    const logicalW = Math.max(drawW + padX * 2, watermarkMinW);
    const logicalH = drawH + padTop + padBottom;
    canvas.width = Math.ceil(logicalW * scale);
    canvas.height = Math.ceil(logicalH * scale);
    ctx.scale(scale, scale);
    ctx.fillStyle = diagramExportBackground(wrap);
    ctx.fillRect(0, 0, logicalW, logicalH);
    const diagramX = (logicalW - drawW) / 2;
    ctx.drawImage(img, diagramX, padTop, drawW, drawH);
    drawDiagramExportWatermark(ctx, logicalW, logicalH);
    return new Promise((resolve, reject) => {
      canvas.toBlob((blob) => {
        if (blob) resolve(blob);
        else reject(new Error("png encode failed"));
      }, "image/png");
    });
  }

  async function downloadDiagramAsPng(wrap) {
    const svg = wrap?.querySelector(".md-diagram-inner svg");
    if (!svg) return;
    const kind = wrap.classList.contains("md-diagram-flow")
      ? "flow"
      : wrap.classList.contains("md-diagram-sequence")
        ? "sequence"
        : "diagram";
    const btn = wrap.querySelector(".md-diagram-download");
    if (btn) {
      btn.disabled = true;
      btn.classList.add("is-busy");
    }
    try {
      const blob = await svgToPngBlob(svg, wrap);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = buildDiagramFilename(kind, svg);
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.warn("diagram download failed", err);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.classList.remove("is-busy");
      }
    }
  }

  function ensureDiagramDownloadButton(wrap) {
    if (!wrap || wrap.querySelector(".md-diagram-fallback")) return;
    if (!wrap.querySelector(".md-diagram-inner svg")) return;
    let btn = wrap.querySelector(".md-diagram-download");
    if (!btn) {
      btn = document.createElement("button");
      btn.type = "button";
      btn.className = "md-diagram-download";
      btn.dataset.i18nAria = "diagramDownloadAria";
      btn.innerHTML = DIAGRAM_DOWNLOAD_ICON;
      btn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        void downloadDiagramAsPng(wrap);
      });
      wrap.appendChild(btn);
    }
    btn.setAttribute("aria-label", diagramDownloadLabel());
    btn.title = diagramDownloadLabel();
  }

  function markMessageHasDiagram(node) {
    const message = node.closest(".message.assistant");
    if (message) message.classList.add("message-has-diagram");
  }

  function showDiagramFallback(container, source) {
    const fallback = document.createElement("div");
    fallback.className = "md-diagram-fallback";
    const note = document.createElement("p");
    note.className = "md-diagram-fallback-note";
    note.textContent = "図の描画に失敗しました";
    const pre = document.createElement("pre");
    const code = document.createElement("code");
    code.textContent = source;
    pre.appendChild(code);
    fallback.appendChild(note);
    fallback.appendChild(pre);
    container.innerHTML = "";
    container.appendChild(fallback);
  }

  async function renderMermaidInto(container, kind, source, renderContext = {}) {
    if (!isDiagramSourceReady(kind, source)) return false;
    const mermaidSource = sourceToMermaid(kind, source);
    const visualKind = mermaidVisualKind(mermaidSource);
    return enqueueMermaidRender(async () => {
      if (!isRenderContextCurrent(renderContext, container)) return false;
      ensureMermaidReady();
      const renderId = `nexgate-mermaid-${++mermaidRenderCounter}`;
      try {
        const { svg } = await mermaid.render(renderId, mermaidSource);
        if (!isRenderContextCurrent(renderContext, container)) return false;
        container.innerHTML = svg;
        polishMermaidSvg(container, visualKind);
        const wrap = container.closest(".md-diagram");
        if (wrap) {
          wrap.dataset.diagramKind = visualKind;
          wrap.classList.remove("md-diagram-flow", "md-diagram-sequence", "md-diagram-mermaid");
          wrap.classList.add(`md-diagram-${visualKind}`, "md-diagram-mermaid");
          markMessageHasDiagram(wrap);
          ensureDiagramDownloadButton(wrap);
        }
        return Boolean(container.querySelector("svg"));
      } catch (err) {
        console.warn("mermaid render failed", err);
        if (!renderContext.streaming && isRenderContextCurrent(renderContext, container)) {
          showDiagramFallback(container, mermaidSource);
        }
        return false;
      }
    });
  }

  function diagramKindFromCode(codeEl) {
    const cls = codeEl.className || "";
    if (/\blanguage-mermaid\b/i.test(cls)) return "mermaid";
    if (/\blanguage-sequence\b/i.test(cls)) return "sequence";
    if (/\blanguage-flow\b/i.test(cls)) return "flow";
    const lang = (codeEl.getAttribute("data-lang") || "").trim().toLowerCase();
    if (lang === "mermaid") return "mermaid";
    if (lang === "sequence") return "sequence";
    if (lang === "flow") return "flow";
    return null;
  }

  function inferDiagramKind(codeEl) {
    const fromLang = diagramKindFromCode(codeEl);
    if (fromLang) return fromLang;
    const text = (codeEl.textContent || "").trim();
    if (!text) return null;
    if (MERMAID_HEAD_RE.test(mermaidDiagramBody(text))) return "mermaid";
    if (FLOW_DEF_RE.test(text) || text.split("\n").some((l) => FLOW_DEF_RE.test(l.trim()))) {
      return "flow";
    }
    if (isDiagramSourceReady("sequence", text)) return "sequence";
    return null;
  }

  function extractClosedDiagramSources(fullMarkdown, kind) {
    const sources = [];
    if (!fullMarkdown) return sources;
    const re = new RegExp("```" + kind + "\\s*\\r?\\n([\\s\\S]*?)```", "gi");
    let match;
    while ((match = re.exec(fullMarkdown)) !== null) {
      sources.push(String(match[1] || "").replace(/\n$/, ""));
    }
    return sources;
  }

  function isClosedDiagramSource(source, kind, fullMarkdown) {
    const trimmed = String(source || "").replace(/\n$/, "").trim();
    if (!trimmed) return false;
    return extractClosedDiagramSources(fullMarkdown, kind).some((block) => {
      const normalized = String(block || "").replace(/\n$/, "").trim();
      return normalized === trimmed || normalized.replace(/\s+/g, " ") === trimmed.replace(/\s+/g, " ");
    });
  }

  function collectDiagramBlocks(root, fullMarkdown, options = {}) {
    const streaming = options.streaming === true;
    const blocks = [];
    root.querySelectorAll("pre code").forEach((codeEl) => {
      const kind = streaming ? diagramKindFromCode(codeEl) : inferDiagramKind(codeEl);
      if (!kind) return;
      const pre = codeEl.closest("pre");
      if (!pre || pre.dataset.diagramEnhanced === "1") return;
      const source = (codeEl.textContent || "").replace(/\n$/, "");
      const explicitLang = /\blanguage-(mermaid|sequence|flow)\b/i.test(codeEl.className || "");
      if (!isDiagramSourceReady(kind, source)) return;
      if (streaming) {
        if (!isClosedDiagramSource(source, kind, fullMarkdown)) return;
      } else if (!explicitLang && kind !== "mermaid" && !MERMAID_HEAD_RE.test(mermaidDiagramBody(source))) {
        return;
      }
      blocks.push({ pre, kind, source });
    });
    return blocks;
  }

  async function hydrateDiagramPlaceholders(root, options = {}) {
    if (!root) return;
    const pending = [];
    root.querySelectorAll(".md-diagram-inner[data-diagram-source]").forEach((inner) => {
      if (inner.dataset.diagramReady === "1" || inner.dataset.diagramLoading === "1") return;
      inner.dataset.diagramLoading = "1";
      pending.push(inner);
    });
    if (!pending.length) return;
    try {
      await loadDiagramLibraries();
    } catch (err) {
      console.warn("diagram libraries failed to load", err);
      pending.forEach((inner) => {
        const source = decodeDiagramSource(inner.getAttribute("data-diagram-source") || "");
        if (!options.streaming) showDiagramFallback(inner, source);
        inner.dataset.diagramReady = options.streaming ? "0" : "1";
        inner.dataset.diagramLoading = "0";
      });
      return;
    }
    for (const inner of pending) {
      const wrap = inner.closest(".md-diagram");
      const kind = (wrap?.dataset?.diagramKind || "mermaid").toLowerCase();
      const source = decodeDiagramSource(inner.getAttribute("data-diagram-source") || "");
      const renderContext = {
        generation: options.generation,
        root: options.root || root,
        streaming: options.streaming === true,
      };
      if (
        options.streaming === true &&
        restoreDiagramCache(renderContext.root, inner, kind, source)
      ) {
        continue;
      }
      const ok = await renderMermaidInto(inner, kind, source, renderContext);
      inner.dataset.diagramLoading = "0";
      if (ok) {
        storeDiagramCache(renderContext.root, kind, source, inner);
        inner.removeAttribute("data-diagram-source");
        inner.dataset.diagramReady = "1";
      } else {
        inner.dataset.diagramReady = options.streaming ? "0" : "1";
      }
    }
  }

  async function replaceDiagramBlock(pre, kind, source, options = {}) {
    const visualKind =
      kind === "mermaid" ? mermaidVisualKind(sourceToMermaid(kind, source)) : kind === "flow" ? "flow" : "sequence";
    const wrap = document.createElement("div");
    wrap.className = `md-diagram md-diagram-${visualKind} md-diagram-mermaid`;
    wrap.dataset.diagramKind = visualKind;
    const inner = document.createElement("div");
    inner.className = "md-diagram-inner";
    wrap.appendChild(inner);
    pre.replaceWith(wrap);
    await renderMermaidInto(inner, kind, source, {
      generation: options.generation,
      root: options.root,
      streaming: options.streaming === true,
    });
  }

  async function enhanceDiagramBlocksInElement(root, fullMarkdown = "", options = {}) {
    if (!root) return;
    await hydrateDiagramPlaceholders(root, options);
    if (options.streaming === true) return;
    const blocks = collectDiagramBlocks(root, fullMarkdown, options);
    if (!blocks.length) return;
    try {
      await loadDiagramLibraries();
    } catch (err) {
      console.warn("diagram libraries failed to load", err);
      return;
    }
    for (const { pre, kind, source } of blocks) {
      pre.dataset.diagramEnhanced = "1";
      await replaceDiagramBlock(pre, kind, source, options);
    }
  }

  window.hydrateDiagramPlaceholders = hydrateDiagramPlaceholders;
  window.isDiagramSourceReady = isDiagramSourceReady;
  window.isClosedDiagramSource = isClosedDiagramSource;
  window.enhanceDiagramBlocksInElement = enhanceDiagramBlocksInElement;
  window.loadDiagramLibraries = loadDiagramLibraries;
  window.encodeDiagramSource = encodeDiagramSource;
  window.decodeDiagramSource = decodeDiagramSource;
  window.normalizeDiagramSvg = normalizeDiagramSvg;
  window.fitFlowchartSize = fitFlowchartSize;
  window.fitSequenceDiagramWidth = fitSequenceDiagramWidth;
  window.bindSequenceDiagramResize = bindSequenceDiagramResize;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindSequenceDiagramResize);
  } else {
    bindSequenceDiagramResize();
  }
})();
