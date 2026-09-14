# Overlay

Front end for the crypto prediction market desk. Three views:

- **Pricing** the Monte Carlo outlook and the largest gap against Polymarket
- **Overlay** every market we can price, with edge, stake and a paper slip
- **Make a market** write a question against the simulation and get it priced

Numbers in `src/data/desk.ts` are seeded from `reports/outlook_latest.md`. Edge,
side and stake are derived in `src/lib/signals.ts`, so bankroll and edge buffer
move every figure on the page.

```
npm install
npm run dev
npm run build
npm run lint
```
