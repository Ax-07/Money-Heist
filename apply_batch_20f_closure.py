from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent

MIRRORED_DOCS = (
    "00_ETAT_ACTUEL_POST_BATCH_15.md",
    "03_SYSTEME_AGENTS.md",
    "06_EVALUATION_ET_APPRENTISSAGE.md",
    "08_API_ET_MODELES_DE_DONNEES.md",
    "09_ROADMAP_DEVELOPPEMENT.md",
    "10_DECISIONS_ET_CHANGELOG.md",
    "11_BACKTESTING_ET_REPLAY_HISTORIQUE.md",
)

DOC_ONLY = (
    "01_PROJECT_MASTER.md",
    "02_ARCHITECTURE.md",
    "07_SECURITE_ET_OPERATIONS.md",
)

STATE_DOCUMENT = """# Money Heist — État actuel post-Batch 20

**Statut :** référence d’alignement active  
**Date :** 2026-09-09  
**Nom de fichier conservé :** `00_ETAT_ACTUEL_POST_BATCH_15.md` pour continuité des références  
existantes  
**Baseline d’entrée Batch 20 :** `572cd07` —  
`feat(recruitment): complete Batch 19 Recruitment Engine`

---

## 1. État intégré

Les Batchs 01 à 20 sont livrés. Le **Batch 20 — Task Force dynamique** ajoute une couche
multi-agents temporaire, déterministe, auditable et advisory-only pour les analyses complexes ou
exceptionnelles.

Le chemin intégré est maintenant :

```text
TaskForceTriggerSignal explicite
→ TaskForceRequest
→ policy opérateur + gates population/capability/budget
→ composition registry-only + réputation multidimensionnelle
→ provenance / stale audit
→ TaskForcePlan PLANNED
→ autorisation opérateur
→ TaskForceExecutionContract
→ compute gate par membre
→ AI Gateway
→ TaskForceMemberAnalysis
→ agrégation provenance-preserving
→ TaskForceReport
→ bridge grounded vers The Professor
→ orchestration principale inchangée
→ Palermo principal
→ Professor final
→ TradeProposal éventuel
→ Risk Engine déterministe
```

La Task Force ne devient jamais une autorité de trading.

---

## 2. Composition et lifecycle

Une Task Force est temporaire et bornée par :
- une mission et une question explicites ;
- une date d’expiration ;
- une policy opérateur de population, coût, appels et retries ;
- une allowlist tools qui ne peut pas dépasser celle du registre ;
- des rôles/capabilities explicitement demandés ;
- des fingerprints déterministes.

La composition sélectionne uniquement des agents réellement présents dans `AgentRegistry`. Un
candidat Recruitment Batch 19 ne peut pas être utilisé tant qu’il n’est pas devenu une entrée
opérationnelle du registre par un processus externe autorisé.

Le lifecycle est :

```text
PLANNED
→ APPROVED_FOR_EXECUTION
→ RUNNING
→ COMPLETED / FAILED / CANCELLED

PLANNED / APPROVED
→ BLOCKED / CANCELLED
```

Le passage vers `APPROVED_FOR_EXECUTION` exige une autorisation opérateur explicite.

---

## 3. Réputation et composition

La réputation Batch 18 est consommée comme preuve multidimensionnelle. Aucun score magique de
réputation ou de consensus n’est calculé.

Les priorités de composition sont explicites et opérateur-owned : état, dimensions de réputation,
capabilities et taille cible. Un changement du registre, des capabilities, des preuves de réputation
ou des policies rend la composition `STALE` et impose une recomposition.

---

## 4. Exécution IA

Chaque membre passe par :

```text
TaskForceComputeQuote
→ TaskForce compute gate
→ AIGateway.generate_structured()
→ TaskForceMemberAnalysis
```

Le budget Task Force est un sous-plafond. Il ne remplace jamais le hard budget du Batch 06 AI
Gateway. Les appels providers directs sont interdits.

En cas de compute gate refusée, dépassement de quote, erreur Gateway, identité incohérente ou
comptabilité de coût non fiable, l’exécution s’arrête fail-closed.

---

## 5. Agrégation et Red Team

L’agrégation conserve les contributions individuelles : réponses, findings, evidence refs,
incertitudes, questions de suivi, coûts et latences.

```text
aggregation_method = PROVENANCE_PRESERVING_NO_SEMANTIC_VOTE
semantic_consensus_computed = False
aggregate_confidence_computed = False
```

Si un Red Team temporaire est requis, il doit déjà être couvert par la composition et exécuté comme
membre. Cette contribution ne remplace pas le `PalermoReview` du pipeline principal.

---

## 6. Intégration orchestration

Le déclenchement ne repose sur aucun seuil caché. Un `TaskForceTriggerSignal` explicite est
requis et
la policy opérateur décide quels triggers sont activés.

Un `TaskForceReport` consommé par l’orchestration est revalidé contre l’opportunité, le snapshot, la
fenêtre temporelle et son fingerprint. Il est exposé uniquement au Professor final comme nouvelle
source grounded `task_force_report.*`.

Il n’est pas injecté dans Palermo et ne court-circuite aucune étape du pipeline historique.

---

## 7. Evaluation et replay

Batch 20e fournit :
- coût réel total et par agent ;
- appels, attempts, latence et taille de Task Force ;
- comptage findings/incertitudes/questions ;
- deltas Trading Net / Economic Net / drawdown uniquement avec baseline comparable ;
- campagne Historical Replay `BASELINE` vs `WITH_TASK_FORCE` ;
- runner et PaperBroker isolés par twin ;
- replay PAPER-only ;
- seal de reproductibilité et audit `FRESH / STALE`.

Sans baseline comparable, les métriques économiques marginales restent `UNAVAILABLE`.

---

## 8. Invariants d’autorité

Les contrats Batch 20 préservent systématiquement :

```text
advisory_only = True
auto_execute = False
registry_mutation = False
risk_authority = False
live_authority = False
```

L’autorité Risk reste le moteur déterministe existant. L’armement LIVE Batch 15 reste séparé et
explicite.

---

## 9. Frontière avec Recruitment

Recruitment décide si un candidat mérite une progression organisationnelle. Task Force compose et
exécute temporairement des agents déjà disponibles dans le registre.

Aucune Task Force ne peut transformer un candidat Recruitment en agent opérationnel, modifier son
lifecycle ou contourner les gates de promotion Batch 19.

---

## 10. Documentation de référence

Pour l’état courant, lire en priorité :
1. le code intégré sur `main` ;
2. ce document ;
3. `09_ROADMAP_DEVELOPPEMENT.md` ;
4. `10_DECISIONS_ET_CHANGELOG.md` ;
5. `11_BACKTESTING_ET_REPLAY_HISTORIQUE.md` ;
6. les addenda Batch 20 des documents de domaine sous `docs/`.

Le layout historique reste inchangé : `01_PROJECT_MASTER.md`, `02_ARCHITECTURE.md` et
`07_SECURITE_ET_OPERATIONS.md` restent docs-only.

---

## 11. Prochaine étape

La prochaine étape de roadmap est **Batch 21 — Master Portfolio Layer**.

Elle ne doit pas être confondue avec une autorisation de premier ordre réel : les bloqueurs LIVE
existants, les campagnes historiques/PAPER/SHADOW et le preflight restent applicables.
"""

