"use client";
import { Sidebar } from "./sidebar";
import { MobileSidebar } from "./mobile-sidebar";
import { Topbar } from "./topbar";
import { SettingsDialog } from "@/components/settings/settings-dialog";
export function AppShell({children}:{children:React.ReactNode}){return <div className="flex min-h-screen bg-slate-950"><Sidebar/><MobileSidebar/><div className="min-w-0 flex-1"><Topbar/><main className="grid-bg h-[calc(100vh-4rem)] overflow-auto p-3 md:p-5">{children}</main></div><SettingsDialog/></div>}
