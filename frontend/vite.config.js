import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const api = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          motion: ["framer-motion"],
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "^/(ingest|health|case|brief|dossier|desk|graph|timeline|communities|faithfulness|search_evidence|interrogate|lock_prediction|session|investigate|fact_check|traces|submit_verdict)": {
        target: api,
        changeOrigin: true,
      },
    },
  },
});
