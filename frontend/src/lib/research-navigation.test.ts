import { describe, expect, it } from "vitest";

import { evidenceToOverlaySelection } from "./research-navigation";

describe("research evidence navigation", () => {
  it("uses the backend causal navigation timestamp without replacing identity", () => {
    const selection = evidenceToOverlaySelection({
      schema_version: "money-heist.decision-quality-evidence-ref.v1",
      ref_id: "ref-1",
      subject_type: "FUNNEL_STAGE",
      source_record_id: "stage-record-1",
      source_record_fingerprint: "a".repeat(64),
      opportunity_id: "opp-1",
      stage_record_id: "stage-record-1",
      stage: "PROFESSOR_FINAL",
      observed_at: "2026-01-01T12:00:00Z",
      navigation_at: "2026-01-01T12:00:01Z",
      object_type: "ProfessorFinal",
      object_id: "stage-record-1",
      label: "PROFESSOR_FINAL · LONG",
      details: { stage: "PROFESSOR_FINAL", result: "LONG" },
    });

    expect(selection.timestamp).toBe("2026-01-01T12:00:00Z");
    expect(selection.navigationTimestamp).toBe("2026-01-01T12:00:01Z");
    expect(selection.opportunityId).toBe("opp-1");
    expect(selection.objectId).toBe("stage-record-1");
  });
});
