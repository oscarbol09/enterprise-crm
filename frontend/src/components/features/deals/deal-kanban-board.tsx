"use client";

import React, { useState } from "react";
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  ChevronRight,
  Plus,
  XCircle,
} from "lucide-react";
import { Deal, PipelineStage } from "../../../types/crm";
import { ApiError, moveDealStage } from "../../../lib/api-client";
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
  const [pendingLossModal, setPendingLossModal] = useState<{
    deal: Deal;
    targetStage: PipelineStage;
  } | null>(null);
  const [lossReasonInput, setLossReasonInput] = useState("");
  const [lossFormError, setLossFormError] = useState<string | null>(null);

  const deals = initialDeals.map((d) => {
    const entry = overrides[d.id];
    return entry && entry.base === initialDeals ? entry.deal : d;
  });

  const executeStageTransition = async (
    deal: Deal,
    targetStage: PipelineStage,
    lossReason?: string
  ) => {
    const optimisticDeal: Deal = {
      ...deal,
      stage_id: targetStage.id,
      win_probability: Number(targetStage.default_probability),
      is_won: targetStage.is_closed_won,
      is_lost: targetStage.is_closed_lost,
      loss_reason: targetStage.is_closed_lost ? lossReason || null : null,
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
        { new_stage_id: targetStage.id, loss_reason: lossReason },
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
      setLossFormError(null);
      setPendingLossModal({ deal, targetStage });
      return;
    }

    void executeStageTransition(deal, targetStage);
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
    await executeStageTransition(deal, targetStage, trimmed);
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
          const totalValue = stageDeals.reduce((sum, d) => sum + Number(d.amount), 0);
          const nextStage = stages[stageIndex + 1];

          return (
            <div
              key={stage.id}
              className="flex flex-col gap-3 bg-card/60 backdrop-blur-sm p-3 rounded-lg border border-border min-w-[270px] w-72 shrink-0"
            >
              <div className="flex items-center justify-between pb-2 border-b border-border">
                <div className="flex items-center gap-2">
                  <h3 className="font-semibold text-sm text-foreground">{stage.name}</h3>
                  <Badge variant="secondary" className="text-xs px-1.5 py-0">
                    {stageDeals.length}
                  </Badge>
                </div>
                <span className="text-xs font-mono text-muted-foreground">
                  ${totalValue.toLocaleString("en-US", { minimumFractionDigits: 0 })}
                </span>
              </div>

              <div
                className="flex flex-col gap-2.5 min-h-[380px]"
                role="list"
                aria-label={`Oportunidades en ${stage.name}`}
              >
                {stageDeals.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-44 border border-dashed border-border rounded-md p-4 text-center">
                    <p className="text-xs text-muted-foreground mb-3">
                      No hay tratos en esta etapa
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

                    return (
                      <article
                        key={deal.id}
                        role="listitem"
                        tabIndex={0}
                        aria-roledescription="tarjeta de oportunidad de venta"
                        aria-label={`${deal.title}, valor $${numericAmount.toLocaleString("en-US")}, probabilidad ${probabilityPct}%`}
                        className={`group relative flex flex-col gap-2 p-3.5 bg-card hover:bg-muted/30 rounded-md border border-border shadow-card transition-all duration-150 cursor-pointer focus-visible:ring-2 focus-visible:ring-primary ${
                          isTransitioning ? "opacity-60 scale-[0.99] border-primary/50" : ""
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
                          <h4 className="font-medium text-sm text-foreground group-hover:text-primary transition-colors line-clamp-2">
                            {deal.title}
                          </h4>
                          {deal.is_won ? (
                            <Badge variant="success" className="gap-1 text-[11px] shrink-0">
                              <CheckCircle2 className="h-3 w-3" /> Ganado
                            </Badge>
                          ) : deal.is_lost ? (
                            <Badge variant="destructive" className="gap-1 text-[11px] shrink-0">
                              <XCircle className="h-3 w-3" /> Perdido
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="text-[11px] shrink-0 font-mono">
                              {probabilityPct}%
                            </Badge>
                          )}
                        </div>

                        <div className="flex items-center justify-between text-xs text-muted-foreground pt-1 border-t border-border/50">
                          <span className="font-semibold font-mono text-foreground text-sm">
                            ${numericAmount.toLocaleString("en-US", { minimumFractionDigits: 0 })}{" "}
                            <span className="text-[10px] font-normal text-muted-foreground">
                              {deal.currency}
                            </span>
                          </span>
                          {deal.expected_close_date && (
                            <div className="flex items-center gap-1 text-[11px]">
                              <Calendar className="h-3 w-3" aria-hidden="true" />
                              <span>{deal.expected_close_date}</span>
                            </div>
                          )}
                        </div>

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
            className="w-full max-w-md p-6 bg-card border border-border rounded-xl shadow-elevated flex flex-col gap-4"
          >
            <h3 className="text-base font-semibold text-foreground">
              Cerrar como Perdido: {pendingLossModal.deal.title}
            </h3>
            <p className="text-xs text-muted-foreground">
              Indica el motivo por el cual la oportunidad pasa a{" "}
              <strong>{pendingLossModal.targetStage.name}</strong>.
            </p>
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
    </div>
  );
}
