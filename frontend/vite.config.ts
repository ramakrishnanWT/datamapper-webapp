import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During `npm run dev` Vite serves on :5173 and proxies /api to Flask.
// `npm run build` emits to ./dist, which Flask serves in production.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:5000",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
