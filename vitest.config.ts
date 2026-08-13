import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "frontend_src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["frontend_src/**/*.test.ts"],
    setupFiles: ["frontend_src/test-setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["frontend_src/**/*.ts"],
      exclude: [
        "frontend_src/**/*.test.ts",
        "frontend_src/test-setup.ts",
        "frontend_src/types/**",
      ],
    },
  },
});
