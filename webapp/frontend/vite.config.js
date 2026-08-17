import { defineConfig } from "vite";

export default defineConfig({
  server: {
    // Dev-time proxy so the frontend can fetch /api/* without CORS —
    // webapp/backend/app.py also sets permissive CORS headers directly for
    // the non-proxied case (e.g. `vite preview`, or a deployed frontend).
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