MASTER_ADDENDUM = """
## Addendum Batch 20 — Task Force dynamique

Batch 20 implémente le concept de Task Force temporaire décrit dans cette spécification.

Une Task Force :
- sélectionne uniquement des agents présents dans `AgentRegistry` ;
- possède mission, question, expiration, budget, appels et allowlist explicites ;
- applique des gates population/capability/compute avant exécution ;
- utilise la réputation Batch 18 sans score global caché ;
- exige une autorisation opérateur avant exécution ;
- appelle l’IA uniquement via le Batch 06 AI Gateway ;
- agrège sans vote majoritaire sémantique ;
- produit un `TaskForceReport` advisory-only ;
- peut être évaluée par replay PAPER baseline vs treatment ;
- n’accorde aucune mutation de registre, autorité Risk ou autorité LIVE.

Le rapport Task Force peut devenir une source grounded du Professor final. Palermo principal reste
une étape distincte de l’orchestration et le Risk Engine déterministe conserve son autorité
constitutionnelle.
"""

ARCHITECTURE_ADDENDUM = """
## Addendum Batch 20 — Architecture Task Force

Le package `app.task_force` est un sibling fonctionnel de Recruitment et non un sous-système de
trading. Il dépend des contrats agents/AI Gateway/evaluation mais ne possède aucune dépendance vers
le broker LIVE ou une API exchange d’ordre.

Architecture logique :

```text
orchestration trigger bridge
→ app.task_force models/lifecycle/gates
→ composition + provenance/stale
→ execution contract/runtime via AI Gateway
→ aggregation
→ orchestration report bridge
```

La composition reste registry-only. Les candidats Batch 19 non inscrits au registre ne sont pas
sélectionnables. Les stale guards entourent composition et replay afin qu’un changement matériel
impose une régénération plutôt qu’une réutilisation silencieuse.
"""

