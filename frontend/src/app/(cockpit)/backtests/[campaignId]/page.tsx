import { BacktestDetail } from "@/features/backtests/backtest-detail";
export default async function BacktestDetailPage({params}:{params:Promise<{campaignId:string}>}){const {campaignId}=await params;return <BacktestDetail campaignId={campaignId}/>}
