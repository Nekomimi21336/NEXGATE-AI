const SIDEBAR_STORAGE_KEY = "nexgate_sidebar_collapsed";
const MOBILE_MQ = window.matchMedia("(max-width: 768px)");
const appEl = document.getElementById("app");
const sidebarToggle = document.getElementById("sidebarToggle");
const sidebarBackdrop = document.getElementById("sidebarBackdrop");
const mobileMenuBtn = document.getElementById("mobileMenuBtn");

function isMobileSidebar() {
  return MOBILE_MQ.matches;
}

function isSidebarOpen() {
  if (!appEl) return false;
  if (isMobileSidebar()) return appEl.classList.contains("sidebar-mobile-open");
  return !appEl.classList.contains("sidebar-collapsed");
}

function setMobileSidebarOpen(open) {
  if (!appEl) return;
  appEl.classList.toggle("sidebar-mobile-open", open);
  if (sidebarBackdrop) {
    sidebarBackdrop.classList.toggle("is-open", open);
    sidebarBackdrop.setAttribute("aria-hidden", String(!open));
    if (open) {
      sidebarBackdrop.removeAttribute("tabindex");
    } else {
      sidebarBackdrop.setAttribute("tabindex", "-1");
    }
  }
  document.body.classList.toggle("sidebar-scroll-lock", open);
  sidebarToggle?.setAttribute("aria-expanded", String(open));
  mobileMenuBtn?.setAttribute("aria-expanded", String(open));
}

function setDesktopSidebarCollapsed(collapsed) {
  if (!appEl) return;
  appEl.classList.toggle("sidebar-collapsed", collapsed);
  localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? "1" : "0");
  sidebarToggle?.setAttribute("aria-expanded", String(!collapsed));
}

function updateSidebarToggle() {
  if (!sidebarToggle) return;
  sidebarToggle.setAttribute("aria-expanded", String(isSidebarOpen()));
}

function applySidebarLayoutMode() {
  if (!appEl) return;
  if (isMobileSidebar()) {
    appEl.classList.remove("sidebar-collapsed");
    setMobileSidebarOpen(false);
  } else {
    appEl.classList.remove("sidebar-mobile-open");
    if (sidebarBackdrop) {
      sidebarBackdrop.classList.remove("is-open");
      sidebarBackdrop.setAttribute("aria-hidden", "true");
      sidebarBackdrop.setAttribute("tabindex", "-1");
    }
    document.body.classList.remove("sidebar-scroll-lock");
    const collapsed = localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1";
    appEl.classList.toggle("sidebar-collapsed", collapsed);
    mobileMenuBtn?.setAttribute("aria-expanded", "false");
  }
  updateSidebarToggle();
}

function toggleSidebar() {
  if (isMobileSidebar()) {
    setMobileSidebarOpen(!isSidebarOpen());
  } else {
    setDesktopSidebarCollapsed(isSidebarOpen());
  }
}

function closeMobileSidebar() {
  if (isMobileSidebar() && isSidebarOpen()) {
    setMobileSidebarOpen(false);
  }
}

const sidebarExtensionsNav = document.getElementById("sidebarExtensionsNav");
const sidebarTasksLink = document.getElementById("sidebarTasksLink");
const sidebarProjectsLink = document.getElementById("sidebarProjectsLink");
const sidebarChatLink = document.getElementById("sidebarChatLink");
const sidebarAskExpertLink = document.getElementById("sidebarAskExpertLink");
const announcementsTabBtn = document.getElementById("announcementsTabBtn");
const announcementsUnreadBadge = document.getElementById("announcementsUnreadBadge");
const ANNOUNCEMENTS_READ_KEY = "nexgate_announcements_read_at";

function isTasksEnabled() {
  return window.__USER__?.tasks_enabled === true;
}

function isProjectsEnabled() {
  return window.__USER__?.projects_enabled === true;
}

function isInfoExpertEnabled() {
  return window.__USER__?.info_expert_enabled === true;
}

const customAgentSelectBtn = document.getElementById("customAgentSelectBtn");

function updateCustomAgentSelectVisibility() {
  const enabled = window.__USER__?.custom_agents_enabled === true;
  if (customAgentSelectBtn) {
    customAgentSelectBtn.classList.toggle("hidden", !enabled);
    customAgentSelectBtn.setAttribute("aria-hidden", String(!enabled));
  }
  if (!enabled) {
    window.customAgentSelect?.selectAgent?.(null);
  }
}

