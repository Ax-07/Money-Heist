# Intégration — Batch 15 — Activation LIVE 100 €

## 1. Baseline

Le ZIP doit être extrait directement à la racine de :

```text
E:\0 money heist
```

La baseline attendue est exactement le commit Batch 14 :

```text
10622f0da59cbb5ba03a66dcdf2bfeba919baf53
feat(live): complete Batch 14 secure Live Broker
```

Avant extraction :

```powershell
cd "E:\0 money heist"
git status --short
git rev-parse HEAD
```

Le working tree doit être propre et `git rev-parse HEAD` doit retourner le SHA ci-dessus.

## 2. Installation et migration

```powershell
cd "E:\0 money heist"
uv sync
uv run alembic upgrade head
uv run alembic current
```

La révision courante attendue après migration est `0002`.

La migration ajoute uniquement les tables LIVE durables :

- `live_orders` ;
- `live_fills` ;
- `live_audit_events` ;
- `live_reconciliation_state` ;
- `live_safety_state`.

## 3. Suite standard

```powershell
uv run pytest -q
```

Aucun credential réel n'est nécessaire. Aucun test standard ne doit appeler Kraken privé ni soumettre/annuler un ordre réel.

## 4. Configuration d'éligibilité LIVE

La configuration par défaut reste PAPER et fail-closed.

Pour pouvoir exécuter un preflight LIVE, l'opérateur doit explicitement définir au minimum :

```powershell
$env:MONEY_HEIST_APP_ENV="production"
$env:MONEY_HEIST_RUNTIME_MODE="LIVE"
$env:MONEY_HEIST_LIVE_ENVIRONMENT="kraken_spot_eur"
$env:MONEY_HEIST_LIVE_SYSTEM_ID="balanced_v1"
```

Ces variables rendent seulement la configuration **éligible au preflight**. Elles n'arment pas le LIVE.

## 5. Paramètres volontairement non inventés

### Profil Balanced

Le dépôt ne contient toujours pas de limites Balanced LIVE numériques résolues. Copier localement le template uniquement lorsqu'une décision externe a fixé les valeurs existantes :

```powershell
Copy-Item ".\config\live_balanced_profile.template.json" ".\data\live_balanced_profile.local.json"
$env:MONEY_HEIST_LIVE_RISK_PROFILE_FILE="E:\0 money heist\data\live_balanced_profile.local.json"
```

Tant que des champs requis restent `null`, le preflight doit retourner `RISK_PROFILE_INCOMPLETE`.

### Market Data Batch 13

Le Batch 13 a volontairement laissé les timeframes et seuils de fraîcheur configurables. Définir uniquement des valeurs déjà validées pour le système :

```powershell
$env:MONEY_HEIST_LIVE_MARKET_MAX_AGE_SECONDS="<valeur-validée>"
$env:MONEY_HEIST_LIVE_METADATA_MAX_AGE_SECONDS="<valeur-validée>"
$env:MONEY_HEIST_LIVE_TIMEFRAMES="<timeframes-validés-séparés-par-virgules>"
```

Aucune valeur par défaut Batch 15 n'est fournie.

## 6. Credentials Kraken

Définir les credentials uniquement dans la frontière d'environnement du processus, jamais dans Git, `.env.example`, les prompts ou les logs :

```powershell
$env:MONEY_HEIST_KRAKEN_API_KEY="<secret-local>"
$env:MONEY_HEIST_KRAKEN_API_SECRET="<secret-local>"
```

Leur présence seule n'autorise rien.

Le preflight vérifie `GetApiKeyInfo` et exige exactement :

- `query-funds` ;
- `query-open-trades` ;
- `query-closed-trades` ;
- `modify-trades` ;
- `close-trades`.

Toute permission supplémentaire détectée bloque, notamment toute permission de retrait ou de gestion d'adresse de retrait.

## 7. Initialiser le verrou sécurité durable

Après migration, l'absence d'état sécurité est volontairement `UNKNOWN` et bloque le preflight.
L'opérateur doit d'abord initialiser explicitement l'état durable, sans armer le LIVE :

```powershell
uv run python -m app.trading.live.safety_cli status
uv run python -m app.trading.live.safety_cli clear --reason "preflight initial validé" --confirm "CLEAR LIVE SAFETY balanced_v1"
```

Pour bloquer immédiatement les nouvelles entrées :

```powershell
uv run python -m app.trading.live.safety_cli stop-new-trades --reason "operator stop"
```

Pour le mode incident :

```powershell
uv run python -m app.trading.live.safety_cli emergency --reason "incident"
```

Ces commandes ne soumettent et n'annulent aucun ordre Kraken. L'état sécurité est durable ; l'armement LIVE, lui, ne l'est jamais.

## 8. Preflight opérateur

Après migration et configuration :

```powershell
uv run python -m app.trading.live.preflight_cli
```

ou :

```powershell
.\scripts\live_preflight.ps1
```

La commande :

- effectue uniquement des lectures Kraken ;
- rafraîchit Market Data ;
- vérifie les permissions de la clé ;
- exige une réconciliation de démarrage ;
- vérifie la persistance/audit ;
- produit du JSON structuré ;
- retourne code processus `0` pour `READY`, `2` pour `BLOCKED` ;
- **n'arme pas le LIVE** ;
- ne peut pas appeler `AddOrder` ou `CancelOrder` grâce au wrapper de capability read-only.

Transmettre la sortie complète du preflight avant toute étape d'activation réelle.

## 9. Important : aucun premier ordre dans Batch 15 tant que la validation locale n'est pas confirmée

Même un résultat `READY` ne soumet aucun ordre. L'armement opérateur est process-local, explicite et non câblé à la commande de preflight. Un redémarrage recrée toujours `LIVE_DISABLED` et impose une nouvelle réconciliation/preflight.

## 10. Nettoyage des secrets de la session PowerShell

Après le preflight :

```powershell
Remove-Item Env:MONEY_HEIST_KRAKEN_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:MONEY_HEIST_KRAKEN_API_SECRET -ErrorAction SilentlyContinue
```

Ne jamais committer un fichier local contenant ces valeurs.
