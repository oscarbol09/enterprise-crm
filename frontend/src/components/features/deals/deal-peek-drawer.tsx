"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  Calendar,
  ChevronLeft,
  ChevronRight,
  Clock,
  MessageSquarePlus,
  Send,
  Terminal,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import {
  Contact,
  Deal,
  DealParticipant,
  DealPlaybookResponse,
  DealStageHistoryItem,
  InteractionItem,
  InteractionSummarizeResponse,
  PipelineStage,
} from "../../../types/crm";
import {
  ApiError,
  addDealParticipant,
  createInteraction,
  createTask,
  fetchDealInteractions,
  fetchDealParticipants,
  fetchDealPlaybook,
  fetchDealStageHistory,
  summarizeInteraction,
} from "../../../lib/api-client";
import { Badge } from "../../ui/badge";
import { Button } from "../../ui/button";

interface DealPeekDrawerProps {
  deal: Deal | null;
  stages: PipelineStage[];
  contacts: Contact[];
  authToken?: string;
  onClose: () => void;
  onNavigateDeal?: (direction: "prev" | "next") => void;
}

type OmniboxMode = "note" | "call" | "meeting" | "email" | "task";

function parseOmniboxSlashCommand(rawInput: string, fallbackMode: OmniboxMode): {
  mode: OmniboxMode;
  cleanBody: string;
  subject: string;
} {
  const trimmed = rawInput.trim();
  const match = trimmed.match(/^\/(call|llamada|note|nota|meeting|reunion|email|correo|task|tarea)\s+([\s\S]+)$/i);
  let resolvedMode = fallbackMode;
  let cleanBody = trimmed;

  if (match) {
    const cmd = match[1].toLowerCase();
    cleanBody = match[2].trim();
    if (cmd === "call" || cmd === "llamada") resolvedMode = "call";
    else if (cmd === "meeting" || cmd === "reunion") resolvedMode = "meeting";
    else if (cmd === "email" || cmd === "correo") resolvedMode = "email";
    else if (cmd === "task" || cmd === "tarea") resolvedMode = "task";
    else resolvedMode = "note";
  }

  const labelByMode: Record<OmniboxMode, string> = {
    note: "Nota rápida",
    call: "Llamada registrada",
    meeting: "Minuta de reunión",
    email: "Correo registrado",
    task: "Tarea de seguimiento",
  };

  const firstSentence = cleanBody.split(/[.!?\n]/)[0]?.slice(0, 80) || labelByMode[resolvedMode];
  const subject = `${labelByMode[resolvedMode]}: ${firstSentence}`;
  return { mode: resolvedMode, cleanBody, subject };
}

