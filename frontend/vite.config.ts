import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const target = env.VITE_API_TARGET || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5273,
      strictPort: true,
      proxy: {
        "/v1": { target, changeOrigin: true },
      },
    },
    preview: {
      host: "127.0.0.1",
      port: 5273,
      strictPort: true,
    },
  };
});
