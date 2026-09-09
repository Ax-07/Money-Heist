# Manifeste — Batch 19 — Recruitment Engine

## Baseline d’entrée

`96b2288` — `feat(evaluation): complete Batch 18 reputation and ablation`

## Code ajouté — Recruitment

- `app/recruitment/__init__.py`
- `app/recruitment/models.py`
- `app/recruitment/lifecycle.py`
- `app/recruitment/gates.py`
- `app/recruitment/campaign.py`
- `app/recruitment/campaign_execution.py`
- `app/recruitment/evidence_gate.py`
- `app/recruitment/ablation_bridge.py`
- `app/recruitment/candidate_reputation.py`
- `app/recruitment/evidence_package.py`
- `app/recruitment/advisory.py`
- `app/recruitment/advisory_transition.py`
- `app/recruitment/advisory_audit.py`
- `app/recruitment/api.py`

## API

- `app/api/routes/recruitment.py` — ajouté ;
- `app/api/router.py` — modifié pour inclure le router Recruitment.

## Tests

Le dossier `tests/recruitment/` couvre contrats, lifecycle, gates, campagnes, exécution, provenance/OOS, bridge Batch 18, réputation/coûts, evidence package, advisory, transition planning, audit stale/fresh, API, documentation et clôture.

## Documentation suivie à la racine et modifiée

- `00_ETAT_ACTUEL_POST_BATCH_15.md`
- `03_SYSTEME_AGENTS.md`
- `06_EVALUATION_ET_APPRENTISSAGE.md`
- `08_API_ET_MODELES_DE_DONNEES.md`
- `09_ROADMAP_DEVELOPPEMENT.md`
- `10_DECISIONS_ET_CHANGELOG.md`
- `11_BACKTESTING_ET_REPLAY_HISTORIQUE.md`
- `CHANGELOG_BATCH.md`

## Documentation canonique sous `docs/`

- `docs/00_ETAT_ACTUEL_POST_BATCH_15.md`
- `docs/01_PROJECT_MASTER.md`
- `docs/02_ARCHITECTURE.md`
- `docs/03_SYSTEME_AGENTS.md`
- `docs/06_EVALUATION_ET_APPRENTISSAGE.md`
- `docs/07_SECURITE_ET_OPERATIONS.md`
- `docs/08_API_ET_MODELES_DE_DONNEES.md`
- `docs/09_ROADMAP_DEVELOPPEMENT.md`
- `docs/10_DECISIONS_ET_CHANGELOG.md`
- `docs/11_BACKTESTING_ET_REPLAY_HISTORIQUE.md`

## Documents Batch 19 ajoutés

- `README_BATCH_19.md`
- `INTEGRATION_BATCH_19.md`
- `MANIFEST_BATCH_19.md`
- `CHANGELOG_BATCH_19F.md`
- `README_BATCH_19F.md`
- `README_BATCH_19A_STEP1.md` / `CHANGELOG_BATCH_19A_STEP1.md`
- `README_BATCH_19A_STEP2.md` / `CHANGELOG_BATCH_19A_STEP2.md`
- `README_BATCH_19A_STEP3.md` / `CHANGELOG_BATCH_19A_STEP3.md`
- `README_BATCH_19B_STEP1.md` / `CHANGELOG_BATCH_19B_STEP1.md`
- `README_BATCH_19B_STEP1_HOTFIX.md` / `CHANGELOG_BATCH_19B_STEP1_HOTFIX.md`
- `README_BATCH_19B_STEP2.md` / `CHANGELOG_BATCH_19B_STEP2.md`
- `README_BATCH_19B_STEP3.md` / `CHANGELOG_BATCH_19B_STEP3.md`
- `README_BATCH_19C_STEP1.md` / `CHANGELOG_BATCH_19C_STEP1.md`
- `README_BATCH_19C_STEP2.md` / `CHANGELOG_BATCH_19C_STEP2.md`
- `README_BATCH_19C_STEP3.md` / `CHANGELOG_BATCH_19C_STEP3.md`
- `README_BATCH_19D_STEP1.md` / `CHANGELOG_BATCH_19D_STEP1.md`
- `README_BATCH_19D_STEP2.md` / `CHANGELOG_BATCH_19D_STEP2.md`
- `README_BATCH_19D_STEP3.md` / `CHANGELOG_BATCH_19D_STEP3.md`
- `README_BATCH_19E_STEP1.md` / `CHANGELOG_BATCH_19E_STEP1.md`
- `README_BATCH_19E_STEP2.md` / `CHANGELOG_BATCH_19E_STEP2.md`

## Fichiers à ne pas versionner à la racine

`01_PROJECT_MASTER.md`, `02_ARCHITECTURE.md` et `07_SECURITE_ET_OPERATIONS.md` ne font pas partie du layout Git historique et **ne doivent pas être versionnés à la racine**. Leurs versions canoniques sont sous `docs/`.

## Hors périmètre

Ne pas embarquer avec le commit Batch 19 les fichiers untracked préexistants tels que datasets, scripts de synchronisation, ZIP de données, helpers Batch 16 ou le fichier au nom corrompu issu d’un ancien terminal.
