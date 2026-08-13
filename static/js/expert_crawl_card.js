(function () {
  function t(key) {
    return window.t?.(key) || key;
  }

  function esc(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatMs(ms) {
    const n = Number(ms);
    if (!Number.isFinite(n) || n < 0) return "";
    if (n < 1000) return `${Math.round(n)}ms`;
    return `${(n / 1000).toFixed(1)}s`;
  }

  function pageKey(evt) {
    return (evt.url || evt.path || evt.page_id || "").trim();
  }

  function pathDepth(path) {
    const clean = String(path || "/").split("?")[0];
    return clean.split("/").filter(Boolean).length;
  }

  function sortPages(pages) {
    return [...pages].sort((a, b) => {
      const pa = a.path || a.url || "";
      const pb = b.path || b.url || "";
      return pa.localeCompare(pb, undefined, { numeric: true, sensitivity: "base" });
    });
  }

  class ExpertCrawlCard {
    constructor(host) {
      this.host = host;
      this.site = null;
      this.phase = "idle";
      this.pages = new Map();
      this.stats = {};
      this.crawlDuration = null;
      this.summarizeDuration = null;
      this.totalDuration = null;
      this.renderShell();
    }

    renderShell() {
      this.host.innerHTML = `
        <div class="expert-crawl-card" aria-live="polite">
          <button type="button" class="expert-crawl-toggle" aria-expanded="true">
            <span class="expert-crawl-pulse" aria-hidden="true"></span>
            <span class="expert-crawl-title">${esc(t("expertCrawlCardTitle"))}</span>
            <span class="expert-crawl-summary"></span>
            <svg class="expert-crawl-chevron" width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z"/></svg>
          </button>
          <div class="expert-crawl-body">
            <div class="expert-crawl-site-card hidden">
              <div class="expert-crawl-site-head">
                <span class="expert-crawl-site-icon" aria-hidden="true">🌐</span>
                <div class="expert-crawl-site-meta">
                  <div class="expert-crawl-site-host"></div>
                  <div class="expert-crawl-site-timing"></div>
                </div>
                <span class="expert-crawl-phase-badge"></span>
              </div>
              <ul class="expert-crawl-page-tree"></ul>
            </div>
          </div>
        </div>
      `;
      this.root = this.host.querySelector(".expert-crawl-card");
      this.toggle = this.root.querySelector(".expert-crawl-toggle");
      this.titleEl = this.root.querySelector(".expert-crawl-title");
      this.summaryEl = this.root.querySelector(".expert-crawl-summary");
      this.siteCard = this.root.querySelector(".expert-crawl-site-card");
      this.siteHostEl = this.root.querySelector(".expert-crawl-site-host");
      this.siteTimingEl = this.root.querySelector(".expert-crawl-site-timing");
      this.phaseBadgeEl = this.root.querySelector(".expert-crawl-phase-badge");
      this.pageTreeEl = this.root.querySelector(".expert-crawl-page-tree");
      this.toggle.addEventListener("click", () => {
        const collapsed = this.root.classList.toggle("is-collapsed");
        this.toggle.setAttribute("aria-expanded", String(!collapsed));
      });
    }

    ensurePage(key, seed = {}) {
      if (!this.pages.has(key)) {
        this.pages.set(key, {
          key,
          url: seed.url || "",
          path: seed.path || "",
          title: seed.title || "",
          status: "pending",
          depth: pathDepth(seed.path || seed.url),
          duration_ms: null,
          crawl_duration_ms: null,
          summarize_duration_ms: null,
          text_preview: "",
          summary_preview: "",
          chars: 0,
          phase: "crawl",
        });
      }
      return this.pages.get(key);
    }

    handleEvent(evt) {
      if (!evt || !evt.type) return;
      const type = evt.type;

      if (type === "start") {
        this.site = evt.site || null;
        this.phase = "crawl";
        this.siteCard?.classList.remove("hidden");
        this.root.classList.add("is-active");
        this.root.classList.remove("is-complete", "is-error");
        if (this.siteHostEl && this.site) {
          this.siteHostEl.textContent = this.site.host || this.site.base_url || "";
        }
        this.setPhaseBadge(t("expertCrawlPhaseDiscover"));
        this.titleEl.textContent = t("expertCrawlCardActive");
        return;
      }

      if (type === "crawl_phase_start") {
        this.phase = "crawl";
        this.setPhaseBadge(t("expertCrawlPhaseCrawl"));
        return;
      }

      if (type === "page_start") {
        const key = pageKey(evt);
        const page = this.ensurePage(key, evt);
        page.status = "fetching";
        page.path = evt.path || page.path;
        page.url = evt.url || page.url;
        page.depth = pathDepth(page.path || page.url);
        this.render();
        return;
      }

      if (type === "page_done") {
        const key = pageKey(evt);
        const page = this.ensurePage(key, evt);
        Object.assign(page, {
          status: evt.status || "ok",
          title: evt.title || page.title,
          duration_ms: evt.duration_ms,
          crawl_duration_ms: evt.duration_ms,
          text_preview: evt.text_preview || "",
          chars: evt.chars || 0,
          error: evt.error || "",
          phase: "crawl",
          depth: pathDepth(evt.path || evt.url || page.path),
        });
        this.render();
        return;
      }

      if (type === "crawl_phase_done") {
        this.crawlDuration = evt.duration_ms;
        this.stats.pages_total = evt.pages_total;
        this.stats.pages_ok = evt.pages_ok;
        this.stats.pages_error = evt.pages_error;
        this.render();
        return;
      }

      if (type === "summarize_phase_start") {
        this.phase = "summarize";
        this.setPhaseBadge(t("expertCrawlPhaseSummarize"));
        this.titleEl.textContent = t("expertCrawlCardSummarize");
        this.render();
        return;
      }

      if (type === "page_summarized") {
        const key = pageKey(evt);
        const page = this.ensurePage(key, evt);
        page.status = evt.status || page.status;
        page.duration_ms = evt.duration_ms ?? page.duration_ms;
        page.summarize_duration_ms = evt.duration_ms ?? page.summarize_duration_ms;
        page.summary_preview = evt.summary_preview || "";
        page.text_preview = evt.text_preview || page.text_preview;
        page.phase = "summarize";
        page.depth = pathDepth(evt.path || evt.url || page.path);
        this.render();
        return;
      }

      if (type === "summarize_phase_done") {
        this.summarizeDuration = evt.duration_ms;
        this.render();
        return;
      }

      if (type === "complete") {
        this.phase = "done";
        this.totalDuration = evt.duration_ms;
        this.root.classList.remove("is-active");
        this.root.classList.add("is-complete");
        this.setPhaseBadge(t("expertCrawlPhaseDone"));
        this.titleEl.textContent = t("expertCrawlCardDone");
        this.render();
        return;
      }

      if (type === "error") {
        this.phase = "error";
        this.root.classList.add("is-error");
        this.root.classList.remove("is-active");
        this.titleEl.textContent = evt.message || t("expertCrawlCardError");
        this.render();
      }
    }

    setPhaseBadge(label) {
      if (this.phaseBadgeEl) this.phaseBadgeEl.textContent = label || "";
    }

    statusLabel(page) {
      if (page.status === "fetching") return t("expertCrawlStatusFetching");
      if (page.status === "error") return t("expertCrawlStatusError");
      if (page.status === "excluded") return t("expertCrawlStatusExcluded");
      if (page.status === "summarized") return t("expertCrawlStatusSummarized");
      if (page.status === "ok") return t("expertCrawlStatusFetched");
      return t("expertCrawlStatusPending");
    }

    render() {
      const parts = [];
      if (this.stats.pages_total != null) {
        parts.push(`${t("expertCrawlPages")} ${this.stats.pages_ok ?? 0}/${this.stats.pages_total}`);
      }
      if (this.crawlDuration != null) {
        parts.push(`${t("expertCrawlCrawlTime")} ${formatMs(this.crawlDuration)}`);
      }
      if (this.summarizeDuration != null) {
        parts.push(`${t("expertCrawlSummarizeTime")} ${formatMs(this.summarizeDuration)}`);
      }
      if (this.summaryEl) this.summaryEl.textContent = parts.join(" · ");

      const timingParts = [];
      if (this.site?.base_url) timingParts.push(this.site.base_url);
      if (this.totalDuration != null) {
        timingParts.push(`${t("expertCrawlTotal")} ${formatMs(this.totalDuration)}`);
      } else if (this.crawlDuration != null) {
        timingParts.push(`${t("expertCrawlCrawlTime")} ${formatMs(this.crawlDuration)}`);
      }
      if (this.siteTimingEl) this.siteTimingEl.textContent = timingParts.join(" · ");

      if (!this.pageTreeEl) return;
      this.pageTreeEl.innerHTML = "";
      const ordered = sortPages(this.pages.values());
      ordered.forEach((page, index) => {
        const depth = page.depth ?? pathDepth(page.path || page.url);
        const li = document.createElement("li");
        li.className = `expert-crawl-page-item status-${page.status}`;
        li.style.setProperty("--crawl-depth", String(depth));
        li.style.animationDelay = `${Math.min(index * 0.04, 0.4)}s`;
        if (page.status === "fetching") li.classList.add("is-active");
        const title = page.title || page.path || page.url || t("expertCrawlUntitled");
        const timeParts = [];
        if (page.crawl_duration_ms != null) {
          timeParts.push(`${t("expertCrawlCrawlTime")} ${formatMs(page.crawl_duration_ms)}`);
        }
        if (page.summarize_duration_ms != null) {
          timeParts.push(`${t("expertCrawlSummarizeTime")} ${formatMs(page.summarize_duration_ms)}`);
        } else if (page.duration_ms != null && page.crawl_duration_ms == null) {
          timeParts.push(formatMs(page.duration_ms));
        }
        const previews = [];
        if (page.text_preview) {
          previews.push(
            `<div class="expert-crawl-preview expert-crawl-preview--text"><span class="expert-crawl-preview-label">${esc(t("expertCrawlPreviewText"))}</span>${esc(page.text_preview)}</div>`
          );
        }
        if (page.summary_preview) {
          previews.push(
            `<div class="expert-crawl-preview expert-crawl-preview--summary"><span class="expert-crawl-preview-label">${esc(t("expertCrawlPreviewSummary"))}</span>${esc(page.summary_preview)}</div>`
          );
        }
        li.innerHTML = `
          <div class="expert-crawl-page-head">
            <span class="expert-crawl-page-rail" aria-hidden="true"></span>
            <span class="expert-crawl-page-dot" aria-hidden="true"></span>
            <div class="expert-crawl-page-main">
              <div class="expert-crawl-page-title">${esc(title)}</div>
              <div class="expert-crawl-page-path">${esc(page.path || page.url)}</div>
            </div>
            <div class="expert-crawl-page-side">
              <span class="expert-crawl-page-status">${esc(this.statusLabel(page))}</span>
              ${timeParts.length ? `<span class="expert-crawl-page-time">${esc(timeParts.join(" · "))}</span>` : ""}
            </div>
          </div>
          ${previews.join("")}
        `;
        this.pageTreeEl.appendChild(li);
      });
    }
  }

  function ensureHost(messageBody) {
    if (!messageBody) return null;
    let host = messageBody.querySelector(".expert-crawl-card-host");
    if (!host) {
      host = document.createElement("div");
      host.className = "expert-crawl-card-host";
      messageBody.insertBefore(host, messageBody.firstChild);
    }
    return host;
  }

  window.ExpertCrawlCard = {
    attach(messageBody) {
      const host = ensureHost(messageBody);
      if (!host) return null;
      return new ExpertCrawlCard(host);
    },
  };
})();
