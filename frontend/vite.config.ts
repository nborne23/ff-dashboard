import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// `process` without pulling in @types/node for one env read.
const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env;

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        // Overridable so a second checkout/session can run its own backend alongside.
        target: env?.GRIDIRON_API_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
  },
});
