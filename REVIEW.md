# Codebase Review: Karo Price Frontend

_Last reviewed: 2026-11-15_

The earlier round of issues (leaking debug endpoint, PostgREST filter injection,
per-request Supabase clients, duplicated `RETAILERS` / `fmt` / `fetchAllRows` /
header / footer / `CAT_CLASS`, sequential home-page fetches, the `min === 0`
spread bug, the `window.innerWidth` SSR crash, missing error states and error
boundary) has been resolved. Shared logic now lives in `lib/` and `components/`,
the debug route is gated to `NODE_ENV === 'development'`, search input is
sanitised, and the home page fetches in parallel.

The 2026-11 round fixed: brand filter staying active after it disappeared from
the dropdown, slow responses overwriting newer selections on the history pages,
pie labels drawn at the top of the chart on Grafer, silent load failures on
Grafer/Produkter, the basket savings figure comparing incomplete baskets, a
made-up "12:00" in the header's updated label, non-deterministic pagination on
`prissammenligning`, and the SVG-only Open Graph image. ESLint and unit tests
for `lib/` were added.

The speed round fixed: history endpoints paging through hundreds of Supabase
requests one at a time (now parallel, with only the needed columns and a
deterministic sort), 0 kr "not stocked" rows being counted as prices in
averages and charts, Ukesnitt downloading every daily row instead of weekly
averages, and Next.js caching Supabase responses indefinitely in its data cache
(stale prices).

## Outstanding

### Performance / Architecture
- **All pages are client components.** Every page uses `'use client'` with
  `useEffect` data fetching — no SSR, so no SEO and a slower first paint. Moving
  data fetching into server components (keeping interactive parts as client
  components) would be the largest improvement, if SEO/first-paint matter.
- **No `loading.js` files.** Pages handle loading manually instead of using
  Next.js Suspense loading UI.

### Data
- **History is aggregated in Node, not in the database.** `lib/historyRows.js`
  pages through `prishistorikk` (one row per retailer per product per day) in
  parallel and pivots/averages it in the API route. A Postgres view or RPC that
  returns the weekly / per-category averages directly would cut a cold request
  from seconds to milliseconds.
- **Functions run in `iad1` (US East).** If the Supabase project is in Europe,
  pin the functions next to it with `"regions"` in `vercel.json`.

### Fonts
- **Euclid Circular A is not bundled.** It is licensed, so the files are not in
  the repo; it only renders where it is installed locally, and everyone else
  gets Figtree. Add the `.woff2` files and load them with `next/font/local` in
  `app/layout.js` to serve it to all visitors.

### Developer Experience
- **Tests only cover `lib/`** (`npm test`). No component or API route tests.
- **No TypeScript** — plain JS with no type checking.
- **No CI** — `npm run lint` and `npm test` are not run automatically.

### Minor
- Inline styles are scattered through the page components (especially
  `historikk/page.js`), mixed with the single global stylesheet.
