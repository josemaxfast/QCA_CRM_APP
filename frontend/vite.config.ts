import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Port 5174 / 8001 so the CRM can run next to QCA Quote (5173 / 8000) on one computer.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: { "/api": "http://127.0.0.1:8001" },
  },
});
