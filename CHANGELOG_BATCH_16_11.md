# CHANGELOG — Batch 16.11

## Advanced Specialist Smoke Validation

- ajout de `run_advanced_specialist_smokes.py` ;
- Denver construit ses statistiques depuis les vrais replays PAPER fermés ;
- usage du `HistoricalSetupStatsCatalog` existant ;
- usage du `DenverSetupStatsContextProvider` existant ;
- Rio lit uniquement les analytics publiques Kraken Futures actuelles ;
- séparation stricte Rio live-context / replay historique pour éviter le look-ahead ;
- aucune modification du Risk Engine, PaperBroker, orchestration de production ou LIVE trading.
