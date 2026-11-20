"use client";

import React, { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  AlertCircle,
  CheckCircle2,
  RefreshCw,
  Search,
  ShieldAlert,
  Sparkles,
  XCircle,
} from "lucide-react";
import {
  AIProposal,
  Contact,
  Deal,
  InteractionSummarizeResponse,
  SemanticSearchResult,
} from "../../types/crm";
import {
  ApiError,
  approveAIProposal,
  fetchAIProposals,
  fetchContacts,
  fetchDeals,
  rejectAIProposal,
  runSemanticSearch,
  summarizeInteraction,
} from "../../lib/api-client";
import { useAuth } from "../../lib/auth-context";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";

function AICopilotWorkspaceContent() {
  const searchParams = useSearchParams();
  const { accessToken, user } = useAuth();

  const [contacts, setContacts] = useState<Contact[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [proposals, setProposals] = useState<AIProposal[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Summarizer form
  const [contactId, setContactId] = useState("");
  const [dealId, setDealId] = useState("");
  const [interactionType, setInteractionType] = useState<"meeting" | "call" | "email" | "note">(
    "meeting"
  );
  const [notes, setNotes] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [summaryResult, setSummaryResult] = useState<InteractionSummarizeResponse | null>(null);

  // Rejection modal
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  // Semantic search
  const [semanticQuery, setSemanticQuery] = useState("");
  const [semanticResults, setSemanticResults] = useState<SemanticSearchResult[]>([]);
  const [semanticSource, setSemanticSource] = useState<string | null>(null);
  const [isSearching, setIsSearching] = useState(false);

  const loadWorkspace = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [cList, dList, pList] = await Promise.all([
        fetchContacts(accessToken ?? undefined),
        fetchDeals(accessToken ?? undefined),
        fetchAIProposals(accessToken ?? undefined),
      ]);
      setContacts(cList);
      setDeals(dList);
      setProposals(pList);

      const paramContact = searchParams.get("contactId");
      const paramDeal = searchParams.get("dealId");
      if (paramContact) {
        setContactId(paramContact);
      } else if (cList.length > 0 && !contactId) {
        setContactId(cList[0].id);
      }
      if (paramDeal) setDealId(paramDeal);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Error al cargar el panel de Copilot IA.");
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, contactId, searchParams]);

  useEffect(() => {
    let active = true;
    async function initWorkspace() {
      try {
        const [cList, dList, pList] = await Promise.all([
          fetchContacts(accessToken ?? undefined),
          fetchDeals(accessToken ?? undefined),
          fetchAIProposals(accessToken ?? undefined),
        ]);
        if (!active) return;
        setContacts(cList);
        setDeals(dList);
        setProposals(pList);

        const paramContact = searchParams.get("contactId");
        const paramDeal = searchParams.get("dealId");
        if (paramContact) {
          setContactId(paramContact);
        } else if (cList.length > 0) {
          setContactId((prev) => prev || cList[0].id);
        }
        if (paramDeal) setDealId(paramDeal);
      } catch (err: unknown) {
        if (active) {
          setError(
            err instanceof ApiError ? err.message : "Error al cargar el panel de Copilot IA."
          );
        }
      } finally {
        if (active) setIsLoading(false);
      }
    }
    void initWorkspace();
    return () => {
      active = false;
    };
  }, [accessToken, searchParams]);

  const handleSummarize = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!contactId || notes.trim().length < 10) return;
    setIsAnalyzing(true);
    setError(null);
    try {
      const res = await summarizeInteraction(
        {
          contact_id: contactId,
          deal_id: dealId || undefined,
          raw_notes_or_transcript: notes.trim(),
          interaction_type: interactionType,
        },
        accessToken ?? undefined
      );
      setSummaryResult(res);
      await loadWorkspace();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Error al invocar el copiloto IA.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleApproveProposal = async (id: string) => {
    setError(null);
    try {
      await approveAIProposal(id, accessToken ?? undefined);
      await loadWorkspace();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Error al aprobar propuesta.");
    }
  };

  const handleRejectSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rejectingId || rejectReason.trim().length < 3) return;
    setError(null);
    try {
      await rejectAIProposal(rejectingId, rejectReason.trim(), accessToken ?? undefined);
      setRejectingId(null);
      setRejectReason("");
      await loadWorkspace();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Error al rechazar propuesta.");
    }
  };

  const handleSemanticSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (semanticQuery.trim().length < 2) return;
    setIsSearching(true);
    setError(null);
    try {
      const res = await runSemanticSearch(semanticQuery.trim(), 5, accessToken ?? undefined);
      setSemanticResults(res.results);
      setSemanticSource(res.source);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Error en búsqueda vectorial.");
    } finally {
      setIsSearching(false);
    }
  };

  const canReviewProposals = user?.role === "admin" || user?.role === "sales_manager";

  return (
    <div className="flex flex-col gap-6 p-6 max-w-6xl w-full mx-auto">
      <div className="flex items-center justify-between pb-4 border-b border-border">
        <div>
          <h1 className="text-xl font-bold text-foreground flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-primary" />
            Copilot Agéntico &amp; Gobernanza Human-in-the-Loop
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Analiza transcripciones con protección XML/HTML, revisa propuestas antes de mutar el
            CRM y busca semánticamente con pgvector.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={loadWorkspace} isLoading={isLoading} className="gap-1.5">
          <RefreshCw className="h-3.5 w-3.5" />
          <span>Actualizar</span>
        </Button>
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 p-3 text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-md"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Interaction Summarizer */}
        <section className="p-5 bg-card border border-border rounded-xl shadow-card flex flex-col gap-4">
          <h2 className="text-sm font-semibold text-foreground">
            1. Resumir Interacción y Proponer Acciones
          </h2>

          <form onSubmit={handleSummarize} className="flex flex-col gap-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <label htmlFor="ai-contact" className="text-xs font-medium">
                  Contacto <span className="text-destructive">*</span>
                </label>
                <select
                  id="ai-contact"
                  required
                  value={contactId}
                  onChange={(e) => setContactId(e.target.value)}
                  className="h-9 px-2 bg-background border border-border rounded-md text-xs"
                >
                  <option value="">Selecciona un contacto...</option>
                  {contacts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.first_name} {c.last_name} ({c.email})
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-1">
                <label htmlFor="ai-deal" className="text-xs font-medium">
                  Oportunidad (opcional)
                </label>
                <select
                  id="ai-deal"
                  value={dealId}
                  onChange={(e) => setDealId(e.target.value)}
                  className="h-9 px-2 bg-background border border-border rounded-md text-xs"
                >
                  <option value="">Sin deal asociado</option>
                  {deals.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.title}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex flex-col gap-1">
              <label htmlFor="ai-type" className="text-xs font-medium">
                Tipo de Interacción
              </label>
              <select
                id="ai-type"
                value={interactionType}
                onChange={(e) =>
                  setInteractionType(e.target.value as "meeting" | "call" | "email" | "note")
                }
                className="h-9 px-2 bg-background border border-border rounded-md text-xs"
              >
                <option value="meeting">Reunión</option>
                <option value="call">Llamada</option>
                <option value="email">Correo</option>
                <option value="note">Nota Interna</option>
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label htmlFor="ai-notes" className="text-xs font-medium">
                Notas o Transcripción (mínimo 10 caracteres)
              </label>
              <textarea
                id="ai-notes"
                rows={4}
                required
                minLength={10}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Pega aquí las notas de la llamada o reunión con el cliente..."
                className="p-2.5 bg-background border border-border rounded-md text-xs focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              size="sm"
              isLoading={isAnalyzing}
              disabled={!contactId || notes.trim().length < 10}
            >
              Analizar Interacción
            </Button>
          </form>

          {summaryResult && (
            <div className="mt-2 p-4 bg-muted/40 border border-border rounded-lg flex flex-col gap-2 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Badge variant="outline" className="font-mono text-[10px]">
                  {summaryResult.model_used} ({summaryResult.key_source})
                </Badge>
                <Badge
                  variant={summaryResult.detected_sentiment === "positive" ? "success" : "secondary"}
                  className="text-[10px]"
                >
                  Sentimiento: {summaryResult.detected_sentiment}
                </Badge>
              </div>
              {summaryResult.is_stub && (
                <div className="flex items-center gap-1.5 text-[11px] text-warning font-medium">
                  <ShieldAlert className="h-3.5 w-3.5" />
                  <span>
                    Respuesta simulada en modo desarrollo offline (sin API key configurada).
                  </span>
                </div>
              )}
              <p className="text-foreground font-medium">{summaryResult.executive_summary}</p>
              <p className="text-muted-foreground">
                <strong>Siguiente paso:</strong> {summaryResult.suggested_next_step}
              </p>
            </div>
          )}
        </section>

        {/* Semantic Vector Search */}
        <section className="p-5 bg-card border border-border rounded-xl shadow-card flex flex-col gap-4">
          <h2 className="text-sm font-semibold text-foreground">
            2. Búsqueda Semántica (pgvector HNSW)
          </h2>

          <form onSubmit={handleSemanticSearch} className="flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                aria-label="Consulta semántica"
                value={semanticQuery}
                onChange={(e) => setSemanticQuery(e.target.value)}
                placeholder="Ej. VP Engineering Kubernetes migración..."
                className="w-full h-9 pl-9 pr-3 bg-background border border-border rounded-md text-xs"
              />
            </div>
            <Button type="submit" variant="outline" size="sm" isLoading={isSearching}>
              Buscar
            </Button>
          </form>

          {semanticSource && (
            <span className="text-[11px] text-muted-foreground font-mono">
              Motor: {semanticSource}
            </span>
          )}

          <div className="flex flex-col gap-2">
            {semanticResults.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                Ejecuta una búsqueda semántica para recuperar contactos, deals o notas indexadas en
                este tenant.
              </p>
            ) : (
              semanticResults.map((res) => (
                <div
                  key={`${res.entity_type}-${res.entity_id}`}
                  className="p-3 rounded-lg bg-muted/40 border border-border text-xs flex flex-col gap-1"
                >
                  <div className="flex items-center justify-between">
                    <Badge variant="secondary" className="text-[10px]">
                      {res.entity_type}
                    </Badge>
                    <span className="font-mono text-[11px] text-muted-foreground">
                      similitud: {res.similarity.toFixed(3)}
                    </span>
                  </div>
                  <p className="text-foreground">{res.text_content}</p>
                </div>
              ))
            )}
          </div>
        </section>
      </div>

      {/* HITL Proposals Queue */}
      <section className="p-5 bg-card border border-border rounded-xl shadow-card flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-foreground">
            3. Cola de Aprobación Human-in-the-Loop ({proposals.length})
          </h2>
          {!canReviewProposals && (
            <span className="text-[11px] text-muted-foreground">
              Solo admin o sales_manager pueden aprobar/rechazar propuestas.
            </span>
          )}
        </div>

        {proposals.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No existen propuestas generadas por agentes en este workspace todavía.
          </p>
        ) : (
          <div className="flex flex-col gap-2.5">
            {proposals.map((prop) => (
              <div
                key={prop.id}
                className="p-4 rounded-lg border border-border bg-background flex flex-col sm:flex-row sm:items-center justify-between gap-3"
              >
                <div className="flex flex-col gap-1 min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {prop.action_type}
                    </Badge>
                    <Badge
                      variant={
                        prop.status === "approved"
                          ? "success"
                          : prop.status === "rejected"
                          ? "destructive"
                          : "warning"
                      }
                      className="text-[10px]"
                    >
                      {prop.status}
                    </Badge>
                    <span className="text-[11px] text-muted-foreground font-mono">
                      {prop.target_entity_type}
                    </span>
                  </div>
                  <p className="text-xs font-medium text-foreground">
                    {String(prop.proposed_payload?.summary || prop.reasoning_summary)}
                  </p>
                  {prop.rejection_reason && (
                    <p className="text-[11px] text-destructive">
                      Motivo rechazo: {prop.rejection_reason}
                    </p>
                  )}
                </div>

                {prop.status === "pending_review" && canReviewProposals && (
                  <div className="flex items-center gap-2 shrink-0">
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => handleApproveProposal(prop.id)}
                      className="h-8 text-xs gap-1"
                    >
                      <CheckCircle2 className="h-3.5 w-3.5" />
                      <span>Aprobar</span>
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setRejectingId(prop.id);
                        setRejectReason("");
                      }}
                      className="h-8 text-xs text-destructive gap-1"
                    >
                      <XCircle className="h-3.5 w-3.5" />
                      <span>Rechazar</span>
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      {rejectingId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Rechazar propuesta de IA"
          onClick={() => setRejectingId(null)}
        >
          <form
            onSubmit={handleRejectSubmit}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md p-6 bg-card border border-border rounded-xl shadow-elevated flex flex-col gap-4"
          >
            <h3 className="text-base font-semibold text-foreground">Rechazar Propuesta</h3>
            <textarea
              required
              minLength={3}
              rows={3}
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Indica el motivo del rechazo para el log de auditoría..."
              className="p-2.5 bg-background border border-border rounded-md text-xs"
            />
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => setRejectingId(null)}>
                Cancelar
              </Button>
              <Button type="submit" variant="destructive" size="sm">
                Confirmar Rechazo
              </Button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

export default function AICopilotPage() {
  return (
    <Suspense
      fallback={<div className="p-6 text-xs text-muted-foreground">Cargando Copilot IA...</div>}
    >
      <AICopilotWorkspaceContent />
    </Suspense>
  );
}