AGENTS_ADDENDUM = """
## Addendum Batch 20 — Task Force Agents implémentés

Les agents temporaires sont désormais implémentés comme **assignations temporaires d’agents du
registre**, et non comme créations autonomes d’identités IA.

Les contraintes centrales sont :
- états autorisés explicitement par policy ;
- agents Core sélectionnables seulement si allowlistés par la policy ;
- `DISABLED` jamais sélectionnable ;
- capability coverage explicite ;
- tool allowlist sous-ensemble de `AgentRegistryEntry.allowed_tools` ;
- budget/appels/retries bornés ;
- expiration obligatoire ;
- Red Team couvert par un agent `red_team` du registre lorsqu’il est requis ;
- aucune mutation automatique d’`AgentState` ou du registre.

La réputation utilisée en composition reste multidimensionnelle et peut prioriser explicitement OOS,
Economic Net marginal, réduction de drawdown, coût ou latence. L’ordre des dimensions est fourni par
la policy de composition ; aucun score composite implicite n’est introduit.
"""

EVALUATION_ADDENDUM = """
## Addendum Batch 20 — Evaluation des Task Forces

`app.evaluation.task_force` mesure séparément une Task Force sans modifier `AgentMetrics` :
- coût réel total et par agent ;
- attempts et usage records ;
- latence et durée wall-clock ;
- taille/completion ;
- présence Red Team ;
- findings, incertitudes et questions de suivi.

Les deltas marginaux Trading Net / Economic Net / drawdown ne deviennent `AVAILABLE` qu’avec deux
runs explicitement comparables. Sans baseline, ils restent `UNAVAILABLE`.

`app.evaluation.task_force_replay` produit des twins PAPER `BASELINE` / `WITH_TASK_FORCE` sur le
Historical Replay existant. `task_force_replay_audit` scelle ensuite plan, business fingerprints,
report, comparaison et évaluation, puis retourne `FRESH` ou `STALE`.

Aucun résultat d’évaluation n’applique automatiquement une transition d’agent, une mutation de
registre ou une action de trading.
"""

SECURITY_ADDENDUM = """
## Addendum Batch 20 — Frontières sécurité Task Force

La Task Force est fail-closed et ne constitue jamais une nouvelle autorité LIVE.

Interdictions structurelles :
- pas de secrets exchange/provider dans les outils membres ;
- pas de broker/exchange/risk_engine/shell/filesystem/withdraw/live_order dans les allowlists ;
- pas d’appel provider direct hors AI Gateway ;
- pas de mutation `AgentRegistry` ;
- pas de transition Recruitment automatique ;
- pas de modification des paramètres constitutionnels de risque ;
- pas de création directe d’ordre ou de `TradeProposal` depuis l’agrégateur ;
- replay Task Force exclusivement PAPER.

L’autorisation opérateur du lifecycle Task Force autorise seulement l’exécution analytique de cette
Task Force. Elle ne vaut ni armement LIVE ni autorisation Risk.
"""

API_ADDENDUM = """
## Addendum Batch 20 — Contrats Task Force

Contrats publics principaux de `app.task_force` :
- `TaskForceRequest`, `TaskForceOperatorPolicy`, `TaskForcePlan` ;
- `TaskForceLifecycleRecord`, `TaskForceTransitionPlan` ;
- `TaskForcePlanGateDecision`, `TaskForceComputeDecision` ;
- `TaskForceCompositionPolicy`, `TaskForceCompositionResult` ;
- `TaskForceCompositionProvenance`, `TaskForceCompositionAudit` ;
- `TaskForceCompositionClosure` ;
- `TaskForceExecutionContract`, `TaskForceMemberExecutionSpec` ;
- `TaskForceMultiMemberExecution` et records d’usage ;
- `TaskForceReport` et contributions agrégées.

Bridges publics orchestration :
- `TaskForceTriggerSignal`, `TaskForceInvocationPolicy`, `TaskForceInvocationDecision` ;
- `TaskForceReportIntegration` ;
- `evaluate_task_force_trigger()` ;
- `prepare_task_force_report_for_orchestration()`.

Contrats publics Evaluation :
- `TaskForceRunOutcome`, `TaskForceOutcomeComparison`, `TaskForceEvaluationReport` ;
- `TaskForceReplayPlan`, `TaskForceReplayCampaignReport`, `TaskForceReplayExecutor` ;
- `TaskForceReplaySeal`, `TaskForceReplayAudit` et audit `FRESH / STALE`.

Les contrats d’autorité utilisent des littéraux/flags fail-closed (`registry_mutation=False`,
`risk_authority=False`, `live_authority=False`).
"""

