"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, Building2, Lock, Mail, Sparkles, User } from "lucide-react";
import { ApiError } from "../../lib/api-client";
import { useAuth } from "../../lib/auth-context";
import { Button } from "../../components/ui/button";

export default function LoginPage() {
  const router = useRouter();
  const { login, register } = useAuth();

  const [mode, setMode] = useState<"login" | "register">("login");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Login fields
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [tenantSlug, setTenantSlug] = useState("");

  // Register fields
  const [tenantName, setTenantName] = useState("");
  const [adminFullName, setAdminFullName] = useState("");

  const handleTenantNameChange = (value: string) => {
    setTenantName(value);
    const slugified = value
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    setTenantSlug(slugified);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    try {
      if (mode === "login") {
        await login({
          email: email.trim(),
          password,
          tenant_slug: tenantSlug.trim() || undefined,
        });
      } else {
        await register({
          tenant_name: tenantName.trim(),
          tenant_slug: tenantSlug.trim(),
          admin_full_name: adminFullName.trim(),
          admin_email: email.trim(),
          password,
        });
      }
      router.push("/deals");
    } catch (err: unknown) {
      const msg =
        err instanceof ApiError
          ? err.message
          : "No se pudo completar la autenticación. Verifica que el backend esté activo.";
      setError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-background">
      <div className="w-full max-w-md bg-card border border-border rounded-xl shadow-elevated p-6 flex flex-col gap-5">
        <div className="flex items-center gap-3 pb-4 border-b border-border">
          <div className="h-10 w-10 rounded-lg bg-primary text-primary-foreground flex items-center justify-center font-bold text-sm shadow-subtle">
            CRM
          </div>
          <div>
            <h1 className="text-base font-bold text-foreground">Enterprise CRM</h1>
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              <Sparkles className="h-3 w-3 text-primary" /> Aislamiento RLS · BYOK · Copilot IA
            </p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-1 p-1 bg-muted rounded-lg" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "login"}
            onClick={() => {
              setMode("login");
              setError(null);
            }}
            className={`py-2 text-xs font-medium rounded-md transition-colors ${
              mode === "login"
                ? "bg-card text-foreground shadow-subtle"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Iniciar Sesión
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "register"}
            onClick={() => {
              setMode("register");
              setError(null);
            }}
            className={`py-2 text-xs font-medium rounded-md transition-colors ${
              mode === "register"
                ? "bg-card text-foreground shadow-subtle"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            Crear Workspace
          </button>
        </div>

        {error && (
          <div
            role="alert"
            className="flex items-center gap-2 p-3 text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-md"
          >
            <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex flex-col gap-3.5">
          {mode === "register" && (
            <>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="tenant-name" className="text-xs font-medium text-foreground">
                  Nombre de la Organización
                </label>
                <div className="relative">
                  <Building2 className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <input
                    id="tenant-name"
                    type="text"
                    required
                    value={tenantName}
                    onChange={(e) => handleTenantNameChange(e.target.value)}
                    placeholder="Acme Enterprise Corp"
                    className="w-full h-10 pl-9 pr-3 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="admin-name" className="text-xs font-medium text-foreground">
                  Nombre Completo del Administrador
                </label>
                <div className="relative">
                  <User className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
                  <input
                    id="admin-name"
                    type="text"
                    required
                    value={adminFullName}
                    onChange={(e) => setAdminFullName(e.target.value)}
                    placeholder="Elena Mendoza"
                    className="w-full h-10 pl-9 pr-3 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
              </div>
            </>
          )}

          <div className="flex flex-col gap-1.5">
            <label htmlFor="tenant-slug" className="text-xs font-medium text-foreground">
              Slug del Workspace{" "}
              {mode === "login" && (
                <span className="text-muted-foreground font-normal">(opcional si correo es único)</span>
              )}
            </label>
            <input
              id="tenant-slug"
              type="text"
              required={mode === "register"}
              pattern="^[a-z0-9-]+$"
              value={tenantSlug}
              onChange={(e) => setTenantSlug(e.target.value.toLowerCase())}
              placeholder="acme-corp"
              className="w-full h-10 px-3 bg-background border border-border rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="login-email" className="text-xs font-medium text-foreground">
              Correo Electrónico
            </label>
            <div className="relative">
              <Mail className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
              <input
                id="login-email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="admin@acme.io"
                className="w-full h-10 pl-9 pr-3 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="login-password" className="text-xs font-medium text-foreground">
              Contraseña
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
              <input
                id="login-password"
                type="password"
                required
                minLength={mode === "register" ? 8 : 1}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="w-full h-10 pl-9 pr-3 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>

          <Button type="submit" variant="primary" size="md" isLoading={isSubmitting} className="mt-1">
            {mode === "login" ? "Entrar al Workspace" : "Crear Workspace y Entrar"}
          </Button>
        </form>

        <div className="p-3 bg-muted/40 border border-border rounded-lg text-[11px] text-muted-foreground leading-relaxed">
          Entorno local con seed demo (<code className="font-mono">python -m src.core.seed</code>):{" "}
          <span className="font-mono text-foreground">acme-corp</span> ·{" "}
          <span className="font-mono text-foreground">admin@acme.io</span>
        </div>
      </div>
    </div>
  );
}
