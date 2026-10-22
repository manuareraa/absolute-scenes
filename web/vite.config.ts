import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // `wrangler dev` in workers/edge serves /api and /ws on 8787.
    proxy: { "/api": "http://localhost:8787", "/ws": { target: "ws://localhost:8787", ws: true } },
  },
});
