(function () {
  const READ_KEY = "nexgate_announcements_read_at";
  const listEl = document.getElementById("announcementsList");
  const detailEl = document.getElementById("announcementsDetail");
  const layoutEl = document.getElementById("announcementsLayout");
  const emptyEl = document.getElementById("announcementsEmpty");
  const loadingEl = document.getElementById("announcementsLoading");
  const detailTitleEl = document.getElementById("announcementsDetailTitle");
  const detailDateEl = document.getElementById("announcementsDetailDate");
  const detailBodyEl = document.getElementById("announcementsDetailBody");

  let items = [];
  let selectedId = null;

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function getReadAt() {
    return localStorage.getItem(READ_KEY) || "";
  }

  function formatDate(iso) {
    if (!iso) return "";
    try {
      return new Intl.DateTimeFormat(undefined, {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      }).format(new Date(iso));
    } catch {
      return iso;
    }
  }

  function unreadCount(announcements, readAt) {
    if (!announcements.length) return 0;
    if (!readAt) return announcements.length;
    return announcements.filter((item) => (item.published_at || "") > readAt).length;
  }

  function markAllRead() {
    if (!items.length) return;
    const latest = items[0].published_at || "";
    if (latest) localStorage.setItem(READ_KEY, latest);
    window.updateAnnouncementsBadge?.();
    renderList();
  }

  function renderList() {
    if (!listEl) return;
    const readAt = getReadAt();
    listEl.innerHTML = items
      .map((item) => {
        const active = item.id === selectedId ? " is-active" : "";
        const unread = (item.published_at || "") > readAt ? " is-unread" : "";
        return (
          `<button type="button" class="announcements-item${active}${unread}" data-id="${escapeHtml(item.id)}">` +
          `<span class="announcements-item-title">${escapeHtml(item.title)}</span>` +
          `<span class="announcements-item-date">${escapeHtml(formatDate(item.published_at))}</span>` +
          `</button>`
        );
      })
      .join("");
  }

  function renderDetail(item) {
    if (!item || !detailEl) return;
    if (detailTitleEl) detailTitleEl.textContent = item.title || "";
    if (detailDateEl) detailDateEl.textContent = formatDate(item.published_at);
    if (detailBodyEl) {
      if (window.applyMarkdownContent) {
        void window.applyMarkdownContent(detailBodyEl, item.body || "");
      } else {
        detailBodyEl.textContent = item.body || "";
      }
    }
  }

  function selectItem(id) {
    selectedId = id;
    const item = items.find((row) => row.id === id);
    renderList();
    renderDetail(item);
    markAllRead();
  }

  async function fetchAnnouncements() {
    const res = await fetch("/api/announcements");
    if (!res.ok) throw new Error("fetch failed");
    const data = await res.json();
    return Array.isArray(data.announcements) ? data.announcements : [];
  }

  async function load() {
    loadingEl?.classList.remove("hidden");
    emptyEl?.classList.add("hidden");
    layoutEl?.classList.add("hidden");
    try {
      items = await fetchAnnouncements();
      items.sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""));
      loadingEl?.classList.add("hidden");
      window.updateAnnouncementsBadge?.();
      if (!items.length) {
        emptyEl?.classList.remove("hidden");
        if (listEl) listEl.innerHTML = "";
        return;
      }
      layoutEl?.classList.remove("hidden");
      const keep = items.some((item) => item.id === selectedId);
      selectItem(keep ? selectedId : items[0].id);
    } catch {
      loadingEl?.classList.add("hidden");
      emptyEl?.classList.remove("hidden");
    }
  }

  listEl?.addEventListener("click", (event) => {
    const btn = event.target.closest(".announcements-item");
    if (!btn?.dataset?.id) return;
    selectItem(btn.dataset.id);
  });

  window.announcementsApp = { load, fetchAnnouncements, unreadCount, getReadAt };
})();
