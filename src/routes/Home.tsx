import { Head } from "vite-react-ssg";

// Smoke-test route. The real Home (filter bar, session list, freshness pill,
// glance card, etc.) decomposes from site/index.html in PR 2. The point of
// this placeholder is just to prove the SSG pipeline writes route-specific
// <head> to dist/index.html and that Tailwind utilities resolve against the
// @theme tokens in src/index.css.
export default function Home() {
  return (
    <>
      <Head>
        <title>CourtTime · scaffold</title>
        <meta
          name="description"
          content="v2 scaffold of CourtTime — Vite + React + TS + Tailwind + SSG. Not the live site yet."
        />
      </Head>
      <main className="mx-auto max-w-prose px-6 py-16">
        <p className="font-display text-xs uppercase tracking-[0.14em] text-forest">
          v2 scaffold
        </p>
        <h1 className="mt-2 font-display text-4xl font-extrabold tracking-tight text-ink">
          CourtTime
        </h1>
        <p className="mt-4 text-ink-soft">
          This is the toolchain smoke test — Vite + React + TypeScript +
          Tailwind v4 + <code className="font-mono text-sm">vite-react-ssg</code>.
          The live site is still served from <code className="font-mono text-sm">site/</code>;
          this build runs in CI but does not ship until the cutover PR.
        </p>
        <p className="mt-6 inline-flex items-center gap-2 rounded-full border border-line-strong bg-paper px-3 py-1 text-sm font-semibold text-forest">
          <span className="h-2 w-2 rounded-full bg-lime-deep" aria-hidden="true" />
          Tokens resolving: <span className="font-mono">bone / forest / lime / Bricolage</span>
        </p>
      </main>
    </>
  );
}
