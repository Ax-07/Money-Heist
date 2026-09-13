import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Money Heist — Trading Cockpit",
  description: "Cockpit officiel d'observabilité, replay et audit Money Heist"
};

export default function RootLayout({children}: {children: React.ReactNode}) {
  return <html lang="fr" className="dark"><body><Providers>{children}</Providers></body></html>;
}
