const VIEW_CHAT = "view-chat";
const VIEW_SETTINGS = "view-settings";
const VIEW_BILLING = "view-billing";
const VIEW_ANNOUNCEMENTS = "view-announcements";
const VIEW_TASKS = "view-tasks";
const VIEW_PROJECTS = "view-projects";
const VIEW_ASK_EXPERT = "view-ask-expert";
const VIEW_ADMIN = "view-admin";
const SETTINGS_PANELS = ["general", "billing-info", "security", "embed", "theme", "display", "performance", "extensions", "memory-settings", "integrations", "agent"];

function parseSettingsHash(hash) {
  const raw = (hash || "#general").slice(1).split("?")[0];
  if (raw === "profile" || raw === "account") return { panel: "general", integrationsTab: null, agentRoute: null };
  if ((raw === "agent" || raw.startsWith("agent/")) && window.__USER__?.custom_agents_enabled !== true) {
    return { panel: "general", integrationsTab: null, agentRoute: null };
  }
  if (raw === "integrations/google") return { panel: "integrations", integrationsTab: "google", agentRoute: null };
  if (raw === "integrations/discord") return { panel: "integrations", integrationsTab: "discord", agentRoute: null };
  if (raw === "integrations/computelab") return { panel: "integrations", integrationsTab: "computelab", agentRoute: null };
  if (raw.startsWith("integrations/")) return { panel: "integrations", integrationsTab: "overview", agentRoute: null };
  const agentEditMatch = raw.match(/^agent\/edit\/([^/]+)$/);
  if (agentEditMatch) {
    return {
      panel: "agent",
      integrationsTab: null,
      agentRoute: { screen: "editor", agentId: decodeURIComponent(agentEditMatch[1]) },
    };
  }
  if (raw === "agent" || raw.startsWith("agent/")) {
    return { panel: "agent", integrationsTab: null, agentRoute: { screen: "list", agentId: null } };
  }
  if (!SETTINGS_PANELS.includes(raw)) return { panel: "general", integrationsTab: null, agentRoute: null };
  return { panel: raw, integrationsTab: null, agentRoute: null };
}
const SESSION_PATH_RE = /^\/chat\/session\/([0-9a-f-]{36})\/?$/i;
const LIVE_COLLAB_PATH_RE = /^\/chat\/live\/([a-f0-9]{32})\/?$/i;
const PROJECT_PATH_RE = /^\/projects\/([0-9a-f-]{36})\/?$/i;
const ASK_EXPERT_SESSION_PATH_RE = /^\/ask-expert\/session\/([0-9a-f-]{36})\/?$/i;
const ASK_EXPERT_PATH_RE = /^\/ask-expert\/([0-9a-f-]{36})\/?$/i;

let activeView = null;

