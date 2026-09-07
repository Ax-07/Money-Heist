# Money Heist — Batch 01 Fondations

Ce dépôt contient les fondations backend du projet Money Heist.

Le Batch 01 implémente uniquement l'infrastructure nécessaire aux lots suivants :
configuration typée, logs structurés, modèles métier de base, FastAPI, santé/readiness,
SQLite, SQLAlchemy, Alembic et tests.

Aucun connecteur exchange, aucun agent IA, aucun Risk Engine et aucun ordre de trading
ne sont implémentés dans ce lot.

## Prérequis

- `uv` installé ;
- Python 3.13 (uv peut l'installer automatiquement si nécessaire).

## Installation

```bash
uv sync
```

Copier ensuite la configuration d'exemple :

### macOS / Linux

```bash
cp .env.example .env
```

### Windows PowerShell

```powershell
Copy-Item .env.example .env
```

## Initialiser la base locale

```bash
uv run python scripts/bootstrap.py
```

Le script applique les migrations Alembic et initialise le runtime système en mode PAPER.

## Lancer l'API

```bash
uv run python scripts/run_dev.py
```

Par défaut : `http://127.0.0.1:8000`

Endpoints disponibles :

- `GET /health` : liveness de l'application ;
- `GET /ready` : disponibilité de la base locale.

## Tests

```bash
uv run pytest
```

Avec couverture :

```bash
uv run pytest --cov=app --cov-report=term-missing
```

## Lint

```bash
uv run ruff check .
uv run ruff format --check .
```

## Sécurité du Batch 01

- `LIVE` est explicitement refusé par la configuration de ce batch ;
- `.env` est ignoré par Git ;
- aucun secret n'est présent dans le code ou les exemples ;
- aucune API d'exchange n'existe encore ;
- les logs sont structurés et n'incluent pas de configuration complète.

## Structure

```text
app/
├── agents/          # frontière réservée aux futurs agents
├── api/             # FastAPI et routes
├── config/          # configuration typée
├── domain/          # modèles métier indépendants des frameworks
├── evaluation/      # frontière réservée
├── intelligence/    # frontière réservée
├── market/          # frontière réservée
├── observability/   # logging/correlation IDs
├── services/        # services applicatifs
├── storage/         # SQLAlchemy / accès DB
└── trading/         # frontière réservée
```

Voir `CHANGELOG_BATCH.md` pour le contenu exact et `docs/10_DECISIONS_ET_CHANGELOG.md`
pour les décisions techniques enregistrées.
