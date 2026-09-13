import type { AgentTrace } from "@/lib/api/schemas";
export function buildDecisionTrace(traces: AgentTrace[], opportunityId?: string | null) {
  return traces.filter(t => !opportunityId || t.opportunity_id === opportunityId).sort((a,b) => a.sequence-b.sequence);
}
