/**
 * indexeddb-store.js - IndexedDBストレージモジュール
 *
 * localStorage の 5-10MB 制限を回避するため、大容量のチャット履歴・メッセージを
 * IndexedDB に保存する。localStorage は軽量なインデックス専用に使う。
 *
 * 使用法:
 *   window.NexIndexedDB.saveSession(sessionId, { id, title, messages })
 *   window.NexIndexedDB.loadSession(sessionId) -> { id, title, messages }
 *   window.NexIndexedDB.deleteSession(sessionId)
 */
(function () {
  const DB_NAME = "nexgate-chat";
  const DB_VERSION = 1;
  const STORE_SESSIONS = "sessions";

  let dbPromise = null;

  function openDB() {
    if (dbPromise) return dbPromise;
    dbPromise = new Promise((resolve, reject) => {
      if (typeof indexedDB === "undefined") {
        reject(new Error("IndexedDB not supported"));
        return;
      }
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = (ev) => {
        const db = ev.target.result;
        if (!db.objectStoreNames.contains(STORE_SESSIONS)) {
          db.createObjectStore(STORE_SESSIONS, { keyPath: "id" });
        }
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
    return dbPromise;
  }

  function withStore(mode, fn) {
    return openDB().then(
      (db) =>
        new Promise((resolve, reject) => {
          const tx = db.transaction(STORE_SESSIONS, mode);
          const store = tx.objectStore(STORE_SESSIONS);
          const result = fn(store);
          tx.oncomplete = () => resolve(result);
          tx.onerror = () => reject(tx.error);
          tx.onabort = () => reject(tx.error);
        })
    );
  }

  const api = {
    isSupported() {
      return typeof indexedDB !== "undefined";
    },

    saveSession(sessionId, data) {
      if (!this.isSupported() || !sessionId) return Promise.resolve();
      const record = {
        id: sessionId,
        title: data.title || "",
        messages: data.messages || [],
        updated_at: new Date().toISOString(),
      };
      return withStore("readwrite", (store) => store.put(record)).catch(() => {});
    },

    loadSession(sessionId) {
      if (!this.isSupported() || !sessionId) return Promise.resolve(null);
      return withStore("readonly", (store) => store.get(sessionId)).catch(() => null);
    },

    loadAllSessions() {
      if (!this.isSupported()) return Promise.resolve([]);
      return withStore("readonly", (store) => store.getAll()).catch(() => []);
    },

    deleteSession(sessionId) {
      if (!this.isSupported() || !sessionId) return Promise.resolve();
      return withStore("readwrite", (store) => store.delete(sessionId)).catch(() => {});
    },

    clearAll() {
      if (!this.isSupported()) return Promise.resolve();
      return withStore("readwrite", (store) => store.clear()).catch(() => {});
    },

    // 概要のみ取得（履歴一覧表示用）
    loadSummaries() {
      return this.loadAllSessions().then((sessions) =>
        (sessions || []).map((s) => ({
          id: s.id,
          title: s.title,
          message_count: Array.isArray(s.messages) ? s.messages.length : 0,
          updated_at: s.updated_at,
        }))
      );
    },
  };

  window.NexIndexedDB = api;
})();
