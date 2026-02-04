import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  clearScreen: false,
  server: {
    host: true,
    port: 5174,
    proxy: {
      "/ws": {
        target: "ws://localhost:8421",
        ws: true,
        configure: (proxy) => {
          proxy.onError = () => {};
        },
      },
      "/api": {
        target: "http://localhost:8421",
      },
    },
  },
});
