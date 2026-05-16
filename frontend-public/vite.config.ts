import path from "node:path";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

/** Same proxy for `vite dev` and `vite preview` — without it, `/api/*` returns SPA HTML. */
/** http-proxy defaults time out long streams — SSE traces need no proxy socket timeout. */
const apiProxy = {
  "/api": {
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
    secure: false,
    timeout: 0,
    proxyTimeout: 0,
  },
  "/health": {
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
    secure: false,
    timeout: 0,
    proxyTimeout: 0,
  },
} as const;

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
  },
  // Resolve package subpaths to source for dev HMR (Phase 1+ components in packages/ui).
  resolve: {
    alias: {
      "@gene-guidelines/ui": path.resolve(__dirname, "../packages/ui/src"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { ...apiProxy },
  },
  preview: {
    port: 4173,
    strictPort: true,
    proxy: { ...apiProxy },
  },
});
