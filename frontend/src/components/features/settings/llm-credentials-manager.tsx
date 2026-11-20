"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Cpu,
  Eye,
  EyeOff,
  KeyRound,
  Plus,
  ShieldCheck,
  Sparkles,
  Trash2,
} from "lucide-react";
import { LLMCredential } from "../../../types/crm";
import {
  ApiError,
  fetchLLMCredentials,
  registerLLMCredential,
  revokeLLMCredential,
} from "../../../lib/api-client";
import { Badge } from "../../ui/badge";
import { Button } from "../../ui/button";

interface LLMCredentialsManagerProps {
  authToken?: string;
  userRole?: string;
}

export function LLMCredentialsManager({ authToken, userRole }: LLMCredentialsManagerProps) {
  const isNonAdmin = Boolean(userRole && userRole !== "admin");
  const [credentials, setCredentials] = useState<LLMCredential[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(!isNonAdmin);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [pendingRevokeId, setPendingRevokeId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(
    null
  );

  const [provider, setProvider] = useState<"gemini" | "claude" | "openai">("gemini");
  const [rawKeyInput, setRawKeyInput] = useState<string>("");
  const [showKeyTyping, setShowKeyTyping] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadCredentials = useCallback(async () => {
    if (isNonAdmin) {
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    try {
      const data = await fetchLLMCredentials(authToken);
      setCredentials(data);
    } catch (err: unknown) {
      const message =
        err instanceof ApiError
          ? err.message
          : "Error al cargar credenciales del tenant.";
      setFeedback({ type: "error", message });
    } finally {
      setIsLoading(false);
    }
  }, [authToken, isNonAdmin]);

  useEffect(() => {
    if (isNonAdmin) {
      return;
    }
    let active = true;
    async function initCredentials() {
      try {
        const data = await fetchLLMCredentials(authToken);
        if (active) setCredentials(data);
      } catch (err: unknown) {
        if (active) {
          const message =
            err instanceof ApiError
              ? err.message
              : "Error al cargar credenciales del tenant.";
          setFeedback({ type: "error", message });
        }
      } finally {
        if (active) setIsLoading(false);
      }
    }
    void initCredentials();
    return () => {
      active = false;
    };
  }, [authToken, isNonAdmin]);

  const handleSaveCredential = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setFeedback(null);

    const trimmedKey = rawKeyInput.trim();
    if (!trimmedKey) {
      setFormError("Debe ingresar una API key válida.");
      return;
    }
    if (trimmedKey.length < 12) {
      setFormError("La API key debe contener al menos 12 caracteres.");
      return;
    }

    setIsSubmitting(true);
    try {
      await registerLLMCredential({ provider, raw_api_key: trimmedKey }, authToken);
      setRawKeyInput("");
      setShowKeyTyping(false);
      setFeedback({
        type: "success",
        message: `Credencial de ${provider.toUpperCase()} cifrada con éxito mediante AES-256-GCM.`,
      });
      await loadCredentials();
    } catch (err: unknown) {
      const message =
        err instanceof ApiError ? err.message : "Error al registrar la clave.";
      setFeedback({ type: "error", message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRevokeCredential = async (credentialId: string, providerName: string) => {
    setFeedback(null);
    try {
      await revokeLLMCredential(credentialId, authToken);
      setPendingRevokeId(null);
      setFeedback({
        type: "success",
        message: `Credencial de ${providerName.toUpperCase()} revocada.`,
      });
      await loadCredentials();
    } catch (err: unknown) {
      const message =
        err instanceof ApiError ? err.message : "Error al revocar la credencial.";
      setFeedback({ type: "error", message });
    }
  };

  return (
    <div className="flex flex-col gap-6 max-w-3xl w-full">
      <div className="flex flex-col gap-1 pb-4 border-b border-border">
        <div className="flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-primary" aria-hidden="true" />
          <h1 className="text-lg font-semibold text-foreground">
            Configuración de IA Agéntica — BYOK (Bring Your Own Key)
          </h1>
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          Configure las credenciales de IA propias de su organización. Todas las claves se cifran en
          reposo mediante <strong className="text-foreground">AES-256-GCM</strong> con AAD por
          tenant y nunca se devuelven en texto plano.
        </p>
      </div>

      {isNonAdmin && (
        <div
          role="alert"
          className="flex items-center gap-2 p-3.5 rounded-md text-xs border bg-warning/10 text-foreground border-warning/30"
        >
          <AlertCircle className="h-4 w-4 text-warning shrink-0" aria-hidden="true" />
          <span>
            Tu rol actual (<strong>{userRole}</strong>) es de solo consulta operativa. Solo un
            usuario con rol <strong>admin</strong> puede gestionar la bóveda BYOK.
          </span>
        </div>
      )}

      {feedback && (
        <div
          role="alert"
          className={`flex items-center justify-between p-3 rounded-md text-xs border ${
            feedback.type === "success"
              ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border-emerald-500/20"
              : "bg-destructive/10 text-destructive border-destructive/20"
          }`}
        >
          <div className="flex items-center gap-2">
            {feedback.type === "success" ? (
              <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
            ) : (
              <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
            )}
            <span>{feedback.message}</span>
          </div>
          <button
            type="button"
            onClick={() => setFeedback(null)}
            className="text-[11px] font-medium underline hover:opacity-80"
          >
            Descartar
          </button>
        </div>
      )}

      {!isNonAdmin && (
        <form
          onSubmit={handleSaveCredential}
          className="flex flex-col gap-4 p-5 bg-card border border-border rounded-xl shadow-card"
          aria-label="Registrar nueva API key"
        >
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-foreground">Registrar o Actualizar API Key</h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="provider-select" className="text-xs font-medium text-foreground">
                Proveedor de IA
              </label>
              <select
                id="provider-select"
                value={provider}
                onChange={(e) => setProvider(e.target.value as "gemini" | "claude" | "openai")}
                className="h-10 px-3 bg-background border border-border rounded-md text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="gemini">Google Gemini</option>
                <option value="claude">Anthropic Claude</option>
                <option value="openai">OpenAI</option>
              </select>
            </div>

            <div className="flex flex-col gap-1.5 sm:col-span-2">
              <label htmlFor="raw-key-input" className="text-xs font-medium text-foreground">
                API Key Privada <span className="text-destructive">*</span>
              </label>
              <div className="relative">
                <input
                  id="raw-key-input"
                  type={showKeyTyping ? "text" : "password"}
                  autoComplete="off"
                  placeholder="Pegue aquí la clave (ej. AIzaSy..., sk-ant-..., sk-proj-...)"
                  value={rawKeyInput}
                  onChange={(e) => {
                    setRawKeyInput(e.target.value);
                    setFormError(null);
                  }}
                  className={`w-full h-10 pl-3 pr-10 bg-background border rounded-md text-sm text-foreground font-mono focus:outline-none focus:ring-2 focus:ring-primary ${
                    formError ? "border-destructive focus:ring-destructive" : "border-border"
                  }`}
                />
                <button
                  type="button"
                  onClick={() => setShowKeyTyping((prev) => !prev)}
                  className="absolute right-3 top-2.5 text-muted-foreground hover:text-foreground transition-colors"
                  title={showKeyTyping ? "Ocultar clave" : "Mostrar clave al escribir"}
                  aria-label={
                    showKeyTyping ? "Ocultar clave mientras escribe" : "Mostrar clave mientras escribe"
                  }
                >
                  {showKeyTyping ? (
                    <EyeOff className="h-4 w-4" aria-hidden="true" />
                  ) : (
                    <Eye className="h-4 w-4" aria-hidden="true" />
                  )}
                </button>
              </div>
              {formError && (
                <span role="alert" className="text-[11px] text-destructive flex items-center gap-1">
                  <AlertCircle className="h-3 w-3" /> {formError}
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between pt-2">
            <span className="text-[11px] text-muted-foreground">
              Solo se conservan los últimos 4 caracteres para identificación visual.
            </span>
            <Button type="submit" variant="primary" size="sm" isLoading={isSubmitting} className="gap-1.5">
              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Guardar Credencial</span>
            </Button>
          </div>
        </form>
      )}

      <div className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-foreground">Credenciales del Tenant</h2>

        {isLoading ? (
          <div className="p-6 border border-border rounded-xl bg-card text-center text-xs text-muted-foreground animate-pulse">
            Consultando bóveda de credenciales del tenant...
          </div>
        ) : credentials.length === 0 ? (
          <div className="flex flex-col items-center justify-center p-8 border border-dashed border-border rounded-xl bg-card text-center gap-2">
            <Cpu className="h-8 w-8 text-muted-foreground/60" aria-hidden="true" />
            <h3 className="text-sm font-medium text-foreground">No hay API keys personalizadas</h3>
            <p className="text-xs text-muted-foreground max-w-sm">
              Su organización utiliza actualmente las credenciales del sistema central si están
              configuradas.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {credentials.map((cred) => (
              <div
                key={cred.id}
                className="flex flex-wrap items-center justify-between gap-3 p-4 bg-card border border-border rounded-lg shadow-subtle hover:bg-muted/20 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                    <Sparkles className="h-4 w-4" aria-hidden="true" />
                  </div>
                  <div className="flex flex-col">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm capitalize text-foreground">
                        {cred.provider}
                      </span>
                      {cred.is_active ? (
                        <Badge variant="success" className="text-[10px] py-0 px-1.5">
                          Activa (BYOK)
                        </Badge>
                      ) : (
                        <Badge variant="destructive" className="text-[10px] py-0 px-1.5">
                          Revocada
                        </Badge>
                      )}
                    </div>
                    <span className="text-xs font-mono text-muted-foreground">
                      ••••••••••••••••••••{cred.key_last_four}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-muted-foreground hidden sm:inline">
                    {new Date(cred.created_at).toLocaleDateString()}
                  </span>
                  {cred.is_active &&
                    (pendingRevokeId === cred.id ? (
                      <div className="flex items-center gap-1.5">
                        <Button
                          variant="destructive"
                          size="sm"
                          onClick={() => handleRevokeCredential(cred.id, cred.provider)}
                          className="h-8 px-2.5 text-xs"
                        >
                          Confirmar
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setPendingRevokeId(null)}
                          className="h-8 px-2 text-xs"
                        >
                          Cancelar
                        </Button>
                      </div>
                    ) : (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setPendingRevokeId(cred.id)}
                        className="text-destructive hover:bg-destructive/10 h-8 px-2 text-xs gap-1"
                        title="Revocar credencial"
                      >
                        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>Revocar</span>
                      </Button>
                    ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