BACKTEST_ADDENDUM = """
## Addendum Batch 20 — Replay Task Force

Batch 20e réutilise le moteur Batch 16 pour comparer une opportunité avec et sans Task Force :

```text
BASELINE
vs
WITH_TASK_FORCE
```

Les deux variantes partagent dataset, rôle, période et configuration matérielle, mais possèdent des
`run_id` distincts via des `execution_assumptions` réservées. Chaque variante reçoit un runner et un
PaperBroker isolés.

La baseline doit produire zéro artefact Task Force. Le treatment doit produire exactement un
`TaskForceReport` et son exécution correspondante pour l’opportunité ciblée. Le report et son
agrégation doivent rester dans les bornes temporelles du replay.

Un seal final capture les business fingerprints baseline/treatment ainsi que les fingerprints Task
Force. Toute dérive matérielle rend l’audit `STALE`. Le mécanisme reste PAPER-only, y compris
lorsque
le mode IA du backtest utilise un fournisseur réel pour l’évaluation.
"""

ADR_027 = """
### ADR-027 — Task Force temporaire registry-only, operator-gated et advisory-only

**Date :** 2026-09-09  
**Statut :** ACCEPTED

**Décision :**
Le Batch 20 implémente les Task Forces comme compositions temporaires d’agents déjà présents dans
`AgentRegistry`. Elles possèdent une mission étroite, une expiration, des policies explicites de
population/coût/appels/retries et une allowlist tools bornée par le registre.

La composition est déterministe et peut utiliser les preuves de réputation multidimensionnelles
Batch 18 sans score magique. Toute exécution exige un lifecycle approuvé par l’opérateur, une gate
Task Force et le hard budget du Batch 06 AI Gateway.

L’agrégation conserve la provenance et n’effectue aucun vote sémantique ou moyenne de confiance. Le
rapport Task Force peut être injecté comme source grounded du Professor final, sans être transmis au
Palermo principal ni contourner le pipeline existant.

L’évaluation historique compare `BASELINE` et `WITH_TASK_FORCE` sur des runtimes PAPER isolés et
scelle les résultats par fingerprints/audit `FRESH / STALE`.

**Conséquences :**
- un candidat Recruitment absent du registre n’est pas sélectionnable ;
- aucune Task Force ne crée ou promeut automatiquement un agent ;
- aucun provider IA n’est appelé hors AI Gateway ;
- aucun rapport Task Force ne crée directement de `TradeProposal` ;
- Palermo principal et le Risk Engine déterministe restent des frontières séparées ;
- aucune autorité LIVE n’est dérivée d’une autorisation Task Force ;
- les preuves économiques marginales nécessitent des twins replay comparables.
"""

DOC_CHANGELOG_V08 = """
### v0.8 — 2026-09-09 — Batch 20 Task Force dynamique
- contrats, lifecycle et gates Task Force temporaires ;
- composition registry-only avec capabilities explicites et réputation Batch 18 ;
- provenance, fingerprints et stale detection ;
- exécution multi-membres exclusivement via AI Gateway et compute gate ;
- agrégation provenance-preserving avec Red Team optionnel ;
- trigger bridge explicite et intégration grounded dans le Professor final ;
- évaluation coût/latence et comparaison économique baseline/treatment ;
- Historical Replay PAPER `BASELINE` / `WITH_TASK_FORCE` ;
- replay seal et audit `FRESH / STALE` ;
- exports publics Task Force/Evaluation/Orchestration ;
- ADR-027 ajouté.
"""

