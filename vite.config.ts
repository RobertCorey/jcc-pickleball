import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Vite + React + Tailwind v4 + vite-react-ssg.
//
// SSG: vite-react-ssg picks up the route tree exported from src/main.tsx and
//   emits real HTML files (with per-route <head>) under dist/. This is what
//   keeps per-event /s/<id>/ pages crawlable by social previews — the
//   non-negotiable constraint behind dropping the hand-rolled Python template.
//
// Tailwind v4 via @tailwindcss/vite: tokens live in src/index.css under
//   @theme, no separate tailwind.config required. We picked the Vite plugin
//   path over classic PostCSS because v4 ships first-class Vite support and
//   we don't need PostCSS for anything else.
//
// base: when GitHub Pages serves the site under /jcc-pickleball/, set
//   VITE_BASE=/jcc-pickleball/ at build time. Defaults to "/" so local
//   `npm run dev` / `npm run preview` Just Work.
export default defineConfig({
  base: process.env.VITE_BASE ?? "/",
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});
