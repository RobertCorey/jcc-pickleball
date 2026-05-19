import { ViteReactSSG } from "vite-react-ssg";
import type { RouteRecord } from "vite-react-ssg";
import App from "./App";
import Home from "./routes/Home";
import "./index.css";

// Route tree consumed by vite-react-ssg at build time. Each path here will
// produce a real HTML file under dist/ (e.g. dist/index.html), with route-
// specific <head> baked in. In a later PR this list will be augmented at
// build time from site/data/sessions.json to also emit dist/s/<id>/index.html
// for every event — preserving the OG-preview-friendly URLs the live site
// currently ships.
const routes: RouteRecord[] = [
  {
    path: "/",
    Component: App,
    children: [
      { index: true, Component: Home },
    ],
  },
];

export const createRoot = ViteReactSSG({ routes });
