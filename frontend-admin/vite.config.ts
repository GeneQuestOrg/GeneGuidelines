import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

/** http-proxy defaults time out long streams — doctor_finder SSE needs no proxy socket timeout. */
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
  // Resolve package subpaths to source for dev HMR (Phase 1+ components in packages/ui).
  resolve: {
    alias: {
      "@gene-guidelines/ui": path.resolve(__dirname, "../packages/ui/src"),
      "@gene-guidelines/ops": path.resolve(__dirname, "../packages/ops/src"),
    },
  },
  server: {
    port: 5174,
    strictPort: true,
    proxy: { ...apiProxy },
  },
  preview: {
    port: 4174,
    strictPort: true,
    proxy: { ...apiProxy },
  },
});
