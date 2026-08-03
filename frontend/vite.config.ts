import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  // an empty prefix reads every variable, not only the VITE_ ones
  const env = loadEnv(mode, ".", "");
  return {
    plugins: [react()],
    server: {
      // the same routing as nginx in the container, the api is reached without the prefix
      proxy: {
        "/api": {
          // another backend, e.g. one on a copy of the database, is set by API_URL
          target: env.API_URL || "http://127.0.0.1:8001",
          rewrite: (path) => path.replace(/^\/api/, ""),
        },
      },
    },
  };
});
