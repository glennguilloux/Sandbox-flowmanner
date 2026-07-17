# Frontend agent-gallery patch — spec

This patch is the frontend half of R1 (expose the 185 previously-unreachable personas).
The backend now serves all 215 personas across 16 domain directories; the gallery UI must
render every one of them and let users narrow the list. Two files change:
(1) `src/data/agents.ts` — extends `DOMAIN_LABELS` and `DOMAIN_COLORS` with the 6 domains that
were missing (`academic`, `agent-personalities`, `browser`, `design`, `engineering`,
`game-development`, `paid-media`, `product`, `project-management`, `spatial-computing`,
`specialized`, `support`, `testing`) so all 16 render with a human label and a distinct
badge color instead of a raw key + generic slate. (2) `src/app/[locale]/agents/agents-page-content.tsx`
— adds client-side discovery controls on top of the already-loaded `domains`: a text search
input that filters agents by name/description, a row of domain filter chips (All + one per
domain, toggling `activeDomain`), and a "Recommended" row showing the first 6 agents across
all domains (hidden once a search/filter is active). The domain sections now iterate
`visibleDomains` (post filter/search) while the header still reports the full catalogue total.
No new network calls, no new dependencies, no backend contract change — purely presentational
filtering over data the endpoint already returns.
