import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

export default defineConfig({
  plugins: [viteSingleFile()],
  build: {
    rollupOptions: {
      input: process.env.INPUT || "src/client/mcp-app.html",
    },
    outDir: "dist",
  },
});
