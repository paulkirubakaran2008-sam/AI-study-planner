import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000", "/health": "http://localhost:8000" } },
  build: {
    sourcemap: false,
    rollupOptions: {
      output: { manualChunks: { vendor: ["react", "react-dom", "react-router-dom"], query: ["@tanstack/react-query"] } },
    },
  },
});
