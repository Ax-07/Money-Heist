# Money Heist — Batch 06 — AI Gateway

## Objectif

Ajouter une passerelle IA indépendante des agents et de l'exécution de trading, conforme à la roadmap :

- client IA abstrait ;
- routage de modèle configurable ;
- fallback de route configurable ;
- comptage des tokens ;
- calcul centralisé du coût en EUR ;
- retry borné ;
- Structured Outputs validés par Pydantic ;
- plafond budgétaire dur appliqué avant chaque appel ;
- mock IA permettant les tests sans API et sans coût.

## Fichiers ajoutés

```text
app/intelligence/ai_gateway/
├── __init__.py
├── budget.py
├── client.py
├── errors.py
├── gateway.py
├── mock_client.py
├── models.py
├── openai_client.py
├── pricing.py
└── routing.py

tests/intelligence/
├── test_ai_gateway_budget.py
├── test_ai_gateway_mock.py
├── test_ai_gateway_pricing.py
├── test_ai_gateway_routing.py
└── test_openai_responses_client.py
```

## Décision Batch 06 — Routage modèles

`OPEN-008` reste volontairement configurable : aucun modèle LIVE n'est codé en dur.

Une `ModelRoute` définit :

- `route_id` ;
- provider (`openai` ou `mock`) ;
- `model_id` ;
- prix en EUR / million de tokens ;
- maximum de tokens de sortie ;
- timeout ;
- route de fallback éventuelle.

Ainsi, le choix de modèles et leur tarification peuvent être modifiés par configuration sans modifier la logique métier.

## Sécurité / budget

Le gateway réserve un coût maximal conservateur avant l'appel. La réservation utilise :

- un majorant tokenizer-free du nombre de tokens d'entrée basé sur les octets UTF-8 ;
- le prix d'entrée non-caché ;
- `max_output_tokens` au complet.

Si aucune route de la chaîne de fallback ne rentre dans le budget restant, **aucun appel fournisseur n'est effectué**.

Le coût réel est ensuite recalculé à partir des compteurs du fournisseur et enregistré dans `AIUsageRecord`. Un `AIUsageRecorder` est appelé pour **chaque réponse facturée**, y compris une tentative dont la sortie structurée est ensuite rejetée.

## OpenAI

L'adaptateur utilise directement `POST /v1/responses` via `httpx` afin de ne pas imposer une nouvelle dépendance SDK au projet.

- clé API confinée dans l'adaptateur infrastructure ;
- `store=false` ;
- Structured Outputs via JSON Schema strict ;
- extraction de `input_tokens`, `cached_tokens` et `output_tokens` ;
- erreurs 408/409/425/429/5xx considérées retryables ;
- refus modèle non retryable ;
- aucun secret n'entre dans les modèles métier ni les prompts automatiquement.

## Intégration

1. Extraire le ZIP à la racine du projet.
2. Aucun paquet supplémentaire n'est requis si `httpx` et `pydantic` sont déjà présents (ils le sont dans la stack actuelle des Batchs précédents).
3. Lancer :

```powershell
uv sync
uv run pytest -q
```

4. Le Batch 07a pourra importer les contrats depuis :

```python
from app.intelligence.ai_gateway import AIGateway, AIGatewayRequest
```

## Exemple minimal

```python
from decimal import Decimal

from app.intelligence.ai_gateway import (
    AIBudgetLedger,
    AIGateway,
    ModelPricing,
    ModelRoute,
    ModelRouter,
    OpenAIResponsesClient,
)

route = ModelRoute(
    route_id="professor_default",
    provider="openai",
    model_id="<configured-model-id>",
    pricing=ModelPricing(
        input_per_million_eur=Decimal("<configured-price>"),
        cached_input_per_million_eur=Decimal("<configured-price>"),
        output_per_million_eur=Decimal("<configured-price>"),
    ),
)

router = ModelRouter([route])
budget = AIBudgetLedger("25.00")
client = OpenAIResponsesClient(api_key="<read-from-secret-store-or-env>")
gateway = AIGateway(router=router, clients={"openai": client}, budget=budget)
```

Les valeurs de modèle et de prix sont laissées hors du code de production afin de respecter le routage configurable et d'éviter qu'un tarif périssable devienne une constante métier.