window.updateCustomAgentSelectVisibility = updateCustomAgentSelectVisibility;

function updateExtensionsNavVisibility() {
  const tasksOn = isTasksEnabled();
  const projectsOn = isProjectsEnabled();
  const infoExpertOn = isInfoExpertEnabled();
  if (sidebarTasksLink) {
    sidebarTasksLink.classList.toggle("hidden", !tasksOn);
    sidebarTasksLink.setAttribute("aria-hidden", String(!tasksOn));
  }
  if (sidebarProjectsLink) {
    sidebarProjectsLink.classList.toggle("hidden", !projectsOn);
    sidebarProjectsLink.setAttribute("aria-hidden", String(!projectsOn));
  }
  if (sidebarAskExpertLink) {
    sidebarAskExpertLink.classList.toggle("hidden", !infoExpertOn);
    sidebarAskExpertLink.setAttribute("aria-hidden", String(!infoExpertOn));
  }
  const activeView = window.NexRouter?.getActiveView?.();
  if (!tasksOn && activeView === "tasks") {
    window.NexRouter.navigate("/chat", { replace: true });
  }
  if (!projectsOn && activeView === "projects") {
    window.NexRouter.navigate("/chat", { replace: true });
  }
  if (!infoExpertOn && activeView === "ask-expert") {
    window.NexRouter.navigate("/chat", { replace: true });
  }
}

function updateSidebarNavActive(view) {
  if (sidebarTasksLink) {
    sidebarTasksLink.classList.toggle("active", view === "tasks");
  }
  if (sidebarProjectsLink) {
    sidebarProjectsLink.classList.toggle("active", view === "projects");
  }
  if (sidebarChatLink) {
    sidebarChatLink.classList.toggle("active", view === "chat");
  }
  if (sidebarAskExpertLink) {
    sidebarAskExpertLink.classList.toggle("active", view === "ask-expert");
  }
  if (announcementsTabBtn) {
    announcementsTabBtn.classList.toggle("active", view === "announcements");
  }
}

window.updateTasksNavVisibility = updateExtensionsNavVisibility;
window.updateProjectsNavVisibility = updateExtensionsNavVisibility;

function setProjectSidebarMode(enabled) {
  const sessionPanel = document.getElementById("sidebarSessionPanel");
  const projectPanel = document.getElementById("sidebarProjectPanel");
  const askExpertPanel = document.getElementById("sidebarAskExpertPanel");
  const on = Boolean(enabled);
  sessionPanel?.classList.toggle("hidden", on);
  projectPanel?.classList.toggle("hidden", !on);
  projectPanel?.setAttribute("aria-hidden", String(!on));
  if (on) {
    askExpertPanel?.classList.add("hidden");
    askExpertPanel?.setAttribute("aria-hidden", "true");
  }
  if (on) window.projectsApp?.renderSidebar?.();
}

window.setProjectSidebarMode = setProjectSidebarMode;

function setAskExpertSidebarMode(enabled) {
  const sessionPanel = document.getElementById("sidebarSessionPanel");
  const projectPanel = document.getElementById("sidebarProjectPanel");
  const askExpertPanel = document.getElementById("sidebarAskExpertPanel");
  const on = Boolean(enabled);
  sessionPanel?.classList.toggle("hidden", on);
  projectPanel?.classList.add("hidden");
  projectPanel?.setAttribute("aria-hidden", "true");
  askExpertPanel?.classList.toggle("hidden", !on);
  askExpertPanel?.setAttribute("aria-hidden", String(!on));
  if (on) window.askExpertApp?.renderSidebar?.();
}

window.setAskExpertSidebarMode = setAskExpertSidebarMode;

async function updateAnnouncementsBadge() {
  if (!announcementsUnreadBadge) return;
  try {
    const res = await fetch("/api/announcements");
    if (!res.ok) return;
    const data = await res.json();
    const items = Array.isArray(data.announcements) ? data.announcements : [];
    const readAt = localStorage.getItem(ANNOUNCEMENTS_READ_KEY) || "";
    const unread = !readAt
      ? items.length
      : items.filter((item) => (item.published_at || "") > readAt).length;
    announcementsUnreadBadge.textContent = unread > 9 ? "9+" : String(unread);
    announcementsUnreadBadge.classList.toggle("hidden", unread === 0);
  } catch (_) {}
}

