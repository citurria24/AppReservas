import { defineConfig } from "vitest/config";
import { loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.DJANGO_PROXY_TARGET || "http://localhost:8012";
  const proxy = Object.fromEntries(
    [
      "/api",
      "/cuenta",
      "/agenda",
      "/peluquerias",
      "/reservar",
      "/static",
      "^/$",
    ].map((path) => [path, { target, changeOrigin: false }]),
  );
  return {
    base: "/app/",
    plugins: [react(), tailwindcss()],
    server: { port: 5173, strictPort: true, proxy },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test-setup.ts"],
      css: true,
    },
  };
});
