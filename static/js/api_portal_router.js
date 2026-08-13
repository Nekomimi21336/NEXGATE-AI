(function () {
  const PANELS = ["dashboard", "tokens", "usage", "docs"];

  function currentPanel() {
    const path = location.pathname.replace(/\/+$/, "") || "/dash";
    if (path === "/dash") return "dashboard";
    if (path.startsWith("/dash/tokens") || path === "/portal" || path === "/portal/tokens") {
      return "tokens";
    }
    if (path.startsWith("/dash/usage") || path.startsWith("/portal/usage")) return "usage";
    if (path.startsWith("/dash/docs") || path.startsWith("/portal/docs")) return "docs";
    return "dashboard";
  }

  function showPanel(panel) {
    const active = PANELS.includes(panel) ? panel : "dashboard";
    document.querySelectorAll("[data-portal-panel]").forEach((el) => {
      const on = el.dataset.portalPanel === active;
      el.classList.toggle("active", on);
      el.hidden = !on;
    });
    document.querySelectorAll("[data-portal-nav]").forEach((el) => {
      el.classList.toggle("is-active", el.dataset.portalNav === active);
    });
    document.dispatchEvent(
      new CustomEvent("api-portal-panel", { detail: { panel: active } })
    );
  }

  function init() {
    showPanel(currentPanel());
    window.addEventListener("popstate", () => showPanel(currentPanel()));
  }

  window.apiPortalRouter = { showPanel, currentPanel, init };
})();