function parseRoute(pathname, hash) {
  const sessionMatch = pathname.match(SESSION_PATH_RE);
  if (sessionMatch) {
    return { view: "chat", sessionId: sessionMatch[1] };
  }
  if (pathname === "/chat" || pathname === "/chat/") {
    return { view: "chat", sessionId: null };
  }
  const liveCollabMatch = pathname.match(LIVE_COLLAB_PATH_RE);
  if (liveCollabMatch) {
    return { view: "chat", sessionId: window.__SESSION_ID__ || null, liveCollabId: liveCollabMatch[1] };
  }
  if (pathname === "/billing" || pathname === "/billing/") {
    return { view: "billing" };
  }
  if (pathname === "/announcements" || pathname === "/announcements/") {
    return { view: "announcements" };
  }
  if (pathname === "/tasks" || pathname === "/tasks/") {
    return { view: "tasks" };
  }
  const askExpertSessionMatch = pathname.match(ASK_EXPERT_SESSION_PATH_RE);
  if (askExpertSessionMatch) {
    return { view: "ask-expert", sessionId: askExpertSessionMatch[1], expertId: null };
  }
  const askExpertMatch = pathname.match(ASK_EXPERT_PATH_RE);
  if (askExpertMatch) {
    return { view: "ask-expert", expertId: askExpertMatch[1], sessionId: null };
  }
  if (pathname === "/ask-expert" || pathname === "/ask-expert/") {
    return { view: "ask-expert", expertId: null, sessionId: null };
  }
  const projectMatch = pathname.match(PROJECT_PATH_RE);
  if (projectMatch) {
    return { view: "projects", projectId: projectMatch[1] };
  }
  if (pathname === "/projects" || pathname === "/projects/") {
    return { view: "projects", projectId: null };
  }
  if (pathname === "/admin" || pathname === "/admin/") {
    const raw = (hash || "#users").slice(1);
    if (raw.startsWith("user/")) {
      return {
        view: "admin",
        panel: "users",
        adminUser: decodeURIComponent(raw.slice(5)),
        adminPlan: null,
      };
    }
    if (raw.startsWith("plan/")) {
      return {
        view: "admin",
        panel: "plans",
        adminUser: null,
        adminPlan: decodeURIComponent(raw.slice(5)),
      };
    }
    let panel = raw;
    if (!window.ADMIN_PANELS.includes(panel)) panel = "users";
    return { view: "admin", panel, adminUser: null, adminPlan: null };
  }
  if (pathname === "/settings" || pathname === "/settings/") {
    const parsed = parseSettingsHash(hash);
    return {
      view: "settings",
      panel: parsed.panel,
      integrationsTab: parsed.integrationsTab,
      agentRoute: parsed.agentRoute,
    };
  }
  return null;
}

function buildPath(route) {
  if (route.view === "settings") {
    if (route.panel === "integrations" && route.integrationsTab === "google") {
      return "/settings#integrations/google";
    }
    if (route.panel === "integrations" && route.integrationsTab === "discord") {
      return "/settings#integrations/discord";
    }
    if (route.panel === "integrations" && route.integrationsTab === "computelab") {
      return "/settings#integrations/computelab";
    }
    if (route.panel === "agent" && route.agentRoute?.screen === "editor" && route.agentRoute.agentId) {
      return `/settings#agent/edit/${encodeURIComponent(route.agentRoute.agentId)}`;
    }
    const panel = route.panel && route.panel !== "general" ? `#${route.panel}` : "";
    return `/settings${panel}`;
  }
  if (route.view === "billing") return "/billing";
  if (route.view === "announcements") return "/announcements";
  if (route.view === "tasks") return "/tasks";
  if (route.view === "ask-expert") {
    if (route.sessionId) return `/ask-expert/session/${route.sessionId}`;
    if (route.expertId) return `/ask-expert/${route.expertId}`;
    return "/ask-expert";
  }
  if (route.view === "projects") {
    if (route.projectId) return `/projects/${route.projectId}`;
    return "/projects";
  }
  if (route.view === "admin") {
    if (route.adminUser) return `/admin#user/${encodeURIComponent(route.adminUser)}`;
    if (route.adminPlan) return `/admin#plan/${encodeURIComponent(route.adminPlan)}`;
    const panel = route.panel && route.panel !== "users" ? `#${route.panel}` : "";
    return `/admin${panel || "#users"}`;
  }
  if (route.sessionId) return `/chat/session/${route.sessionId}`;
  return "/chat";
}

function pageTitle(view) {
  if (view === "settings") return "設定 - NEXGATE AI";
  if (view === "billing") return "プラン/課金 - NEXGATE AI";
  if (view === "announcements") return "お知らせ - NEXGATE AI";
  if (view === "tasks") return "TASKS - NEXGATE AI";
  if (view === "projects") return "Projects [BETA] - NEXGATE AI";
  if (view === "ask-expert") return "AskExpert - NEXGATE AI";
  if (view === "admin") return "管理機能 - NEXGATE AI";
  return "チャット - NEXGATE AI";
}