BATCH_CHANGELOG = """
# Batch 20 — Task Force dynamique — clôture

## Livré

- contrats Task Force temporaires avec mission, expiration, budget, appels et allowlist ;
- lifecycle `PLANNED → APPROVED_FOR_EXECUTION → RUNNING → terminal` ;
- gates population/capability/compute fail-closed ;
- composition déterministe registry-only ;
- réputation Batch 18 multidimensionnelle sans score magique ;
- provenance de composition, fingerprints et stale detection ;
- clôture de composition vers `TaskForcePlan` toujours `PLANNED` ;
- contrats d’exécution et appels multi-membres via AI Gateway uniquement ;
- comptabilité coût/attempts/latence et arrêt fail-closed ;
- agrégation provenance-preserving, sans vote sémantique ;
- Red Team temporaire optionnel sans remplacer Palermo principal ;
- trigger bridge explicite, sans seuil de complexité inventé ;
- intégration `TaskForceReport` grounded dans le Professor final ;
- Evaluation Task Force et contribution économique uniquement avec baseline comparable ;
- Historical Replay twins `BASELINE` / `WITH_TASK_FORCE` PAPER-only ;
- replay seal et audit `FRESH / STALE` ;
- exports publics consolidés.

## Frontières de clôture

Batch 20 ne :
- sélectionne pas un candidat Recruitment absent d'`AgentRegistry` ;
- ne modifie pas automatiquement le registre ou l’état d’un agent ;
- ne remplace pas le hard budget AI Gateway ;
- n’appelle pas directement un provider IA ;
- ne crée pas directement un `TradeProposal` depuis une Task Force ;
- ne contourne pas Palermo principal ni le Risk Engine ;
- n’accorde aucune autorité LIVE ;
- n’invente aucune métrique économique lorsqu’une baseline comparable est absente.

## Suite

La prochaine étape de roadmap est **Batch 21 — Master Portfolio Layer**. Les bloqueurs LIVE
existants
restent indépendants et doivent toujours être satisfaits avant tout premier ordre réel.
"""

ROADMAP_BATCH20 = """## 23. Batch 20 — Task Force dynamique

**État : livré et validé.**

Livré :
- contrats temporaires, expiration et mission ;
- lifecycle opérateur-gaté ;
- policies population, budget, appels, retries et tools ;
- composition registry-only par rôle/capability ;
- réputation multidimensionnelle Batch 18 ;
- provenance, fingerprints et stale detection ;
- exécution multi-membres via AI Gateway ;
- agrégation provenance-preserving et Red Team optionnel ;
- trigger bridge explicite ;
- `TaskForceReport` grounded dans le Professor final ;
- Evaluation coût/latence et economic lift conditionnel ;
- Historical Replay PAPER baseline vs treatment ;
- seal de reproductibilité et audit `FRESH / STALE` ;
- exports publics consolidés.

Non livré volontairement :
- création/promotion automatique d’agents ;
- mutation automatique d’`AgentRegistry` ;
- score magique de consensus/réputation ;
- autorité Risk ou LIVE ;
- ordre ou `TradeProposal` direct depuis la Task Force.

---"""

ROADMAP_NEXT = """## 28. Prochaine action

1. Clôturer Batch 20 avec tests complets, consolidation documentaire et commit dédié.
2. Conserver les campagnes historiques/PAPER/SHADOW comme preuves et maintenir le LIVE non armé
   tant que ses gates propres ne sont pas satisfaites.
3. Démarrer **Batch 21 — Master Portfolio Layer** sans réutiliser l’autorisation Task Force comme
   autorité de portefeuille ou autorité LIVE.
4. Définir toute future allocation multi-crews comme une couche déterministe/opérateur-gatée avec
   un Master Risk Engine séparé de la logique analytique des agents.
"""

EVAL_LAZY_EXPORTS = """_BATCH20_LAZY_EXPORTS = {
    "TaskForceRunOutcome": (".task_force", "TaskForceRunOutcome"),
    "TaskForceOutcomeComparison": (".task_force", "TaskForceOutcomeComparison"),
    "TaskForceEvaluationReport": (".task_force", "TaskForceEvaluationReport"),
    "compare_task_force_outcomes": (".task_force", "compare_task_force_outcomes"),
    "evaluate_task_force": (".task_force", "evaluate_task_force"),
    "TaskForceReplayCampaignReport": (
        ".task_force_replay",
        "TaskForceReplayCampaignReport",
    ),
    "TaskForceReplayExecutor": (".task_force_replay", "TaskForceReplayExecutor"),
    "TaskForceReplayPlan": (".task_force_replay", "TaskForceReplayPlan"),
    "TaskForceReplayRuntime": (".task_force_replay", "TaskForceReplayRuntime"),
    "TaskForceReplayRuntimeFactory": (
        ".task_force_replay",
        "TaskForceReplayRuntimeFactory",
    ),
    "TaskForceReplayVariant": (".task_force_replay", "TaskForceReplayVariant"),
    "TaskForceReplayVariantExecution": (
        ".task_force_replay",
        "TaskForceReplayVariantExecution",
    ),
    "TaskForceReplayVariantKind": (
        ".task_force_replay",
        "TaskForceReplayVariantKind",
    ),
    "build_task_force_replay_plan": (
        ".task_force_replay",
        "build_task_force_replay_plan",
    ),
    "TaskForceReplayAudit": (".task_force_replay_audit", "TaskForceReplayAudit"),
    "TaskForceReplayAuditStatus": (
        ".task_force_replay_audit",
        "TaskForceReplayAuditStatus",
    ),
    "TaskForceReplaySeal": (".task_force_replay_audit", "TaskForceReplaySeal"),
    "assert_task_force_replay_fresh": (
        ".task_force_replay_audit",
        "assert_task_force_replay_fresh",
    ),
    "audit_task_force_replay": (
        ".task_force_replay_audit",
        "audit_task_force_replay",
    ),
    "seal_task_force_replay": (".task_force_replay_audit", "seal_task_force_replay"),
}

_LAZY_EXPORTS = {**_BATCH18B_LAZY_EXPORTS, **_BATCH20_LAZY_EXPORTS}
"""

