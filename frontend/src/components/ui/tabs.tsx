"use client";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "@/lib/utils";
export const Tabs = TabsPrimitive.Root;
export const TabsContent = TabsPrimitive.Content;
export function TabsList({className, ...props}: React.ComponentProps<typeof TabsPrimitive.List>) { return <TabsPrimitive.List className={cn("flex gap-1 rounded-lg border border-slate-800 bg-slate-900/60 p-1", className)} {...props}/>; }
export function TabsTrigger({className, ...props}: React.ComponentProps<typeof TabsPrimitive.Trigger>) { return <TabsPrimitive.Trigger className={cn("rounded-md px-3 py-1.5 text-xs font-medium text-slate-400 data-[state=active]:bg-slate-700 data-[state=active]:text-white", className)} {...props}/>; }
