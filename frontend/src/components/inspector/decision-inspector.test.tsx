import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DecisionInspector } from "./decision-inspector";
import type { DashboardDecision } from "@/lib/api/schemas";

const decision: DashboardDecision = {
  system_id:"balanced_v1", opportunity_id:"opp-1", source_snapshot_id:"snap-1", pipeline_status:"COMPLETED", branch_status:"TRADE",
  professor:{direction:"LONG",confidence:0.74,thesis:["breakout confirmé"],counter_evidence:["volume fragile"],invalidation:["retour sous support"]},
  proposal:{proposal_id:"p-1",opportunity_id:"opp-1",source_snapshot_id:"snap-1",system_id:"balanced_v1",symbol:"BTC/EUR",timeframe:"1h",side:"LONG",confidence:0.74,entry_price:"100",stop_price:"95",targets:["110"],expected_rr:"2",market_regime:"trend",expires_at:"2026-09-12T12:00:00Z"},
  risk:{risk_decision_id:"r-1",proposal_id:"p-1",status:"RESIZED",reason_codes:["MAX_RISK_PER_TRADE"],approved_quantity:"0.01",approved_risk_amount:"1",approved_notional:"100",created_at:"2026-09-12T12:00:00Z"},
  failure_code:null,failure_stage:null,failure_message:null
};

describe("DecisionInspector",()=>{
  it("keeps Professor and Risk decisions separate",()=>{render(<DecisionInspector decision={decision}/>);expect(screen.getByText("Trade Proposal")).toBeInTheDocument();expect(screen.getByText("Risk Engine")).toBeInTheDocument();expect(screen.getByText("MAX_RISK_PER_TRADE")).toBeInTheDocument();expect(screen.getByText("breakout confirmé",{exact:false})).toBeInTheDocument()});
});
