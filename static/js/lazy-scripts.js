(function () {
  const base = (window.__STATIC_JS_BASE__ || "/static/js/").replace(/\/?$/, "/");
  const loaded = new Map();

  const BUNDLES = {
    settings: ["settings.js", "memory_settings.js", "custom_agents_settings.js"],
    billing: ["billing.js", "confetti.js"],
    announcements: ["announcements.js"],
    admin: ["admin.js"],
    tasks: ["tasks.js"],
    projects: ["projects.js"],
    "ask-expert": ["expert_crawl_card.js", "ask_expert.js"],
  };

  function loadOne(src) {
    if (loaded.has(src)) return loaded.get(src);
    const promise = new Promise((resolve, reject) => {
      const el = document.createElement("script");
      el.src = src;
      el.async = false;
      el.onload = () => resolve();
      el.onerror = () => reject(new Error(`script load failed: ${src}`));
      document.body.appendChild(el);
    });
    loaded.set(src, promise);
    return promise;
  }

  async function loadFiles(files) {
    for (const file of files) {
      await loadOne(base + file);
    }
  }

  async function ensureChartJs() {
    if (window.Chart) return;
    await loadOne(
      "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"
    );
  }

  async function ensureViewScripts(view) {
    if (view === "tasks" && window.__USER__?.tasks_enabled !== true) return;
    if (view === "projects" && window.__USER__?.projects_enabled !== true) return;
    if (view === "ask-expert" && window.__USER__?.info_expert_enabled !== true) return;
    if (view === "admin" && !window.__IS_ADMIN__) return;
    const files = BUNDLES[view];
    if (!files?.length) return;
    if (view === "admin") await ensureChartJs();
    await loadFiles(files);
  }

  async function preloadInitialViewScripts() {
    const view = window.__INITIAL_VIEW__;
    if (!view || view === "chat") return;
    await ensureViewScripts(view);
  }

  window.NexLazyScripts = {
    ensureViewScripts,
    preloadInitialViewScripts,
  };
})();