EVAL_PUBLIC_NAMES = (
    "TaskForceRunOutcome",
    "TaskForceOutcomeComparison",
    "TaskForceEvaluationReport",
    "compare_task_force_outcomes",
    "evaluate_task_force",
    "TaskForceReplayCampaignReport",
    "TaskForceReplayExecutor",
    "TaskForceReplayPlan",
    "TaskForceReplayRuntime",
    "TaskForceReplayRuntimeFactory",
    "TaskForceReplayVariant",
    "TaskForceReplayVariantExecution",
    "TaskForceReplayVariantKind",
    "build_task_force_replay_plan",
    "TaskForceReplayAudit",
    "TaskForceReplayAuditStatus",
    "TaskForceReplaySeal",
    "assert_task_force_replay_fresh",
    "audit_task_force_replay",
    "seal_task_force_replay",
)

TASK_FORCE_RUNTIME_PUBLIC_NAMES = (
    "TaskForceExecutionFailure",
    "TaskForceExecutionFailureStage",
    "TaskForceExecutionRunStatus",
    "TaskForceExecutionUsageSnapshot",
    "TaskForceMemberComputeQuote",
    "TaskForceMemberExecutionRecord",
    "TaskForceMemberUsageSnapshot",
    "TaskForceMultiMemberExecution",
    "TaskForceStructuredGateway",
    "execute_task_force_members",
    "task_force_compute_quote_fingerprint",
    "zero_task_force_execution_usage",
)

ORCH_IMPORTS = """from .task_force_report import (
    TaskForceReportIntegration,
    prepare_task_force_report_for_orchestration,
    task_force_report_fingerprint,
)
from .task_force_trigger import (
    TaskForceInvocationDecision,
    TaskForceInvocationPolicy,
    TaskForceInvocationStatus,
    TaskForceTriggerSignal,
    evaluate_task_force_trigger,
    task_force_invocation_policy_fingerprint,
    task_force_trigger_signal_fingerprint,
)
"""

ORCH_PUBLIC_NAMES = (
    "TaskForceReportIntegration",
    "prepare_task_force_report_for_orchestration",
    "task_force_report_fingerprint",
    "TaskForceInvocationDecision",
    "TaskForceInvocationPolicy",
    "TaskForceInvocationStatus",
    "TaskForceTriggerSignal",
    "evaluate_task_force_trigger",
    "task_force_invocation_policy_fingerprint",
    "task_force_trigger_signal_fingerprint",
)