export function DealPeekDrawer({
  deal,
  stages,
  contacts,
  authToken,
  onClose,
  onNavigateDeal,
}: DealPeekDrawerProps) {
  const [activeTab, setActiveTab] = useState<"timeline" | "committee" | "history">("timeline");
  const [interactions, setInteractions] = useState<InteractionItem[]>([]);
  const [participants, setParticipants] = useState<DealParticipant[]>([]);
  const [stageHistory, setStageHistory] = useState<DealStageHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Omnibox state
  const [omniboxMode, setOmniboxMode] = useState<OmniboxMode>("note");
  const [omniboxText, setOmniboxText] = useState("");
  const [isSubmittingOmnibox, setIsSubmittingOmnibox] = useState(false);

  // In-place Copilot summary & Rep Playbook state
  const [isRunningCopilot, setIsRunningCopilot] = useState(false);
  const [copilotSummary, setCopilotSummary] = useState<InteractionSummarizeResponse | null>(null);
  const [isLoadingPlaybook, setIsLoadingPlaybook] = useState(false);
  const [playbook, setPlaybook] = useState<DealPlaybookResponse | null>(null);

  // Buying committee quick-add state
  const [selectedContactId, setSelectedContactId] = useState("");
  const [selectedRole, setSelectedRole] = useState<
    "champion" | "economic_buyer" | "technical_evaluator" | "legal_blocker" | "executive_sponsor" | "stakeholder"
  >("economic_buyer");
  const [isAddingParticipant, setIsAddingParticipant] = useState(false);

  const loadDealContext = useCallback(
    async (targetDeal: Deal, preserveSummary = false) => {
      setIsLoading(true);
      setError(null);
      if (!preserveSummary) {
        setCopilotSummary(null);
      }
      try {
        const [timelineRes, partsRes, histRes] = await Promise.all([
          fetchDealInteractions(targetDeal.id, authToken).catch(() => []),
          fetchDealParticipants(targetDeal.id, authToken).catch(() => []),
          fetchDealStageHistory(targetDeal.id, authToken).catch(() => []),
        ]);
        setInteractions(timelineRes);
        setParticipants(partsRes);
        setStageHistory(histRes);
      } finally {
        setIsLoading(false);
      }
    },
    [authToken]
  );

  useEffect(() => {
    if (!deal) return;
    let active = true;
    async function initDrawer(targetDeal: Deal) {
      const [timelineRes, partsRes, histRes] = await Promise.all([
        fetchDealInteractions(targetDeal.id, authToken).catch(() => []),
        fetchDealParticipants(targetDeal.id, authToken).catch(() => []),
        fetchDealStageHistory(targetDeal.id, authToken).catch(() => []),
      ]);
      if (!active) return;
      setInteractions(timelineRes);
      setParticipants(partsRes);
      setStageHistory(histRes);
      setIsLoading(false);
    }
    void initDrawer(deal);
    return () => {
      active = false;
    };
  }, [deal, authToken]);

  if (!deal) return null;

  const stageName = stages.find((s) => s.id === deal.stage_id)?.name || "Etapa activa";

  const handleOmniboxSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!omniboxText.trim()) return;
    setIsSubmittingOmnibox(true);
    setError(null);

    const { mode, cleanBody, subject } = parseOmniboxSlashCommand(omniboxText, omniboxMode);

    try {
      if (mode === "task") {
        const dueIso = new Date(Date.now() + 86400000 * 2).toISOString();
        await createTask(
          {
            title: cleanBody.slice(0, 200),
            due_date: dueIso,
            priority: "high",
            deal_id: deal.id,
            contact_id: deal.contact_id ?? undefined,
          },
          authToken
        );
      } else {
        const created = await createInteraction(
          {
            deal_id: deal.id,
            contact_id: deal.contact_id ?? undefined,
            account_id: deal.account_id ?? undefined,
            type: mode,
            direction: "outbound",
            subject,
            content_body: cleanBody,
          },
          authToken
        );
        setInteractions((prev) => [created, ...prev]);
      }
      setOmniboxText("");
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo registrar la actividad.");
    } finally {
      setIsSubmittingOmnibox(false);
    }
  };

  const handleRunInPlaceCopilot = async () => {
    const targetContactId = deal.contact_id || contacts[0]?.id;
    const textToAnalyze =
      omniboxText.trim().length >= 10
        ? omniboxText.trim()
        : interactions[0]?.content_body || deal.title;

    if (!targetContactId || textToAnalyze.length < 10) {
      setError("Para resumir con IA in-place, escribe al menos 10 caracteres en la Omnibox y vincula un contacto.");
      return;
    }

    setIsRunningCopilot(true);
    setError(null);
    try {
      const res = await summarizeInteraction(
        {
          contact_id: targetContactId,
          deal_id: deal.id,
          raw_notes_or_transcript: textToAnalyze,
          interaction_type: omniboxMode === "task" ? "note" : omniboxMode,
        },
        authToken
      );
      setCopilotSummary(res);
      await loadDealContext(deal, true);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Error al ejecutar Copilot in-place.");
    } finally {
      setIsRunningCopilot(false);
    }
  };

  const handleLoadRepPlaybook = async () => {
    setIsLoadingPlaybook(true);
    setError(null);
    try {
      const res = await fetchDealPlaybook(deal.id, authToken);
      setPlaybook(res);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo cargar el Playbook de la etapa.");
    } finally {
      setIsLoadingPlaybook(false);
    }
  };

  const handleAddParticipant = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedContactId) return;
    setIsAddingParticipant(true);
    setError(null);
    try {
      const created = await addDealParticipant(
        deal.id,
        {
          contact_id: selectedContactId,
          buying_role: selectedRole,
          is_primary: false,
        },
        authToken
      );
      setParticipants((prev) => [...prev, created]);
      setSelectedContactId("");
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo añadir al comité de compra.");
    } finally {
      setIsAddingParticipant(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-background/50 backdrop-blur-[1px]"
      role="dialog"
      aria-modal="true"
      aria-label={`Detalle de ${deal.title}`}
      onClick={onClose}
    >
      <aside
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-xl h-full bg-card border-l border-border shadow-elevated flex flex-col overflow-hidden"
      >
        {/* Top Drawer Bar */}
        <header className="px-5 py-4 border-b border-border flex items-start justify-between gap-3 bg-muted/20">
          <div className="flex flex-col gap-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="outline" className="text-[10px]">
                {stageName}
              </Badge>
              <Badge variant="secondary" className="text-[10px] font-mono uppercase">
                {deal.forecast_category}
              </Badge>
              {(deal.close_date_push_count ?? 0) > 0 && (
                <Badge variant="warning" className="text-[10px]">
                  Slippage x{deal.close_date_push_count}
                </Badge>
              )}
            </div>
            <h2 className="text-base font-bold text-foreground truncate">{deal.title}</h2>
            <p className="text-xs text-muted-foreground font-mono tabular-nums">
              ${Number(deal.amount).toLocaleString("en-US")} {deal.currency}
              {deal.currency !== "USD" && (
                <span>
                  {" "}
                  (≈${Number(deal.normalized_amount_usd ?? deal.amount).toLocaleString("en-US")}{" "}
                  USD)
                </span>
              )}{" "}
              · Probabilidad {Math.round(Number(deal.win_probability) * 100)}% (Ponderado: $
              {Math.round(
                Number(deal.normalized_amount_usd ?? deal.amount) * Number(deal.win_probability)
              ).toLocaleString("en-US")}{" "}
              USD)
            </p>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            {onNavigateDeal && (
              <>
                <button
                  type="button"
                  onClick={() => onNavigateDeal("prev")}
                  aria-label="Oportunidad anterior"
                  className="p-1.5 rounded border border-border text-muted-foreground hover:text-foreground"
                >
                  <ChevronLeft className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => onNavigateDeal("next")}
                  aria-label="Siguiente oportunidad"
                  className="p-1.5 rounded border border-border text-muted-foreground hover:text-foreground"
                >
                  <ChevronRight className="h-3.5 w-3.5" />
                </button>
              </>
            )}
            <button
              type="button"
              onClick={onClose}
              aria-label="Cerrar detalle"
              className="p-1.5 rounded text-muted-foreground hover:text-foreground"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </header>

        {/* Omnibox Activity Bar (Always accessible at the top of the drawer) */}
        <section className="p-4 border-b border-border bg-card flex flex-col gap-2.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1">
              {(
                [
                  { id: "note", label: "Nota" },
                  { id: "call", label: "Llamada" },
                  { id: "meeting", label: "Reunión" },
                  { id: "email", label: "Correo" },
                  { id: "task", label: "Tarea" },
                ] as { id: OmniboxMode; label: string }[]
              ).map((pill) => (
                <button
                  key={pill.id}
                  type="button"
                  onClick={() => setOmniboxMode(pill.id)}
                  className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${
                    omniboxMode === pill.id
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-muted"
                  }`}
                >
                  {pill.label}
                </button>
              ))}
            </div>
            <span className="text-[10px] font-mono text-muted-foreground hidden sm:inline">
              Slash: /call /meeting /task · ⌘+Enter
            </span>
          </div>

          <form onSubmit={handleOmniboxSubmit} className="flex flex-col gap-2">
            <textarea
              rows={2}
              value={omniboxText}
              onChange={(e) => setOmniboxText(e.target.value)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                  e.preventDefault();
                  void handleOmniboxSubmit();
                }
              }}
              placeholder="Escribe una nota o usa /call, /meeting, /task para registrar en 1 paso..."
              className="w-full p-2.5 bg-background border border-border rounded-md text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            />
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="flex items-center gap-1.5">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleRunInPlaceCopilot}
                  isLoading={isRunningCopilot}
                  className="h-7 text-[11px] gap-1.5"
                >
                  <Terminal className="h-3 w-3" />
                  <span>Extraer resumen y pasos</span>
                </Button>

                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleLoadRepPlaybook}
                  isLoading={isLoadingPlaybook}
                  className="h-7 text-[11px] gap-1.5"
                >
                  <span>Playbook & Borrador</span>
                </Button>
              </div>

              <Button
                type="submit"
                variant="primary"
                size="sm"
                isLoading={isSubmittingOmnibox}
                disabled={!omniboxText.trim()}
                className="h-7 text-[11px] gap-1.5"
              >
                <Send className="h-3 w-3" />
                <span>Registrar Actividad</span>
              </Button>
            </div>
          </form>

          {playbook && (
            <div className="p-3 rounded-lg bg-muted/40 border border-border text-xs flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-foreground">
                  Playbook de Etapa: {playbook.stage_name}
                </span>
                <button
                  type="button"
                  onClick={() => setPlaybook(null)}
                  className="text-[11px] text-muted-foreground hover:text-foreground"
                >
                  Ocultar
                </button>
              </div>
              <ul className="list-disc pl-4 text-muted-foreground flex flex-col gap-0.5">
                {playbook.recommended_actions.map((action, idx) => (
                  <li key={idx}>{action}</li>
                ))}
              </ul>
              <div className="p-2 rounded bg-background border border-border flex flex-col gap-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[11px] font-semibold text-foreground">
                    Asunto: {playbook.follow_up_email_subject}
                  </span>
                  <button
                    type="button"
                    onClick={() => {
                      setOmniboxMode("email");
                      setOmniboxText(playbook.follow_up_email_body);
                    }}
                    className="text-[11px] font-medium text-primary hover:underline"
                  >
                    Usar borrador en Omnibox
                  </button>
                </div>
                <pre className="text-[11px] text-muted-foreground whitespace-pre-wrap font-sans">
                  {playbook.follow_up_email_body}
                </pre>
              </div>
            </div>
          )}

          {copilotSummary && (
            <div className="p-3 rounded-md bg-muted/50 border border-border text-xs flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-foreground">Resumen extraído</span>
                <Badge variant="outline" className="text-[10px] font-mono">
                  {copilotSummary.detected_sentiment}
                </Badge>
              </div>
              <p className="text-foreground">{copilotSummary.executive_summary}</p>
              <p className="text-muted-foreground">
                <strong>Próximo paso sugerido:</strong> {copilotSummary.suggested_next_step}
              </p>
            </div>
          )}

          {error && (
            <div role="alert" className="text-xs text-destructive bg-destructive/10 p-2 rounded">
              {error}
            </div>
          )}
        </section>

        {/* Sub-Navigation Tabs */}
        <div className="px-5 pt-2 border-b border-border flex items-center gap-4 text-xs bg-muted/10">
          <button
            type="button"
            onClick={() => setActiveTab("timeline")}
            className={`pb-2 font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === "timeline"
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <MessageSquarePlus className="h-3.5 w-3.5" />
            <span>Timeline ({interactions.length})</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("committee")}
            className={`pb-2 font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === "committee"
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Users className="h-3.5 w-3.5" />
            <span>Comité de Compra ({participants.length})</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("history")}
            className={`pb-2 font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === "history"
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Clock className="h-3.5 w-3.5" />
            <span>Historial de Etapas ({stageHistory.length})</span>
          </button>
        </div>

        {/* Drawer Content Body */}
        <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-3">
          {deal.loss_reason && (
            <div className="p-3 rounded-md bg-destructive/10 border border-destructive/20 text-xs text-destructive">
              <strong>Motivo de pérdida:</strong> {deal.loss_reason}
            </div>
          )}

          {isLoading ? (
            <p className="text-xs text-muted-foreground">Cargando contexto de la oportunidad...</p>
          ) : activeTab === "timeline" ? (
            interactions.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                Aún no hay interacciones registradas. Usa la Omnibox superior (`/call`, `/note`) para
                registrar la primera.
              </p>
            ) : (
              <ul className="flex flex-col gap-2.5">
                {interactions.map((item) => (
                  <li
                    key={item.id}
                    className="p-3 rounded-lg bg-muted/30 border border-border text-xs flex flex-col gap-1"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5">
                        <Badge variant="secondary" className="text-[10px] uppercase">
                          {item.type}
                        </Badge>
                        <span className="font-semibold text-foreground">{item.subject}</span>
                      </div>
                      <span className="text-[10px] text-muted-foreground flex items-center gap-1 tabular-nums">
                        <Calendar className="h-3 w-3" />
                        {new Date(item.occurred_at).toLocaleDateString()}
                      </span>
                    </div>
                    <p className="text-muted-foreground leading-relaxed">{item.content_body}</p>
                  </li>
                ))}
              </ul>
            )
          ) : activeTab === "committee" ? (
            <div className="flex flex-col gap-4">
              <form onSubmit={handleAddParticipant} className="flex flex-wrap items-center gap-2">
                <select
                  aria-label="Seleccionar contacto para comité"
                  value={selectedContactId}
                  onChange={(e) => setSelectedContactId(e.target.value)}
                  className="flex-1 min-w-[160px] h-8 px-2 bg-background border border-border rounded text-xs"
                >
                  <option value="">Añadir contacto al comité...</option>
                  {contacts
                    .filter((c) => !participants.some((p) => p.contact_id === c.id))
                    .map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.first_name} {c.last_name} ({c.email})
                      </option>
                    ))}
                </select>
                <select
                  aria-label="Rol de compra"
                  value={selectedRole}
                  onChange={(e) =>
                    setSelectedRole(
                      e.target.value as
                        | "champion"
                        | "economic_buyer"
                        | "technical_evaluator"
                        | "legal_blocker"
                        | "executive_sponsor"
                        | "stakeholder"
                    )
                  }
                  className="h-8 px-2 bg-background border border-border rounded text-xs"
                >
                  <option value="champion">Champion</option>
                  <option value="economic_buyer">Comprador Económico</option>
                  <option value="technical_evaluator">Evaluador Técnico</option>
                  <option value="legal_blocker">Legal / Procurement</option>
                  <option value="executive_sponsor">Sponsor Ejecutivo</option>
                  <option value="stakeholder">Stakeholder</option>
                </select>
                <Button
                  type="submit"
                  variant="outline"
                  size="sm"
                  isLoading={isAddingParticipant}
                  disabled={!selectedContactId}
                  className="h-8 text-xs gap-1"
                >
                  <UserPlus className="h-3.5 w-3.5" />
                  <span>Vincular</span>
                </Button>
              </form>

              {participants.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No hay participantes asignados al comité de compra de este trato.
                </p>
              ) : (
                <ul className="flex flex-col gap-2">
                  {participants.map((p) => {
                    const matched = contacts.find((c) => c.id === p.contact_id);
                    return (
                      <li
                        key={p.id}
                        className="p-3 rounded-lg bg-muted/30 border border-border text-xs flex items-center justify-between"
                      >
                        <div>
                          <span className="font-semibold text-foreground">
                            {matched ? `${matched.first_name} ${matched.last_name}` : p.contact_id}
                          </span>
                          {matched?.job_title && (
                            <span className="text-muted-foreground ml-1.5">· {matched.job_title}</span>
                          )}
                        </div>
                        <Badge variant={p.is_primary ? "default" : "secondary"} className="text-[10px]">
                          {p.buying_role.replace("_", " ")}
                        </Badge>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {stageHistory.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  Sin registros de transición de etapa SCD Tipo 2.
                </p>
              ) : (
                stageHistory.map((h) => {
                  const toName = stages.find((s) => s.id === h.to_stage_id)?.name || h.to_stage_id;
                  const fromName = h.from_stage_id
                    ? stages.find((s) => s.id === h.from_stage_id)?.name || "Etapa previa"
                    : "Creación inicial";
                  return (
                    <div
                      key={h.id}
                      className="p-3 rounded-lg bg-muted/30 border border-border text-xs flex items-center justify-between tabular-nums"
                    >
                      <div className="flex flex-col gap-0.5">
                        <span className="font-medium text-foreground">
                          {fromName} → <strong>{toName}</strong>
                        </span>
                        <span className="text-[11px] text-muted-foreground font-mono">
                          Monto: ${Number(h.amount_at_transition).toLocaleString("en-US")} · Prob:{" "}
                          {Math.round(Number(h.win_probability_at_transition) * 100)}%
                        </span>
                      </div>
                      <div className="text-right text-[11px] text-muted-foreground font-mono">
                        <div>{new Date(h.entered_at).toLocaleDateString()}</div>
                        <div>
                          {h.exited_at
                            ? `Duración: ${h.duration_seconds ?? 0}s`
                            : "Etapa actual"}
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