function setActiveView(view) {
  const chatEl = document.getElementById(VIEW_CHAT);
  const settingsEl = document.getElementById(VIEW_SETTINGS);
  const billingEl = document.getElementById(VIEW_BILLING);
  const announcementsEl = document.getElementById(VIEW_ANNOUNCEMENTS);
  const tasksEl = document.getElementById(VIEW_TASKS);
  const projectsEl = document.getElementById(VIEW_PROJECTS);
  const askExpertEl = document.getElementById(VIEW_ASK_EXPERT);
  const adminEl = document.getElementById(VIEW_ADMIN);
  if (!chatEl || !settingsEl || !billingEl || !announcementsEl || !tasksEl || !projectsEl || !askExpertEl) return;

  if (activeView === "projects" && view !== "projects") {
    window.projectsApp?.onHide?.();
  }
  if (activeView === "ask-expert" && view !== "ask-expert") {
    window.askExpertApp?.onHide?.();
  }

  chatEl.classList.toggle("is-active", view === "chat");
  settingsEl.classList.toggle("is-active", view === "settings");
  billingEl.classList.toggle("is-active", view === "billing");
  announcementsEl.classList.toggle("is-active", view === "announcements");
  tasksEl.classList.toggle("is-active", view === "tasks");
  projectsEl.classList.toggle("is-active", view === "projects");
  askExpertEl.classList.toggle("is-active", view === "ask-expert");
  if (adminEl) adminEl.classList.toggle("is-active", view === "admin");
  activeView = view;
  const activeEl = document.querySelector(".app-view.is-active");
  if (activeEl) window.applyLanguage?.(window.__USER__?.language || "ja", activeEl);
  if (view !== "projects") {
    window.setProjectSidebarMode?.(false);
  }
  if (view !== "ask-expert") {
    window.setAskExpertSidebarMode?.(false);
  }
  document.title = pageTitle(view);
  window.NexSidebar?.updateNavActive?.(view);
}

