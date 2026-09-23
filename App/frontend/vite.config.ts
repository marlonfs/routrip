import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  base: "./",
  build: {
    outDir: "../backend/static",
    emptyOutDir: true,
    // Só roda no WebView2 (Chromium atual): dispensa os polyfills e a transpilação
    // voltada a navegadores antigos.
    target: "chrome120",
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
