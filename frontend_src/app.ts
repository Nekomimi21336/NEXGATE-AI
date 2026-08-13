// ============================================================
// NexgateAI - Main App Entry Point
// ============================================================
// This is the Vite entry point. It imports all migrated utility
// modules. In a full migration, this would import and orchestrate
// the entire application.

import "./utils/uuid";
import "./utils/notify";
import "./utils/preferences";

// TODO: Migrate remaining JS modules incrementally.
// For now, the legacy static/js/*.js files continue to work via
// script tags in app.html. The migrated TypeScript modules above
// register themselves on the window object, making them available
// to legacy code as well.

console.log("[NexgateAI] TypeScript modules loaded (uuid, notify, preferences)");
