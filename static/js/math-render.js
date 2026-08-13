(function () {
  function mathPlaceholder(id) {
    return `\uE000MDM${id}\uE001`;
  }

  function isLikelyMathBody(body) {
    const t = String(body || "").trim();
    if (!t) return false;
    if (/\\[a-zA-Z]+/.test(t)) return true;
    if (/[_^{}]/.test(t) && /[=+\-*/]/.test(t)) return true;
    if (/[A-Za-z]_[{A-Za-z0-9-]/.test(t)) return true;
    if (/^[=+\-*/0-9A-Za-z().,\s]+$/.test(t) && /[=^_]/.test(t)) return true;
    return false;
  }

  function protectMathSegments(text) {
    const segments = [];
    let work = text;

    work = work.replace(/\\\[([\s\S]*?)\\\]/g, (_, body) => {
      const id = segments.length;
      segments.push({ display: true, body });
      return mathPlaceholder(id);
    });

    work = work.replace(/\$\$([\s\S]*?)\$\$/g, (_, body) => {
      const id = segments.length;
      segments.push({ display: true, body });
      return mathPlaceholder(id);
    });

    work = work.replace(/\\\(([\s\S]*?)\\\)/g, (match, body) => {
      if (!isLikelyMathBody(body)) return match;
      const id = segments.length;
      segments.push({ display: false, body });
      return mathPlaceholder(id);
    });

    work = work.replace(/(?<!\$)\$(?!\$)((?:[^$\n]|\\\$)+?)\$(?!\$)/g, (match, body) => {
      if (!isLikelyMathBody(body)) return match;
      const id = segments.length;
      segments.push({ display: false, body });
      return mathPlaceholder(id);
    });

    return { work, segments };
  }

  function renderMathSegment(seg) {
    if (typeof katex === "undefined") {
      const raw = seg.body.trim();
      return seg.display ? `$$${raw}$$` : `$${raw}$`;
    }
    try {
      return katex.renderToString(seg.body.trim(), {
        displayMode: Boolean(seg.display),
        throwOnError: false,
        strict: "ignore",
        trust: false,
      });
    } catch {
      const raw = seg.body.trim();
      return seg.display ? `$$${raw}$$` : `$${raw}$`;
    }
  }

  function injectRenderedMath(html, segments) {
    if (!segments.length) return html;
    let out = html;
    segments.forEach((seg, id) => {
      const token = mathPlaceholder(id);
      if (!out.includes(token)) return;
      const rendered = renderMathSegment(seg);
      const wrapped = seg.display
        ? `<div class="md-math-block">${rendered}</div>`
        : `<span class="md-math-inline">${rendered}</span>`;
      out = out.split(token).join(wrapped);
    });
    return out;
  }

  window.protectMathSegments = protectMathSegments;
  window.injectRenderedMath = injectRenderedMath;
})();
