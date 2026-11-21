"use client";

import React, { useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  Calendar,
  CheckCircle2,
  ChevronRight,
  GripVertical,
  Plus,
  XCircle,
} from "lucide-react";
import { Deal, PipelineStage, StageGateFieldRequirement } from "../../../types/crm";
import { ApiError, moveDealStage, updateDeal } from "../../../lib/api-client";
import { Badge } from "../../ui/badge";
import { Button } from "../../ui/button";
import { Skeleton } from "../../ui/skeleton";

interface DealKanbanBoardProps {
  stages: PipelineStage[];
  initialDeals: Deal[];
  authToken?: string;
  onDealClick?: (deal: Deal) => void;
  onCreateDeal?: (stageId: string) => void;
  onDealMoved?: (updatedDeal: Deal) => void;
  isLoading?: boolean;
}

function isDealOverdue(deal: Deal): boolean {
  if (deal.is_won || deal.is_lost || !deal.expected_close_date) return false;
  const todayIso = new Date().toISOString().slice(0, 10);
  return deal.expected_close_date < todayIso;
}

const STALE_DEAL_DAYS_THRESHOLD = 14;

function getDealStaleDays(deal: Deal): number {
  if (deal.is_won || deal.is_lost) return 0;
  const referenceIso = deal.last_interaction_at || deal.stage_entered_at || deal.created_at;
  if (!referenceIso) return 0;
  const refMs = Date.parse(referenceIso);
  if (Number.isNaN(refMs)) return 0;
  return Math.max(0, Math.floor((Date.now() - refMs) / 86400000));
}

