import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import React from "react";
import "./globals.css";
import { AuthProvider } from "../lib/auth-context";
import { AppShell } from "../components/features/navigation/app-shell";

const ibmPlexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-plex-sans",
  display: "swap",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Enterprise CRM — Pipeline y Operaciones B2B",
  description:
    "CRM operativo para equipos comerciales B2B: pipeline multidivisa, cuentas, contactos, seguimiento de tareas y revisión asistida de notas.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className={`h-full ${ibmPlexSans.variable} ${ibmPlexMono.variable}`}>
      <body className="h-full bg-background text-foreground font-sans antialiased">
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
