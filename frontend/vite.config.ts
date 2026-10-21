import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import tsconfigPaths from "vite-tsconfig-paths";
import tailwindcss from "@tailwindcss/vite";
import { nitro } from "nitro/vite";

export default defineConfig({
  plugins: [
    tsconfigPaths({ projects: ["./tsconfig.json"] }),
    tanstackStart({
      server: { entry: "server" },
      importProtection: {
        behavior: "error",
        client: {
          files: ["**/server/**"],
          specifiers: ["server-only"]
        }
      }
    }),
    nitro({
      preset: "node-server",
      routeRules: {
        "/**": {
          headers: { "Strict-Transport-Security": "max-age=31536000; includeSubDomains", "X-Content-Type-Options": "nosniff" },
        },
        "/api/**": {
          proxy: `${(process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/$/, "")}/api/**`,
        },
      },
    }),
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      "@": `${process.cwd()}/src`
    },
    dedupe: [
      "react",
      "react-dom",
      "react/jsx-runtime",
      "react/jsx-dev-runtime",
      "@tanstack/react-query",
      "@tanstack/query-core"
    ]
  },
  optimizeDeps: {
    include: ["react", "react-dom", "react-dom/client", "react/jsx-runtime", "react/jsx-dev-runtime"],
    ignoreOutdatedRequests: true
  },
  server: {
    headers: { "X-Content-Type-Options": "nosniff" },
    host: "localhost",
    port: 8080,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  }
});