async function applyRoute(route, { updateUrl = true, replace = false } = {}) {
  if (!route) return;

  if (route.view === "admin" && !window.__IS_ADMIN__) {
    applyRoute({ view: "chat", sessionId: null }, { updateUrl: true, replace: true });
    return;
  }

  window.NexSidebar?.close?.();

  if (route.view === "settings") {
    await window.NexLazyScripts?.ensureViewScripts?.("settings");
  } else if (route.view === "billing") {
    await window.NexLazyScripts?.ensureViewScripts?.("billing");
  } else if (route.view === "announcements") {
    await window.NexLazyScripts?.ensureViewScripts?.("announcements");
  } else if (route.view === "tasks") {
    await window.NexLazyScripts?.ensureViewScripts?.("tasks");
  } else if (route.view === "projects") {
    await window.NexLazyScripts?.ensureViewScripts?.("projects");
  } else if (route.view === "ask-expert") {
    await window.NexLazyScripts?.ensureViewScripts?.("ask-expert");
  } else if (route.view === "admin") {
    await window.NexLazyScripts?.ensureViewScripts?.("admin");
  }

  if (route.view === "chat") {
    setActiveView("chat");
    window.__SESSION_ID__ = route.sessionId;
    if (window.chatApp?.loadSession) {
      window.chatApp.loadSession(route.sessionId);
    }
    if (route.sessionId === null) {
      document.getElementById("messageInput")?.focus();
    }
  } else if (route.view === "settings") {
    setActiveView("settings");
    window.settingsApp?.showPanel(route.panel || "general", {
      syncUrl: updateUrl,
      integrationsTab: route.integrationsTab || undefined,
      agentRoute: route.agentRoute || undefined,
    });
  } else if (route.view === "billing") {
    setActiveView("billing");
    window.billingApp?.loadUsage();
  } else if (route.view === "announcements") {
    setActiveView("announcements");
    window.announcementsApp?.load?.();
  } else if (route.view === "tasks") {
    if (window.__USER__?.tasks_enabled !== true) {
      applyRoute({ view: "chat", sessionId: null }, { updateUrl: true, replace: true });
      return;
    }
    setActiveView("tasks");
    window.tasksApp?.onShow?.();
  } else if (route.view === "projects") {
    if (window.__USER__?.projects_enabled !== true) {
      applyRoute({ view: "chat", sessionId: null }, { updateUrl: true, replace: true });
      return;
    }
    setActiveView("projects");
    window.projectsApp?.onShow?.(route.projectId ?? null);
  } else if (route.view === "ask-expert") {
    if (window.__USER__?.info_expert_enabled !== true) {
      applyRoute({ view: "chat", sessionId: null }, { updateUrl: true, replace: true });
      return;
    }
    setActiveView("ask-expert");
    window.__SESSION_ID__ = route.sessionId ?? null;
    window.askExpertApp?.onShow?.({
      expertId: route.expertId ?? null,
      sessionId: route.sessionId ?? window.__SESSION_ID__ ?? null,
    });
  } else if (route.view === "admin") {
    setActiveView("admin");
    window.adminApp?.showPanel(route.panel || "users", {
      syncUrl: updateUrl,
      adminUser: route.adminUser || null,
      adminPlan: route.adminPlan || null,
    });
    const afterAdminLoad = () => {
      if (route.adminUser) {
        window.adminApp?.openUser?.(route.adminUser, { syncUrl: false });
      } else {
        window.adminApp?.closeUser?.({ syncUrl: false });
      }
      if (route.adminPlan) {
        window.adminApp?.openPlan?.(route.adminPlan, { syncUrl: false });
      } else {
        window.adminApp?.closePlan?.({ syncUrl: false });
      }
    };
    const loaded = window.adminApp?.loadAdmin?.();
    if (loaded?.then) loaded.then(afterAdminLoad);
    else afterAdminLoad();
  }

  if (updateUrl) {
    const path = buildPath(route);
    const state = { route };
    if (replace) history.replaceState(state, "", path);
    else history.pushState(state, "", path);
  }
}

function navigate(url, { replace = false } = {}) {
  let pathname = url;
  let hash = "";
  if (url.includes("#")) {
    const parts = url.split("#");
    pathname = parts[0];
    hash = `#${parts[1]}`;
  }
  const route = parseRoute(pathname, hash);
  if (!route) return;
  void applyRoute(route, { updateUrl: true, replace });
}

function isSpaPath(pathname) {
  return (
    pathname === "/chat" ||
    pathname === "/chat/" ||
    SESSION_PATH_RE.test(pathname) ||
    pathname === "/settings" ||
    pathname === "/settings/" ||
    pathname === "/billing" ||
    pathname === "/billing/" ||
    pathname === "/announcements" ||
    pathname === "/announcements/" ||
    pathname === "/tasks" ||
    pathname === "/tasks/" ||
    pathname === "/projects" ||
    pathname === "/projects/" ||
    PROJECT_PATH_RE.test(pathname) ||
    pathname === "/ask-expert" ||
    pathname === "/ask-expert/" ||
    ASK_EXPERT_SESSION_PATH_RE.test(pathname) ||
    ASK_EXPERT_PATH_RE.test(pathname) ||
    pathname === "/admin" ||
    pathname === "/admin/"
  );
}

