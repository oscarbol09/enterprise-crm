import type { Metadata } from "next";
import React from "react";
import "./globals.css";
import { AuthProvider } from "../lib/auth-context";
import { AppShell } from "../components/features/navigation/app-shell";

export const metadata: Metadata = {
  title: "Enterprise CRM — Multi-Tenant & Agentic AI Platform",
  description:
    "CRM empresarial multi-tenant con PostgreSQL Forced RLS, bóveda BYOK AES-256-GCM y copiloto de IA con aprobación Human-in-the-Loop.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" className="h-full">
      <body className="h-full bg-background text-foreground antialiased">
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