window.updateAnnouncementsBadge = updateAnnouncementsBadge;

window.NexSidebar = {
  close: closeMobileSidebar,
  isMobile: isMobileSidebar,
  updateNavActive: updateSidebarNavActive,
};

if (window.__USER__) {
  updateExtensionsNavVisibility();
  void updateAnnouncementsBadge();
}

if (appEl) {
  if (!isMobileSidebar() && localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1") {
    appEl.classList.add("sidebar-collapsed");
  }
  applySidebarLayoutMode();
  MOBILE_MQ.addEventListener("change", applySidebarLayoutMode);
}

sidebarToggle?.addEventListener("click", toggleSidebar);
mobileMenuBtn?.addEventListener("click", (e) => {
  e.stopPropagation();
  toggleSidebar();
});
document.querySelectorAll(".mobile-menu-btn:not(#mobileMenuBtn)").forEach((btn) => {
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleSidebar();
  });
});
sidebarBackdrop?.addEventListener("click", () => setMobileSidebarOpen(false));

document.getElementById("sidebarRegion")?.addEventListener("click", (e) => {
  e.stopPropagation();
});

const accountBtn = document.getElementById("accountBtn");
const accountMenu = document.getElementById("accountMenu");
const accountAvatar = document.getElementById("accountAvatar");
const accountName = document.getElementById("accountName");
const accountPlan = document.getElementById("accountPlan");
const accountPlanName = document.getElementById("accountPlanName");
const accountPlanPrice = document.getElementById("accountPlanPrice");
const logoutBtn = document.getElementById("logoutBtn");
const accountApiPlatformLink = document.getElementById("accountApiPlatformLink");

function updateAccountDisplay(user) {
  if (!user) return;
  const displayName = user.display_name || user.username;
  if (accountName) accountName.textContent = displayName;
  if (accountAvatar) accountAvatar.textContent = displayName.charAt(0).toUpperCase();
  if (accountPlan) accountPlan.dataset.plan = user.plan || "plus";
  if (accountPlanName) accountPlanName.textContent = user.plan_name || "PASS+";
  if (accountPlanPrice) accountPlanPrice.textContent = user.plan_price_label || "$10/月";
  if (accountApiPlatformLink) {
    const apiOn = user.api_access_active === true;
    accountApiPlatformLink.classList.toggle("hidden", !apiOn);
    accountApiPlatformLink.setAttribute("aria-hidden", String(!apiOn));
  }
  window.updateAccountProfileCard?.(user);
}

window.updateAccountDisplay = updateAccountDisplay;

if (window.__USER__) {
  updateAccountDisplay(window.__USER__);
  updateCustomAgentSelectVisibility();
}

if (accountBtn && accountMenu) {
  accountBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const hidden = accountMenu.classList.toggle("hidden");
    accountBtn.setAttribute("aria-expanded", String(!hidden));
  });

  document.addEventListener("click", (e) => {
    if (e.target.closest("#sidebarRegion") || e.target.closest("#sidebarBackdrop")) {
      return;
    }
    accountMenu.classList.add("hidden");
    accountBtn.setAttribute("aria-expanded", "false");
  });

  accountMenu.addEventListener("click", (e) => e.stopPropagation());

  accountMenu.querySelectorAll(".account-menu-item").forEach((item) => {
    item.addEventListener("click", () => {
      accountMenu.classList.add("hidden");
      accountBtn.setAttribute("aria-expanded", "false");
      closeMobileSidebar();
    });
  });
}

if (logoutBtn) {
  logoutBtn.addEventListener("click", async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/login";
  });
}

document.getElementById("newChatBtn")?.addEventListener("click", closeMobileSidebar);
document.getElementById("askExpertCreateBtn")?.addEventListener("click", closeMobileSidebar);
sidebarTasksLink?.addEventListener("click", closeMobileSidebar);
sidebarProjectsLink?.addEventListener("click", closeMobileSidebar);
sidebarChatLink?.addEventListener("click", closeMobileSidebar);
sidebarAskExpertLink?.addEventListener("click", closeMobileSidebar);
announcementsTabBtn?.addEventListener("click", closeMobileSidebar);
