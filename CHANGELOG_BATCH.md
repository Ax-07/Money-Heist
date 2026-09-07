# Batch 07a — Core Agents

## Contenu

- The Professor : planification et décision finale structurées via AI Gateway.
- Palermo : revue contradictoire structurée.
- Lisbon : analyse de l'économie IA et recommandations d'état.
- Registre d'agents Core avec états, rôles, routes modèles et allowlist d'outils.
- Registre de prompts versionnés (`v1`) avec résolution explicite des versions.
- Tests des contrats, du versionnage et des frontières de sécurité.

## Frontières de sécurité

- Aucun agent n'importe ni n'appelle le broker.
- Aucun agent ne reçoit de secret.
- Aucun agent n'importe ni ne modifie le Risk Engine.
- Tous les appels IA passent par `AIGatewayRequest`, donc par le budget dur et la validation structurée du Batch 06.
- Les outils privilégiés sont refusés dans `AgentRegistryEntry`.

## Correctif v2

Le `FakeGateway` des tests du premier ZIP construisait des objets d'audit incomplets par rapport aux contrats stricts du Batch 06.

Correction :
- renseignement de `input_tokens`, `cached_input_tokens`, `output_tokens`, `latency_ms` et `attempt` dans `AIUsageRecord` ;
- renseignement de `attempts` dans `AIGatewayResult`.

Aucun assouplissement n'a été apporté au AI Gateway ni à ses modèles d'audit.

Validation locale ciblée : `5 passed` pour `tests/agents` avec les modèles du Batch 06.

## Intégration

Extraire le ZIP à la racine du projet en autorisant le remplacement des fichiers du premier Batch 07a, puis lancer :

```powershell
uv sync
uv run pytest -q
```

Aucune nouvelle dépendance n'est ajoutée.
