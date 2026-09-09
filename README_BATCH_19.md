# Money Heist — Batch 19 — Recruitment Engine

## Résultat

Batch 19 livre un moteur de recrutement d’agents **déterministe, auditable et advisory-only**.

Le candidat est défini et évalué hors `AgentRegistry`, passe par un lifecycle séparé, est confronté à une baseline figée sur Historical Replay/PAPER, puis produit une evidence lineage complète avant tout avis organisationnel.

## Chaîne livrée

```text
Proposal
→ CandidateSpec
→ Lifecycle + Gates
→ BASELINE / WITH_CANDIDATE
→ Historical Replay / PAPER
→ Comparability + OOS
→ Ablation / Reputation / Costs
→ Evidence Package
→ Advisory
→ Transition Plan
→ FRESH / STALE Audit
```

## Avis possibles

- `REJECT`
- `EXTEND`
- `PROBATION`
- `RECOMMEND_PROMOTION`

Aucun de ces avis ne s’applique automatiquement.

## Surface API

```text
GET /api/recruitment/capabilities
mode = ADVISORY_READ_ONLY
```

Aucun endpoint HTTP d’écriture Recruitment n’est livré.

## Invariants

- aucune mutation automatique `AgentRegistry` ;
- aucune promotion automatique ;
- aucun bypass Risk ;
- aucune autorité LIVE candidat ;
- critères pré-enregistrés ;
- preuve promotion OOS ;
- population/budget opérateur-gatés ;
- plans périmés refusés.

## Prochaine étape

**Batch 20 — Task Force Agents**.
