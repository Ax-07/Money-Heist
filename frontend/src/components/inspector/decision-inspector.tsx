import React from "react";
import type { DashboardDecision } from "@/lib/api/schemas";
import { StatusBadge } from "@/components/ui/badge";
import { formatMoney } from "@/lib/utils";
export function DecisionInspector({ decision }: { decision?: DashboardDecision | null }) {
  if (!decision)
    return (
      <div className="p-5 text-sm text-slate-500">Sélectionnez une décision ou un marker pour inspecter la chaîne.</div>
    );
  return (
    <div className="space-y-5 p-5 text-sm">
      <section>
        <div className="panel-title mb-2">Décision</div>
        <div className="flex gap-2">
          <StatusBadge value={decision.professor?.direction ?? decision.branch_status} />
          {decision.professor && (
            <span className="font-mono text-slate-400">conf. {decision.professor.confidence.toFixed(2)}</span>
          )}
        </div>
      </section>
      <section>
        <div className="panel-title mb-2">Pourquoi cette décision ?</div>
        {decision.professor?.thesis.map((x, i) => (
          <p key={i} className="mb-1 text-slate-300">
            • {x}
          </p>
        ))}
        {!decision.professor && <p className="text-slate-500">Non fourni par le backend.</p>}
      </section>
      {decision.professor?.counter_evidence?.length ? (
        <section>
          <div className="panel-title mb-2">Contre-évidence</div>
          {decision.professor.counter_evidence.map((x, i) => (
            <p key={i} className="mb-1 text-amber-200/80">
              • {x}
            </p>
          ))}
        </section>
      ) : null}
      {decision.proposal && (
        <section>
          <div className="panel-title mb-2">Trade Proposal</div>
          <div className="grid grid-cols-2 gap-2 font-mono text-xs">
            <span className="text-slate-500">Entry</span>
            <span>{formatMoney(decision.proposal.entry_price)}</span>
            <span className="text-slate-500">Stop</span>
            <span>{formatMoney(decision.proposal.stop_price)}</span>
            <span className="text-slate-500">Targets</span>
            <span>{decision.proposal.targets.join(", ")}</span>
            <span className="text-slate-500">RR</span>
            <span>{decision.proposal.expected_rr}</span>
          </div>
        </section>
      )}
      {decision.risk && (
        <section>
          <div className="panel-title mb-2">Risk Engine</div>
          <StatusBadge value={decision.risk.status} />
          <div className="mt-2 text-xs text-slate-400">
            {decision.risk.reason_codes.length ? decision.risk.reason_codes.join(" · ") : "Aucun reason_code"}
          </div>
          <div className="mt-2 font-mono text-xs">
            qty {decision.risk.approved_quantity} · risk {decision.risk.approved_risk_amount}
          </div>
        </section>
      )}
      {decision.failure_message && (
        <section className="rounded-lg border border-rose-900/50 bg-rose-950/20 p-3 text-rose-200">
          {decision.failure_stage}: {decision.failure_message}
        </section>
      )}
    </div>
  );
}
