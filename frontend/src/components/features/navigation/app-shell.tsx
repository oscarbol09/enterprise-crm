"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  BarChart3,
  Building2,
  CheckSquare,
  ClipboardCheck,
  Command,
  KeyRound,
  LogOut,
  Menu,
  Moon,
  Sun,
  TrendingUp,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "../../../lib/auth-context";
import { CommandPalette } from "./command-palette";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, accessToken, isLoading, logout } = useAuth();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [isCommandPaletteOpen, setIsCommandPaletteOpen] = useState(false);
  const [isDarkTheme, setIsDarkTheme] = useState(false);

  const isAuthPage = pathname === "/login";

  const handleToggleTheme = () => {
    const nextDark = !isDarkTheme;
    setIsDarkTheme(nextDark);
    document.documentElement.classList.toggle("dark", nextDark);
  };

  useEffect(() => {
    if (isLoading) return;
    if (!user && !isAuthPage) {
      router.replace("/login");
    } else if (user && isAuthPage) {
      router.replace("/deals");
    }
  }, [isLoading, user, isAuthPage, router]);

  if (isAuthPage) {
    return <div className="min-h-screen w-full bg-background">{children}</div>;
  }

  if (isLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-background text-xs text-muted-foreground">
        Cargando espacio de trabajo...
      </div>
    );
  }

  if (!user) {
    return null;
  }

  const navLinks = [
    { name: "Pipeline", href: "/deals", icon: TrendingUp },
    { name: "Reportes", href: "/reports", icon: BarChart3 },
    { name: "Contactos", href: "/contacts", icon: Users },
    { name: "Empresas", href: "/accounts", icon: Building2 },
    { name: "Tareas", href: "/tasks", icon: CheckSquare },
    { name: "Revisión IA", href: "/ai", icon: ClipboardCheck },
    { name: "Claves API", href: "/settings/llm-credentials", icon: KeyRound },
  ];

  const handleNavigate = (path: string) => {
    router.push(path);
    setIsCommandPaletteOpen(false);
    setMobileMenuOpen(false);
  };

  const handleLogout = async () => {
    await logout();
    router.push("/login");
  };

  return (
    <div className="h-screen w-full bg-background text-foreground antialiased flex flex-col md:flex-row overflow-hidden">
      <CommandPalette
        isOpen={isCommandPaletteOpen}
        authToken={accessToken ?? undefined}
        onClose={() => setIsCommandPaletteOpen(false)}
        onToggle={() => setIsCommandPaletteOpen((prev) => !prev)}
        onNavigate={handleNavigate}
      />

      {/* Mobile Header */}
      <header className="md:hidden flex items-center justify-between p-4 border-b border-border bg-card shrink-0">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-primary text-primary-foreground flex items-center justify-center font-bold text-sm shadow-subtle">
            CRM
          </div>
          <span className="font-semibold text-sm">Enterprise CRM</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setIsCommandPaletteOpen(true)}
            className="p-2 text-muted-foreground hover:text-foreground rounded-md border border-border"
            aria-label="Abrir paleta de comandos"
          >
            <Command className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            className="p-2 text-muted-foreground hover:text-foreground rounded-md border border-border"
            aria-label={mobileMenuOpen ? "Cerrar menú" : "Abrir menú"}
          >
            {mobileMenuOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </header>

      {/* Mobile Backdrop */}
      {mobileMenuOpen && (
        <div
          className="fixed inset-0 z-30 bg-background/70 backdrop-blur-sm md:hidden"
          onClick={() => setMobileMenuOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Persistent Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 md:static flex flex-col w-64 bg-card border-r border-border transition-transform duration-200 ease-in-out shrink-0 ${
          mobileMenuOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
        }`}
        aria-label="Navegación principal"
      >
        <div className="p-5 border-b border-border flex items-center justify-between">
          <Link href="/deals" className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-primary text-primary-foreground flex items-center justify-center font-bold text-sm shadow-subtle">
              CRM
            </div>
            <div className="flex flex-col">
              <span className="font-semibold text-sm tracking-tight leading-tight">Enterprise CRM</span>
              <span className="text-[11px] text-muted-foreground">
                Operaciones Comerciales
              </span>
            </div>
          </Link>
        </div>

        <div className="px-3 pt-3">
          <button
            type="button"
            onClick={() => setIsCommandPaletteOpen(true)}
            className="w-full flex items-center justify-between px-3 py-2 text-xs text-muted-foreground bg-muted/50 hover:bg-muted border border-border rounded-lg transition-colors"
          >
            <span className="flex items-center gap-2">
              <Command className="h-3.5 w-3.5" />
              <span>Buscar o saltar...</span>
            </span>
            <kbd className="font-mono text-[10px] bg-card px-1.5 py-0.5 rounded border border-border">
              ⌘K
            </kbd>
          </button>
        </div>

        <nav className="flex-1 p-3 flex flex-col gap-1 overflow-y-auto">
          {navLinks.map((link) => {
            const Icon = link.icon;
            const isActive = pathname === link.href || pathname?.startsWith(`${link.href}/`);
            return (
              <Link
                key={link.href}
                href={link.href}
                onClick={() => setMobileMenuOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-xs font-medium transition-colors ${
                  isActive
                    ? "bg-primary text-primary-foreground shadow-subtle"
                    : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span>{link.name}</span>
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-border bg-muted/20 text-xs flex items-center justify-between gap-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <Building2 className="h-4 w-4 text-muted-foreground shrink-0" />
            <div className="flex flex-col min-w-0">
              <span className="font-medium text-foreground truncate">{user.full_name}</span>
              <span className="text-[10px] text-muted-foreground truncate">
                {user.tenant_name || user.tenant_slug} · {user.role}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              type="button"
              onClick={handleToggleTheme}
              title={isDarkTheme ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
              aria-label={isDarkTheme ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              {isDarkTheme ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            <button
              type="button"
              onClick={handleLogout}
              title="Cerrar sesión"
              aria-label="Cerrar sesión"
              className="p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>
      </aside>

      <main className="flex-1 flex flex-col min-w-0 overflow-y-auto">{children}</main>
    </div>
  );
}
