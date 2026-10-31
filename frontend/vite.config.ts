import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// nginx sends /api to the app, here and in production
export default defineConfig({
  plugins: [react()],
});