function initialRoute() {
  const parsed = parseRoute(location.pathname, location.hash);
  if (parsed) return parsed;
  if (window.__INITIAL_VIEW__ === "settings") {
    const parsed = parseSettingsHash(location.hash);
    return {
      view: "settings",
      panel: parsed.panel,
      integrationsTab: parsed.integrationsTab,
      agentRoute: parsed.agentRoute,
    };
  }
  if (window.__INITIAL_VIEW__ === "billing") {
    return { view: "billing" };
  }
  if (window.__INITIAL_VIEW__ === "announcements") {
    return { view: "announcements" };
  }
  if (window.__INITIAL_VIEW__ === "tasks") {
    return { view: "tasks" };
  }
  if (window.__INITIAL_VIEW__ === "projects") {
    const projectMatch = location.pathname.match(PROJECT_PATH_RE);
    return { view: "projects", projectId: projectMatch ? projectMatch[1] : null };
  }
  if (window.__INITIAL_VIEW__ === "ask-expert") {
    const sessionMatch = location.pathname.match(ASK_EXPERT_SESSION_PATH_RE);
    if (sessionMatch) {
      return { view: "ask-expert", sessionId: sessionMatch[1], expertId: null };
    }
    const expertMatch = location.pathname.match(ASK_EXPERT_PATH_RE);
    return { view: "ask-expert", expertId: expertMatch ? expertMatch[1] : null, sessionId: null };
  }
  if (window.__INITIAL_VIEW__ === "admin") {
    const raw = (location.hash || "#users").slice(1);
    if (raw.startsWith("user/")) {
      return {
        view: "admin",
        panel: "users",
        adminUser: decodeURIComponent(raw.slice(5)),
        adminPlan: null,
      };
    }
    if (raw.startsWith("plan/")) {
      return {
        view: "admin",
        panel: "plans",
        adminUser: null,
        adminPlan: decodeURIComponent(raw.slice(5)),
      };
    }
    let panel = raw;
    if (!window.ADMIN_PANELS.includes(panel)) panel = "users";
    return { view: "admin", panel, adminUser: null, adminPlan: null };
  }
  return { view: "chat", sessionId: window.__SESSION_ID__ || null };
}

async function initRouter() {
  await window.NexLazyScripts?.preloadInitialViewScripts?.();
  const route = initialRoute();
  await applyRoute(route, { updateUrl: false });
  history.replaceState({ route }, "", buildPath(route));

  document.addEventListener("click", (e) => {
    const link = e.target.closest("a[href]");
    if (!link || link.target === "_blank" || link.hasAttribute("download")) return;
    const href = link.getAttribute("href");
    if (!href || href.startsWith("mailto:") || href.startsWith("tel:")) return;

    const url = new URL(link.href, location.origin);
    if (url.origin !== location.origin || !isSpaPath(url.pathname)) return;

    e.preventDefault();
    navigate(url.pathname + url.hash, { replace: false });
  });

  window.addEventListener("popstate", () => {
    const route =
      parseRoute(location.pathname, location.hash) ||
      history.state?.route ||
      { view: "chat", sessionId: null };
    void applyRoute(route, { updateUrl: false });
  });

  window.addEventListener("hashchange", () => {
    void (async () => {
      const route = parseRoute(location.pathname, location.hash);
      if (activeView === "settings" && route?.view === "settings") {
        await window.NexLazyScripts?.ensureViewScripts?.("settings");
        window.settingsApp?.showPanel(route.panel, {
          syncUrl: false,
          integrationsTab: route.integrationsTab || undefined,
          agentRoute: route.agentRoute || undefined,
        });
      }
      if (activeView === "admin" && route?.view === "admin") {
        await window.NexLazyScripts?.ensureViewScripts?.("admin");
        window.adminApp?.showPanel(route.panel, {
          syncUrl: false,
          adminUser: route.adminUser || null,
          adminPlan: route.adminPlan || null,
        });
        if (route.adminUser) window.adminApp?.openUser?.(route.adminUser, { syncUrl: false });
        else window.adminApp?.closeUser?.({ syncUrl: false });
        if (route.adminPlan) window.adminApp?.openPlan?.(route.adminPlan, { syncUrl: false });
        else window.adminApp?.closePlan?.({ syncUrl: false });
      }
    })();
  });
}

window.NexRouter = { navigate, parseRoute, getActiveView: () => activeView };

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initRouter);
} else {
  initRouter();
}