def _read(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    return text, newline


def _write(path: Path, text: str, newline: str) -> None:
    normalized = text.rstrip() + "\n"
    if newline == "\r\n":
        normalized = normalized.replace("\n", "\r\n")
    path.write_bytes(normalized.encode("utf-8"))


def _upsert_block(text: str, *, key: str, body: str) -> str:
    start = f"<!-- {key}_START -->"
    end = f"<!-- {key}_END -->"
    block = f"{start}\n\n{body.strip()}\n\n{end}"
    if start in text or end in text:
        pattern = re.compile(
            rf"{re.escape(start)}.*?{re.escape(end)}",
            flags=re.DOTALL,
        )
        if len(pattern.findall(text)) != 1:
            raise RuntimeError(f"{key}: malformed or duplicate marker block")
        return pattern.sub(block, text, count=1)
    return text.rstrip() + "\n\n" + block + "\n"


def _replace_section(text: str, *, start_heading: str, next_heading: str, body: str) -> str:
    pattern = re.compile(
        rf"{re.escape(start_heading)}.*?(?=\n{re.escape(next_heading)})",
        flags=re.DOTALL,
    )
    matches = pattern.findall(text)
    if len(matches) != 1:
        raise RuntimeError(
            f"section {start_heading!r}: expected one section, found {len(matches)}"
        )
    return pattern.sub(body.rstrip() + "\n", text, count=1)


def _insert_before_once(text: str, anchor: str, block: str, *, label: str) -> str:
    if block.strip() in text:
        return text
    count = text.count(anchor)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(anchor, block.rstrip() + "\n\n" + anchor, 1)


def _add_all_names(text: str, names: tuple[str, ...], *, label: str) -> str:
    start = text.find("__all__ = [")
    if start < 0:
        raise RuntimeError(f"{label}: __all__ opening bracket not found")
    marker = "\n]\n"
    end = text.find(marker, start)
    if end < 0:
        raise RuntimeError(f"{label}: __all__ closing bracket not found")
    public_block = text[start:end]
    missing = [name for name in names if f'"{name}"' not in public_block]
    if not missing:
        return text
    addition = "".join(f'    "{name}",\n' for name in missing)
    return text[:end] + "\n" + addition.rstrip("\n") + text[end:]


def _patch_task_force_init(text: str) -> str:
    return _add_all_names(
        text,
        TASK_FORCE_RUNTIME_PUBLIC_NAMES,
        label="app.task_force",
    )


def _patch_evaluation_init(text: str) -> str:
    if "_BATCH20_LAZY_EXPORTS = {" not in text:
        anchor = "\n\ndef __getattr__(name: str):\n"
        count = text.count(anchor)
        if count != 1:
            raise RuntimeError("app.evaluation: __getattr__ anchor not found uniquely")
        text = text.replace(anchor, "\n\n" + EVAL_LAZY_EXPORTS.rstrip() + anchor, 1)
    old = "    target = _BATCH18B_LAZY_EXPORTS.get(name)\n"
    new = "    target = _LAZY_EXPORTS.get(name)\n"
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise RuntimeError("app.evaluation: lazy export lookup anchor missing")
    return _add_all_names(text, EVAL_PUBLIC_NAMES, label="app.evaluation")


def _patch_orchestration_init(text: str) -> str:
    if "from .task_force_report import (" not in text:
        anchor = "__all__ = [\n"
        count = text.count(anchor)
        if count != 1:
            raise RuntimeError("orchestration: __all__ anchor not found uniquely")
        text = text.replace(anchor, ORCH_IMPORTS.rstrip() + "\n\n" + anchor, 1)
    return _add_all_names(text, ORCH_PUBLIC_NAMES, label="orchestration")


def _patch_roadmap(text: str) -> str:
    text = text.replace("**Version :** 0.2", "**Version :** 0.3", 1)
    old_status = "**Statut :** Roadmap active — réalignée post-Batch 15"
    new_status = "**Statut :** Roadmap active — réalignée post-Batch 20"
    if old_status in text:
        text = text.replace(old_status, new_status, 1)
    elif new_status not in text:
        raise RuntimeError("roadmap status anchor missing")
    if "## 23. Batch 20 — Task Force Agents" in text:
        text = _replace_section(
            text,
            start_heading="## 23. Batch 20 — Task Force Agents",
            next_heading="## 24. Batch 21 — Master Portfolio Layer",
            body=ROADMAP_BATCH20,
        )
    elif "## 23. Batch 20 — Task Force dynamique" not in text:
        raise RuntimeError("roadmap Batch 20 section missing")
    pattern = re.compile(r"## 28\. Prochaine action.*\Z", flags=re.DOTALL)
    if len(pattern.findall(text)) != 1:
        raise RuntimeError("roadmap next-action section not found uniquely")
    return pattern.sub(ROADMAP_NEXT.rstrip() + "\n", text, count=1)


def _patch_decisions(text: str) -> str:
    if "### ADR-027 — Task Force temporaire registry-only" not in text:
        text = _insert_before_once(
            text,
            "## 4. Décisions ouvertes",
            ADR_027,
            label="ADR-027",
        )
    if "### v0.8 — 2026-09-09 — Batch 20 Task Force dynamique" not in text:
        anchor = "## 5. Changelog documentation\n"
        count = text.count(anchor)
        if count != 1:
            raise RuntimeError("documentation changelog anchor missing")
        text = text.replace(
            anchor,
            anchor + "\n" + DOC_CHANGELOG_V08.rstrip() + "\n\n",
            1,
        )
    text = text.replace("**Version :** 0.7", "**Version :** 0.8", 1)
    return text


def _require_paths() -> None:
    required = [
        ROOT / "app" / "task_force" / "__init__.py",
        ROOT / "app" / "evaluation" / "__init__.py",
        ROOT / "app" / "services" / "orchestration" / "__init__.py",
        ROOT / "CHANGELOG_BATCH.md",
    ]
    required.extend(ROOT / name for name in MIRRORED_DOCS)
    required.extend(ROOT / "docs" / name for name in MIRRORED_DOCS)
    required.extend(ROOT / "docs" / name for name in DOC_ONLY)
    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    if missing:
        raise SystemExit("Missing Batch 20f closure paths: " + ", ".join(missing))


def _verify_mirrors() -> None:
    for name in MIRRORED_DOCS:
        root_text, _ = _read(ROOT / name)
        docs_text, _ = _read(ROOT / "docs" / name)
        if root_text != docs_text:
            raise RuntimeError(f"documentation mirror diverged before Batch 20f: {name}")


def _plan_document_updates() -> dict[Path, str]:
    updates: dict[Path, str] = {}

    state_paths = (
        ROOT / "00_ETAT_ACTUEL_POST_BATCH_15.md",
        ROOT / "docs" / "00_ETAT_ACTUEL_POST_BATCH_15.md",
    )
    for path in state_paths:
        updates[path] = STATE_DOCUMENT

    addenda = {
        "03_SYSTEME_AGENTS.md": ("BATCH20_AGENTS", AGENTS_ADDENDUM),
        "06_EVALUATION_ET_APPRENTISSAGE.md": ("BATCH20_EVALUATION", EVALUATION_ADDENDUM),
        "08_API_ET_MODELES_DE_DONNEES.md": ("BATCH20_API", API_ADDENDUM),
        "11_BACKTESTING_ET_REPLAY_HISTORIQUE.md": ("BATCH20_REPLAY", BACKTEST_ADDENDUM),
    }
    for name, (key, body) in addenda.items():
        for path in (ROOT / name, ROOT / "docs" / name):
            text, _ = _read(path)
            updates[path] = _upsert_block(text, key=key, body=body)

    for name, key, body in (
        ("01_PROJECT_MASTER.md", "BATCH20_MASTER", MASTER_ADDENDUM),
        ("02_ARCHITECTURE.md", "BATCH20_ARCHITECTURE", ARCHITECTURE_ADDENDUM),
        ("07_SECURITE_ET_OPERATIONS.md", "BATCH20_SECURITY", SECURITY_ADDENDUM),
    ):
        path = ROOT / "docs" / name
        text, _ = _read(path)
        updates[path] = _upsert_block(text, key=key, body=body)

    roadmap_paths = (
        ROOT / "09_ROADMAP_DEVELOPPEMENT.md",
        ROOT / "docs" / "09_ROADMAP_DEVELOPPEMENT.md",
    )
    for path in roadmap_paths:
        text, _ = _read(path)
        updates[path] = _patch_roadmap(text)

    decision_paths = (
        ROOT / "10_DECISIONS_ET_CHANGELOG.md",
        ROOT / "docs" / "10_DECISIONS_ET_CHANGELOG.md",
    )
    for path in decision_paths:
        text, _ = _read(path)
        updates[path] = _patch_decisions(text)

    changelog = ROOT / "CHANGELOG_BATCH.md"
    text, _ = _read(changelog)
    updates[changelog] = _upsert_block(
        text,
        key="BATCH20_CLOSURE",
        body=BATCH_CHANGELOG,
    )
    return updates


def _plan_code_updates() -> dict[Path, str]:
    updates: dict[Path, str] = {}
    patches = (
        (ROOT / "app" / "task_force" / "__init__.py", _patch_task_force_init),
        (ROOT / "app" / "evaluation" / "__init__.py", _patch_evaluation_init),
        (
            ROOT / "app" / "services" / "orchestration" / "__init__.py",
            _patch_orchestration_init,
        ),
    )
    for path, patch in patches:
        text, _ = _read(path)
        updates[path] = patch(text)
    return updates


def main() -> None:
    _require_paths()
    _verify_mirrors()

    updates = {**_plan_code_updates(), **_plan_document_updates()}

    # All anchors and mirror checks succeed before the first write.
    changed: list[str] = []
    for path, new_text in updates.items():
        old_text, newline = _read(path)
        if old_text != new_text.rstrip() + "\n":
            _write(path, new_text, newline)
            changed.append(str(path.relative_to(ROOT)))

    _verify_mirrors()

    print("Batch 20f closure applied:")
    for item in changed:
        print(f"- {item}")
    if not changed:
        print("- no changes (already applied)")


if __name__ == "__main__":
    main()
