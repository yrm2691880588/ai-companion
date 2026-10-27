import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  const target = env.VITE_API_TARGET || "http://127.0.0.1:8000";
  return {
    plugins: [
      react(),
      VitePWA({
        registerType: "autoUpdate",
        // 只预缓存静态资源；接口请求一律走网络，避免拿到过期数据
        workbox: {
          globPatterns: ["**/*.{js,css,html,svg,png,ico,webmanifest}"],
          navigateFallbackDenylist: [/^\/v1\//],
          runtimeCaching: [
            {
              urlPattern: /\/v1\/.*/,
              handler: "NetworkOnly",
            },
          ],
        },
        manifest: {
          name: "AI 伴侣",
          short_name: "AI 伴侣",
          description: "面向成年人的虚构陪伴工具，数据只存在本机",
          lang: "zh-CN",
          start_url: "/",
          scope: "/",
          display: "standalone",
          orientation: "portrait",
          background_color: "#fff7f9",
          theme_color: "#c2577f",
          icons: [
            { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
            { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
            {
              src: "/icons/icon-512.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "maskable",
            },
          ],
        },
      }),
    ],
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
