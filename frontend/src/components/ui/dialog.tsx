"use client";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export function DialogContent({children}: {children: React.ReactNode}) {
  return <DialogPrimitive.Portal>
    <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm" />
    <DialogPrimitive.Content className="fixed left-1/2 top-1/2 z-50 max-h-[88vh] w-[min(960px,94vw)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-xl border border-slate-700 bg-slate-950 shadow-2xl">
      {children}<DialogPrimitive.Close className="absolute right-4 top-4 rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-white" aria-label="Fermer"><X className="h-4 w-4"/></DialogPrimitive.Close>
    </DialogPrimitive.Content>
  </DialogPrimitive.Portal>;
}
export const DialogTitle = DialogPrimitive.Title;
