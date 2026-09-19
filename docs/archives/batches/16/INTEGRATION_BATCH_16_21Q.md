# Batch 16.21q — Backtest duration presets

Adds three operator presets to the historical backtest timeline:

- **1 mois** = 30 calendar days;
- **3 mois** = 90 calendar days;
- **1 an** = 365 calendar days.

The presets:

- require a successfully previewed dataset;
- start after the existing 35-bar warm-up;
- use the dataset timestamp axis rather than assuming a fixed source timeframe;
- clamp naturally to the available history;
- repartition the selected window into DESIGN / VALIDATION / OOS at 60 / 20 / 20;
- do not alter the scanner, MTF construction, agents, Risk Engine, Rio, Denver, broker, or execution model.

Existing **Test rapide**, **Tout le dataset**, and **Réinitialiser 60 / 20 / 20**
controls remain unchanged.