export function DealKanbanBoard({
  stages,
  initialDeals,
  authToken,
  onDealClick,
  onCreateDeal,
  onDealMoved,
  isLoading = false,
}: DealKanbanBoardProps) {
  // Optimistic overrides automatically yield to newer `initialDeals` references without effects
  const [overrides, setOverrides] = useState<Record<string, { base: Deal[]; deal: Deal }>>({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeTransitionId, setActiveTransitionId] = useState<string | null>(null);
  const [draggedDealId, setDraggedDealId] = useState<string | null>(null);
  const [dragOverStageId, setDragOverStageId] = useState<string | null>(null);
  const [pendingLossModal, setPendingLossModal] = useState<{
    deal: Deal;
    targetStage: PipelineStage;
  } | null>(null);
  const [lossReasonInput, setLossReasonInput] = useState("");
  const [lossCategoryInput, setLossCategoryInput] = useState<
    "price" | "missing_feature" | "competitor" | "ghosting" | "timing" | "other"
  >("price");
  const [competitorInput, setCompetitorInput] = useState("");
  const [missingFeatureInput, setMissingFeatureInput] = useState("");
  const [lossFormError, setLossFormError] = useState<string | null>(null);

  // Inline Soft Stage-Gate Popover when a stage transition requires a missing custom field
  const [pendingStageGate, setPendingStageGate] = useState<{
    deal: Deal;
    targetStage: PipelineStage;
    fields: StageGateFieldRequirement[];
  } | null>(null);
  const [stageGateValues, setStageGateValues] = useState<Record<string, string>>({});
  const [isSavingGate, setIsSavingGate] = useState(false);

  const deals = initialDeals.map((d) => {
    const entry = overrides[d.id];
    return entry && entry.base === initialDeals ? entry.deal : d;
  });

  const executeStageTransition = async (
    deal: Deal,
    targetStage: PipelineStage,
    lossDetails?: {
      loss_reason?: string;
      loss_category?: "price" | "missing_feature" | "competitor" | "ghosting" | "timing" | "other";
      competitor_name?: string;
      missing_feature_tag?: string;
    }
  ) => {
    const optimisticDeal: Deal = {
      ...deal,
      stage_id: targetStage.id,
      win_probability: Number(targetStage.default_probability),
      is_won: targetStage.is_closed_won,
      is_lost: targetStage.is_closed_lost,
      loss_reason: targetStage.is_closed_lost ? lossDetails?.loss_reason || null : null,
    };

    setOverrides((prev) => ({
      ...prev,
      [deal.id]: { base: initialDeals, deal: optimisticDeal },
    }));
    setActiveTransitionId(deal.id);
    setErrorMessage(null);

    try {
      const updated = await moveDealStage(
        deal.id,
        {
          new_stage_id: targetStage.id,
          loss_reason: lossDetails?.loss_reason,
          loss_category: lossDetails?.loss_category,
          competitor_name: lossDetails?.competitor_name,
          missing_feature_tag: lossDetails?.missing_feature_tag,
        },
        authToken
      );
      setOverrides((prev) => ({
        ...prev,
        [deal.id]: { base: initialDeals, deal: updated },
      }));
      onDealMoved?.(updated);
    } catch (err: unknown) {
      setOverrides((prev) => {
        const next = { ...prev };
        delete next[deal.id];
        return next;
      });
      if (err instanceof ApiError && err.status === 422 && err.stageGateFields?.length) {
        const initialDraft: Record<string, string> = {};
        for (const f of err.stageGateFields) {
          initialDraft[f.field_key] = "";
        }
        setStageGateValues(initialDraft);
        setPendingStageGate({ deal, targetStage, fields: err.stageGateFields });
        return;
      }
      const message =
        err instanceof ApiError
          ? err.message
          : "Error de conexión al mover la oportunidad. Se restauró el estado previo.";
      setErrorMessage(message);
    } finally {
      setActiveTransitionId(null);
    }
  };

  const handleStageSelect = (deal: Deal, targetStageId: string) => {
    if (deal.stage_id === targetStageId) return;
    const targetStage = stages.find((s) => s.id === targetStageId);
    if (!targetStage) return;

    if (targetStage.is_closed_lost) {
      setLossReasonInput("");
      setLossCategoryInput("price");
      setCompetitorInput("");
      setMissingFeatureInput("");
      setLossFormError(null);
      setPendingLossModal({ deal, targetStage });
      return;
    }

    void executeStageTransition(deal, targetStage);
  };

  const handleDragStart = (e: React.DragEvent<HTMLElement>, deal: Deal) => {
    setDraggedDealId(deal.id);
    e.dataTransfer?.setData("text/plain", deal.id);
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = "move";
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLElement>, stageId: string) => {
    e.preventDefault();
    if (e.dataTransfer) {
      e.dataTransfer.dropEffect = "move";
    }
    if (dragOverStageId !== stageId) {
      setDragOverStageId(stageId);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLElement>, targetStageId: string) => {
    e.preventDefault();
    setDragOverStageId(null);
    const droppedId = e.dataTransfer?.getData("text/plain") || draggedDealId;
    setDraggedDealId(null);
    if (!droppedId) return;
    const deal = deals.find((d) => d.id === droppedId);
    if (deal && deal.stage_id !== targetStageId) {
      handleStageSelect(deal, targetStageId);
    }
  };

  const handleConfirmLossModal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pendingLossModal) return;
    const trimmed = lossReasonInput.trim();
    if (!trimmed) {
      setLossFormError("El motivo de pérdida es obligatorio para cerrar una oportunidad como perdida.");
      return;
    }
    const { deal, targetStage } = pendingLossModal;
    setPendingLossModal(null);
    await executeStageTransition(deal, targetStage, {
      loss_reason: trimmed,
      loss_category: lossCategoryInput,
      competitor_name: competitorInput.trim() || undefined,
      missing_feature_tag: missingFeatureInput.trim() || undefined,
    });
  };

  const handleConfirmStageGate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pendingStageGate) return;
    setIsSavingGate(true);
    setErrorMessage(null);
    try {
      const metadataPatch: Record<string, unknown> = { ...(pendingStageGate.deal.metadata || {}) };
      for (const f of pendingStageGate.fields) {
        const raw = (stageGateValues[f.field_key] || "").trim();
        metadataPatch[f.field_key] = f.field_type === "number" ? Number(raw) : raw;
      }
      const patched = await updateDeal(
        pendingStageGate.deal.id,
        { metadata: metadataPatch },
        authToken
      );
      const { targetStage } = pendingStageGate;
      setPendingStageGate(null);
      await executeStageTransition(patched, targetStage);
    } catch (err: unknown) {
      setErrorMessage(
        err instanceof ApiError ? err.message : "No se pudo guardar el campo requerido."
      );
    } finally {
      setIsSavingGate(false);
    }
  };

  if (isLoading) {
    return (
      <div
        className="grid grid-cols-1 md:grid-cols-4 gap-4 p-4 overflow-x-auto min-h-[500px]"
        aria-busy="true"
        aria-label="Cargando tablero del pipeline de ventas"
      >
        {[1, 2, 3, 4].map((col) => (
          <div
            key={col}
            className="flex flex-col gap-3 bg-muted/40 p-3 rounded-lg border border-border"
          >
            <div className="flex items-center justify-between pb-2 border-b border-border/50">
              <Skeleton className="h-5 w-28" />
              <Skeleton className="h-4 w-12" />
            </div>
            <Skeleton className="h-28 w-full rounded-md" />
            <Skeleton className="h-28 w-full rounded-md" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div aria-live="polite" className="sr-only">
        {errorMessage ? `Error: ${errorMessage}` : "Tablero de ventas actualizado"}
      </div>

      {errorMessage && (
        <div
          role="alert"
          className="flex items-center justify-between p-3 rounded-md bg-destructive/10 border border-destructive/20 text-destructive text-sm"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
            <span>{errorMessage}</span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setErrorMessage(null)}
            className="text-destructive hover:bg-destructive/10 h-8 px-2"
          >
            Descartar
          </Button>
        </div>
      )}

      <div
        className="flex gap-4 overflow-x-auto pb-6"
        role="region"
        aria-label="Etapas del Pipeline"
      >
        {stages.map((stage, stageIndex) => {
          const stageDeals = deals.filter((d) => d.stage_id === stage.id);
          const totalValue = stageDeals.reduce(
            (sum, d) => sum + Number(d.normalized_amount_usd ?? d.amount),
            0
          );
          const weightedValue = stageDeals.reduce(
            (sum, d) =>
              sum + Number(d.normalized_amount_usd ?? d.amount) * Number(d.win_probability),
            0
          );
          const nextStage = stages[stageIndex + 1];
          const isDropTarget = dragOverStageId === stage.id;

          return (
            <div
              key={stage.id}
              onDragOver={(e) => handleDragOver(e, stage.id)}
              onDragLeave={() => setDragOverStageId(null)}
              onDrop={(e) => handleDrop(e, stage.id)}
              className={`flex flex-col gap-3 bg-card p-3 rounded-lg border transition-colors min-w-[275px] w-72 shrink-0 ${
                isDropTarget ? "border-primary bg-primary/5 ring-2 ring-primary/30" : "border-border"
              }`}
            >
              <div className="flex flex-col gap-1 pb-2 border-b border-border">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold text-sm text-foreground">{stage.name}</h3>
                    <Badge variant="secondary" className="text-xs px-1.5 py-0 tabular-nums">
                      {stageDeals.length}
                    </Badge>
                  </div>
                  <span className="text-xs font-mono font-semibold text-foreground tabular-nums">
                    ${totalValue.toLocaleString("en-US", { minimumFractionDigits: 0 })}
                  </span>
                </div>
                {!stage.is_closed_lost && (
                  <div className="flex items-center justify-between text-[10px] text-muted-foreground tabular-nums">
                    <span>Prob. base {Math.round(Number(stage.default_probability) * 100)}%</span>
                    <span>
                      Ponderado: ${Math.round(weightedValue).toLocaleString("en-US")}
                    </span>
                  </div>
                )}
              </div>

              <div
                className="flex flex-col gap-2.5 min-h-[380px]"
                role="list"
                aria-label={`Oportunidades en ${stage.name}`}
                onDragOver={(e) => handleDragOver(e, stage.id)}
                onDrop={(e) => handleDrop(e, stage.id)}
              >
                {stageDeals.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-44 border border-dashed border-border rounded-md p-4 text-center">
                    <p className="text-xs text-muted-foreground mb-3">
                      Arrastra tratos aquí o crea uno nuevo
                    </p>
                    {onCreateDeal && (
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onCreateDeal(stage.id)}
                        className="text-xs gap-1.5 h-8 min-h-[36px]"
                      >
                        <Plus className="h-3.5 w-3.5" aria-hidden="true" />
                        <span>Agregar trato</span>
                      </Button>
                    )}
                  </div>
                ) : (
                  stageDeals.map((deal) => {
                    const isTransitioning = activeTransitionId === deal.id;
                    const numericAmount = Number(deal.amount);
                    const probabilityPct = Math.round(Number(deal.win_probability) * 100);
                    const overdue = isDealOverdue(deal);
                    const staleDays = getDealStaleDays(deal);
                    const isStale = staleDays >= STALE_DEAL_DAYS_THRESHOLD;
                    const hasRisk = overdue || isStale;

                    return (
                      <article
                        key={deal.id}
                        role="listitem"
                        tabIndex={0}
                        draggable={!isTransitioning}
                        onDragStart={(e) => handleDragStart(e, deal)}
                        onDragEnd={() => {
                          setDraggedDealId(null);
                          setDragOverStageId(null);
                        }}
                        aria-roledescription="tarjeta de oportunidad de venta"
                        aria-label={`${deal.title}, valor $${numericAmount.toLocaleString("en-US")}, probabilidad ${probabilityPct}%`}
                        className={`group relative flex flex-col gap-2 p-3.5 bg-card hover:bg-muted/30 rounded-md border shadow-card transition-all duration-150 cursor-grab active:cursor-grabbing focus-visible:ring-2 focus-visible:ring-primary ${
                          isTransitioning
                            ? "opacity-60 scale-[0.99] border-primary/50"
                            : hasRisk
                            ? "border-warning/60"
                            : "border-border"
                        }`}
                        onClick={() => onDealClick?.(deal)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            onDealClick?.(deal);
                          }
                        }}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-start gap-1.5 min-w-0">
                            <GripVertical
                              className="h-3.5 w-3.5 text-muted-foreground/50 shrink-0 mt-0.5"
                              aria-hidden="true"
                            />
                            <h4 className="font-medium text-sm text-foreground group-hover:text-primary transition-colors line-clamp-2">
                              {deal.title}
                            </h4>
                          </div>
                          {deal.is_won ? (
                            <Badge variant="success" className="gap-1 text-[11px] shrink-0">
                              <CheckCircle2 className="h-3 w-3" /> Ganado
                            </Badge>
                          ) : deal.is_lost ? (
                            <Badge variant="destructive" className="gap-1 text-[11px] shrink-0">
                              <XCircle className="h-3 w-3" /> Perdido
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="text-[11px] shrink-0 font-mono tabular-nums">
                              {probabilityPct}%
                            </Badge>
                          )}
                        </div>

                        <div className="flex items-center justify-between text-xs text-muted-foreground pt-1 border-t border-border/50 tabular-nums">
                          <span className="font-semibold font-mono text-foreground text-sm">
                            ${numericAmount.toLocaleString("en-US", { minimumFractionDigits: 0 })}{" "}
                            <span className="text-[10px] font-normal text-muted-foreground">
                              {deal.currency}
                            </span>
                            {deal.currency !== "USD" && deal.normalized_amount_usd !== undefined && (
                              <span className="text-[10px] font-normal text-muted-foreground ml-1">
                                (≈${Number(deal.normalized_amount_usd).toLocaleString("en-US")} USD)
                              </span>
                            )}
                          </span>
                          {deal.expected_close_date && (
                            <div
                              className={`flex items-center gap-1 text-[11px] ${
                                overdue ? "text-warning font-semibold" : ""
                              }`}
                            >
                              {overdue ? (
                                <AlertTriangle className="h-3 w-3" aria-hidden="true" />
                              ) : (
                                <Calendar className="h-3 w-3" aria-hidden="true" />
                              )}
                              <span>{deal.expected_close_date}</span>
                              {overdue && (
                                <span className="text-[10px] uppercase tracking-tight bg-warning/15 text-warning px-1 rounded">
                                  Vencido
                                </span>
                              )}
                            </div>
                          )}
                        </div>

                        {isStale && (
                          <div className="flex items-center gap-1 text-[10px] font-medium text-warning bg-warning/10 border border-warning/25 rounded px-1.5 py-0.5 w-fit tabular-nums">
                            <AlertTriangle className="h-3 w-3 shrink-0" aria-hidden="true" />
                            <span>Estancado {staleDays}d</span>
                          </div>
                        )}

                        <div
                          className="pt-2 flex flex-col gap-1.5"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {nextStage && !deal.is_won && !deal.is_lost && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 px-2 text-xs text-primary hover:text-primary hover:bg-primary/10 gap-1 w-full justify-between"
                              onClick={() => handleStageSelect(deal, nextStage.id)}
                              aria-label={`Avanzar oportunidad ${deal.title} a ${nextStage.name}`}
                            >
                              <span className="text-[11px]">Avanzar a {nextStage.name}</span>
                              <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                            </Button>
                          )}

                          <label className="sr-only" htmlFor={`stage-select-${deal.id}`}>
                            Mover {deal.title} a etapa
                          </label>
                          <select
                            id={`stage-select-${deal.id}`}
                            aria-label={`Mover ${deal.title} a etapa`}
                            value={deal.stage_id}
                            onChange={(e) => handleStageSelect(deal, e.target.value)}
                            className="w-full h-8 px-2 bg-background border border-border rounded text-[11px] text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                          >
                            {stages.map((opt) => (
                              <option key={opt.id} value={opt.id}>
                                Etapa: {opt.name}
                              </option>
                            ))}
                          </select>
                        </div>
                      </article>
                    );
                  })
                )}
              </div>
            </div>
          );
        })}
      </div>

      {pendingLossModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Registrar motivo de pérdida"
          onClick={() => setPendingLossModal(null)}
        >
          <form
            onSubmit={handleConfirmLossModal}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md p-6 bg-card border border-border rounded-lg shadow-elevated flex flex-col gap-4"
          >
            <h3 className="text-base font-semibold text-foreground">
              Cerrar como Perdido: {pendingLossModal.deal.title}
            </h3>
            <p className="text-xs text-muted-foreground">
              Indica el motivo por el cual la oportunidad pasa a{" "}
              <strong>{pendingLossModal.targetStage.name}</strong>.
            </p>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="loss-category-select" className="text-xs font-medium text-foreground">
                Categoría principal
              </label>
              <select
                id="loss-category-select"
                value={lossCategoryInput}
                onChange={(e) =>
                  setLossCategoryInput(
                    e.target.value as
                      | "price"
                      | "missing_feature"
                      | "competitor"
                      | "ghosting"
                      | "timing"
                      | "other"
                  )
                }
                className="h-9 px-2.5 bg-background border border-border rounded-md text-xs text-foreground"
              >
                <option value="price">Precio / Presupuesto</option>
                <option value="missing_feature">Funcionalidad faltante</option>
                <option value="competitor">Selección de competidor</option>
                <option value="ghosting">Sin respuesta / Sin decisión</option>
                <option value="timing">Timing / Pospuesto</option>
                <option value="other">Otro motivo</option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="flex flex-col gap-1">
                <label htmlFor="loss-competitor" className="text-[11px] font-medium text-muted-foreground">
                  Competidor (opcional)
                </label>
                <input
                  id="loss-competitor"
                  type="text"
                  value={competitorInput}
                  onChange={(e) => setCompetitorInput(e.target.value)}
                  placeholder="Ej. HubSpot"
                  className="h-8 px-2.5 bg-background border border-border rounded-md text-xs"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="loss-feature" className="text-[11px] font-medium text-muted-foreground">
                  Funcionalidad faltante
                </label>
                <input
                  id="loss-feature"
                  type="text"
                  value={missingFeatureInput}
                  onChange={(e) => setMissingFeatureInput(e.target.value)}
                  placeholder="Ej. SSO/SAML"
                  className="h-8 px-2.5 bg-background border border-border rounded-md text-xs"
                />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="loss-reason-input" className="text-xs font-medium text-foreground">
                Motivo de pérdida <span className="text-destructive">*</span>
              </label>
              <textarea
                id="loss-reason-input"
                rows={3}
                value={lossReasonInput}
                onChange={(e) => {
                  setLossReasonInput(e.target.value);
                  setLossFormError(null);
                }}
                placeholder="Ej. Presupuesto congelado hasta Q1 / Selección de competidor..."
                className="w-full p-2.5 bg-background border border-border rounded-md text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
              {lossFormError && (
                <span role="alert" className="text-[11px] text-destructive">
                  {lossFormError}
                </span>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setPendingLossModal(null)}
              >
                Cancelar
              </Button>
              <Button type="submit" variant="destructive" size="sm">
                Confirmar Cierre Perdido
              </Button>
            </div>
          </form>
        </div>
      )}

      {pendingStageGate && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/75 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Completar requisito de etapa"
          onClick={() => setPendingStageGate(null)}
        >
          <form
            onSubmit={handleConfirmStageGate}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-sm p-5 bg-card border border-border rounded-lg shadow-elevated flex flex-col gap-3.5"
          >
            <div className="flex flex-col gap-0.5">
              <h3 className="text-sm font-semibold text-foreground">
                Requisito para pasar a {pendingStageGate.targetStage.name}
              </h3>
              <p className="text-xs text-muted-foreground">
                Completa este dato en <strong>{pendingStageGate.deal.title}</strong> para mover la oportunidad sin perder el cambio.
              </p>
            </div>
            {pendingStageGate.fields.map((field, idx) => (
              <div key={field.field_key} className="flex flex-col gap-1">
                <label
                  htmlFor={`gate-field-${field.field_key}`}
                  className="text-xs font-medium text-foreground"
                >
                  {field.label} <span className="text-destructive">*</span>
                </label>
                {field.field_type === "select" && field.allowed_values?.length ? (
                  <select
                    id={`gate-field-${field.field_key}`}
                    required
                    autoFocus={idx === 0}
                    value={stageGateValues[field.field_key] || ""}
                    onChange={(e) =>
                      setStageGateValues((prev) => ({
                        ...prev,
                        [field.field_key]: e.target.value,
                      }))
                    }
                    className="h-9 px-2.5 bg-background border border-border rounded-md text-xs"
                  >
                    <option value="">Selecciona una opción...</option>
                    {field.allowed_values.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id={`gate-field-${field.field_key}`}
                    type={field.field_type === "number" ? "number" : field.field_type === "date" ? "date" : "text"}
                    required
                    autoFocus={idx === 0}
                    value={stageGateValues[field.field_key] || ""}
                    onChange={(e) =>
                      setStageGateValues((prev) => ({
                        ...prev,
                        [field.field_key]: e.target.value,
                      }))
                    }
                    placeholder={`Ingresa ${field.label}`}
                    className="h-9 px-2.5 bg-background border border-border rounded-md text-xs font-mono focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                )}
              </div>
            ))}
            <div className="flex justify-end gap-2 pt-1">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setPendingStageGate(null)}
              >
                Cancelar
              </Button>
              <Button type="submit" variant="primary" size="sm" isLoading={isSavingGate}>
                Guardar y Mover
              </Button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
