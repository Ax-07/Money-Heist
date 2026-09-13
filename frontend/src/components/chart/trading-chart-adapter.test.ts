import { describe, expect, it } from "vitest";
import { markerFor } from "./trading-chart-adapter";

describe("chart event mapping",()=>{
 it("renders Risk as a distinct square marker",()=>{const marker=markerFor({event_id:"1",observed_at:"2026-09-12T12:00:00Z",event_type:"RISK",label:"RESIZED",opportunity_id:null,agent:"risk_engine",phase:"RISK",price:null,details:{}});expect(marker.shape).toBe("square");expect(marker.text).toBe("RISK")});
 it("renders entries below the candle",()=>{const marker=markerFor({event_id:"2",observed_at:"2026-09-12T12:00:00Z",event_type:"ENTRY",label:"Entry",opportunity_id:null,agent:null,phase:null,price:"100",details:{}});expect(marker.position).toBe("belowBar");expect(marker.shape).toBe("arrowUp")});
});
