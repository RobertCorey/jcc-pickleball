import { Outlet } from "react-router-dom";

// Router shell. Real layout (top bar, footer, freshness pill) lands in PR 2,
// once we start porting site/index.html's chrome over. For the scaffold we
// just render the active child route inside a body div.
export default function App() {
  return (
    <div className="min-h-screen bg-bone text-ink font-body">
      <Outlet />
    </div>
  );
}
