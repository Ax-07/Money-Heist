# Batch 16.10 — MOCK Agent Coverage

Ce patch complète le bouton **Test rapide** pour tester réellement la communication
multi-agents en mode MOCK.

Le MOCK historique sélectionnait toujours Berlin. Désormais, uniquement lorsque
**Test rapide** a été utilisé et que le mode IA est **MOCK**, le Professor MOCK
tourne de manière déterministe parmi les spécialistes que l'orchestration expose
déjà comme disponibles.

Avec les spécialistes standards sans contexte additionnel :

```text
1 -> Berlin
2 -> Nairobi
3 -> Tokyo
4 -> Berlin + Nairobi
5 -> Berlin + Tokyo
6 -> Nairobi + Tokyo
puis répétition
```

Rio et Denver ne sont jamais rendus artificiellement disponibles. Ils restent
soumis à leurs contextes spécialisés réels. Si l'orchestration les expose dans un
backtest, le MOCK avancé existant est utilisé pour leurs sorties.

Le MOCK normal sans Test rapide, CACHED, LIVE_EVAL, le Professor réel, le Risk
Engine et le PaperBroker restent inchangés.

## Installation

```powershell
uv run python apply_batch_16_10_mock_agent_coverage.py
uv run pytest -q tests/dashboard/test_backtest_agent_coverage.py
uv run pytest -q tests/dashboard
uv run pytest -q
```
