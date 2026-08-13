const CACHE_KEY = "nexgate_location_city";
const CACHE_TS_KEY = "nexgate_location_city_ts";
const CACHE_TTL_MS = 30 * 60 * 1000;

function isGeolocationEnabled() {
  return window.__USER__?.geolocation_enabled === true;
}

function readCache() {
  try {
    const city = sessionStorage.getItem(CACHE_KEY);
    const ts = Number(sessionStorage.getItem(CACHE_TS_KEY) || 0);
    if (!city || !ts || Date.now() - ts > CACHE_TTL_MS) return null;
    return city;
  } catch {
    return null;
  }
}

function writeCache(city) {
  try {
    sessionStorage.setItem(CACHE_KEY, city);
    sessionStorage.setItem(CACHE_TS_KEY, String(Date.now()));
  } catch {
    /* ignore */
  }
}

function getCurrentPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("unsupported"));
      return;
    }
    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: false,
      timeout: 12000,
      maximumAge: CACHE_TTL_MS,
    });
  });
}

async function fetchCityFromCoords(lat, lon) {
  const res = await fetch("/api/geolocation/city", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ lat, lon }),
  });
  let data = {};
  try {
    data = await res.json();
  } catch {
    return null;
  }
  if (!res.ok || !data.city) return null;
  return String(data.city).trim() || null;
}

async function getLocationContextForChat() {
  if (!isGeolocationEnabled()) return null;

  const cached = readCache();
  if (cached) return cached;

  try {
    const pos = await getCurrentPosition();
    const city = await fetchCityFromCoords(pos.coords.latitude, pos.coords.longitude);
    if (city) {
      writeCache(city);
      return city;
    }
  } catch {
    return null;
  }
  return null;
}

window.NexGeolocation = {
  isGeolocationEnabled,
  getLocationContextForChat,
};
