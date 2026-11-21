"use client";

import React, { useEffect, useState } from "react";
import { AlertTriangle, Check, Edit3, X } from "lucide-react";
import { Deal, PipelineStage } from "../../../types/crm";
import { ApiError, moveDealStage, updateDeal } from "../../../lib/api-client";
import { Badge } from "../../ui/badge";

interface DealDataGridProps {
  stages: PipelineStage[];
  deals: Deal[];
  authToken?: string;
  isReadonly?: boolean;
  onDealClick?: (deal: Deal) => void;
  onDealUpdated?: (updatedDeal: Deal) => void;
}

export function DealDataGrid({
  stages,
  deals,
  authToken,
  isReadonly = false,
  onDealClick,
  onDealUpdated,
}: DealDataGridProps) {
  const [editingAmountId, setEditingAmountId] = useState<string | null>(null);
  const [amountDraft, setAmountDraft] = useState<string>("");
  const [savingId, setSavingId] = useState<string | null>(null);
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (deals.length === 0) return;
    const handleKeyNav = (e: KeyboardEvent) => {
      const target = e.target;
      if (target instanceof HTMLElement) {
        const tag = target.tagName.toLowerCase();
        if (tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable) {
          return;
        }
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      const key = e.key.toLowerCase();
      if (key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setFocusedIndex((prev) => (prev < deals.length - 1 ? prev + 1 : 0));
      } else if (key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setFocusedIndex((prev) => (prev > 0 ? prev - 1 : deals.length - 1));
      } else if ((e.key === " " || e.key === "Enter") && focusedIndex >= 0 && focusedIndex < deals.length) {
        e.preventDefault();
        onDealClick?.(deals[focusedIndex]);
      }
    };
    window.addEventListener("keydown", handleKeyNav);
    return () => window.removeEventListener("keydown", handleKeyNav);
  }, [deals, focusedIndex, onDealClick]);

  const todayIso = new Date().toISOString().slice(0, 10);

  const activeDeals = deals.filter((d) => !d.is_lost);
  const grossTotal = activeDeals.reduce(
    (sum, d) => sum + Number(d.normalized_amount_usd ?? d.amount),
    0
  );
  const weightedTotal = activeDeals.reduce(
    (sum, d) => sum + Number(d.normalized_amount_usd ?? d.amount) * Number(d.win_probability),
    0
  );
  const avgTicket = activeDeals.length > 0 ? Math.round(grossTotal / activeDeals.length) : 0;
  const commitCount = activeDeals.filter(
    (d) => d.forecast_category === "commit" || d.is_won
  ).length;

  const startEditAmount = (e: React.MouseEvent, deal: Deal) => {
    e.stopPropagation();
    if (isReadonly) return;
    setEditingAmountId(deal.id);
    setAmountDraft(String(deal.amount));
    setError(null);
  };

  const commitAmountEdit = async (deal: Deal) => {
    const parsed = Number(amountDraft);
    if (Number.isNaN(parsed) || parsed < 0) {
      setError("El monto debe ser un número válido mayor o igual a 0.");
      return;
    }
    setSavingId(deal.id);
    setError(null);
    try {
      const updated = await updateDeal(deal.id, { amount: parsed }, authToken);
      setEditingAmountId(null);
      onDealUpdated?.(updated);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo actualizar el monto.");
    } finally {
      setSavingId(null);
    }
  };

  const handleInlineStageChange = async (deal: Deal, newStageId: string) => {
    if (deal.stage_id === newStageId) return;
    const targetStage = stages.find((s) => s.id === newStageId);
    if (!targetStage) return;

    let lossReason: string | undefined;
    if (targetStage.is_closed_lost) {
      lossReason = "Cerrado perdido desde tabla operativa";
    }

    setSavingId(deal.id);
    setError(null);
    try {
      const updated = await moveDealStage(
        deal.id,
        { new_stage_id: newStageId, loss_reason: lossReason },
        authToken
      );
      onDealUpdated?.(updated);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo cambiar la etapa.");
    } finally {
      setSavingId(null);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      {error && (
        <div
          role="alert"
          className="p-2.5 text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-md"
        >
          {error}
        </div>
      )}

      <div className="bg-card border border-border rounded-lg shadow-card overflow-hidden">
        <div className="overflow-x-auto">
          <table
            className="w-full text-left text-xs tabular-nums"
            aria-label="Tabla de alta densidad de oportunidades"
          >
            <thead className="bg-muted/60 border-b border-border text-muted-foreground font-medium uppercase tracking-wider text-[11px]">
              <tr>
                <th scope="col" className="py-2.5 px-3.5">
                  Oportunidad
                </th>
                <th scope="col" className="py-2.5 px-3.5">
                  Etapa (Inline)
                </th>
                <th scope="col" className="py-2.5 px-3.5 text-right">
                  Monto Bruto
                </th>
                <th scope="col" className="py-2.5 px-3.5 text-right">
                  Prob.
                </th>
                <th scope="col" className="py-2.5 px-3.5 text-right">
                  Valor Ponderado
                </th>
                <th scope="col" className="py-2.5 px-3.5">
                  Categoría Forecast
                </th>
                <th scope="col" className="py-2.5 px-3.5">
                  Cierre Estimado
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {deals.map((deal, rowIdx) => {
                const isEditingAmount = editingAmountId === deal.id;
                const isRowSaving = savingId === deal.id;
                const isFocused = focusedIndex === rowIdx;
                const normalizedUsd = Number(deal.normalized_amount_usd ?? deal.amount);
                const weighted = Math.round(normalizedUsd * Number(deal.win_probability));
                const probPct = Math.round(Number(deal.win_probability) * 100);
                const overdue =
                  !deal.is_won &&
                  !deal.is_lost &&
                  Boolean(deal.expected_close_date && deal.expected_close_date < todayIso);

                return (
                  <tr
                    key={deal.id}
                    data-focused={isFocused ? "true" : "false"}
                    onClick={() => {
                      setFocusedIndex(rowIdx);
                      onDealClick?.(deal);
                    }}
                    className={`hover:bg-muted/30 transition-colors cursor-pointer ${
                      isRowSaving ? "opacity-60" : ""
                    } ${isFocused ? "bg-primary/10 ring-1 ring-inset ring-primary/40" : ""}`}
                  >
                    <td className="py-2 px-3.5 font-medium text-foreground">
                      <div className="flex items-center gap-2">
                        <span>{deal.title}</span>
                        {(deal.close_date_push_count ?? 0) > 0 && (
                          <Badge variant="warning" className="text-[10px] py-0 px-1">
                            Slip x{deal.close_date_push_count}
                          </Badge>
                        )}
                      </div>
                    </td>

                    <td className="py-2 px-3.5" onClick={(e) => e.stopPropagation()}>
                      <select
                        aria-label={`Cambiar etapa de ${deal.title}`}
                        disabled={isReadonly || isRowSaving}
                        value={deal.stage_id}
                        onChange={(e) => void handleInlineStageChange(deal, e.target.value)}
                        className="h-7 px-2 bg-background border border-border rounded text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                      >
                        {stages.map((st) => (
                          <option key={st.id} value={st.id}>
                            {st.name}
                          </option>
                        ))}
                      </select>
                    </td>

                    <td
                      className="py-2 px-3.5 text-right font-mono font-semibold text-foreground"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {isEditingAmount ? (
                        <div className="inline-flex items-center justify-end gap-1">
                          <input
                            type="number"
                            min={0}
                            step="100"
                            aria-label={`Monto de ${deal.title}`}
                            value={amountDraft}
                            onChange={(e) => setAmountDraft(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault();
                                void commitAmountEdit(deal);
                              } else if (e.key === "Escape") {
                                e.preventDefault();
                                setEditingAmountId(null);
                              }
                            }}
                            className="w-28 h-7 px-2 text-right bg-background border border-primary rounded text-xs font-mono focus:outline-none"
                            autoFocus
                          />
                          <button
                            type="button"
                            aria-label={`Guardar monto de ${deal.title}`}
                            onClick={() => void commitAmountEdit(deal)}
                            className="p-1 text-success hover:bg-success/10 rounded"
                          >
                            <Check className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            aria-label="Cancelar edición de monto"
                            onClick={() => setEditingAmountId(null)}
                            className="p-1 text-muted-foreground hover:text-foreground rounded"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={(e) => startEditAmount(e, deal)}
                          aria-label={`Editar monto de ${deal.title}`}
                          className="inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded hover:bg-muted transition-colors"
                        >
                          <span>
                            ${Number(deal.amount).toLocaleString("en-US")} {deal.currency}
                            {deal.currency !== "USD" && (
                              <span className="text-[10px] font-normal text-muted-foreground ml-1">
                                (≈${normalizedUsd.toLocaleString("en-US")} USD)
                              </span>
                            )}
                          </span>
                          {!isReadonly && (
                            <Edit3 className="h-3 w-3 text-muted-foreground/70" aria-hidden="true" />
                          )}
                        </button>
                      )}
                    </td>

                    <td className="py-2 px-3.5 text-right font-mono text-muted-foreground">
                      {probPct}%
                    </td>

                    <td className="py-2 px-3.5 text-right font-mono text-foreground">
                      ${weighted.toLocaleString("en-US")}
                    </td>

                    <td className="py-2 px-3.5">
                      <Badge
                        variant={
                          deal.is_won
                            ? "success"
                            : deal.is_lost
                            ? "destructive"
                            : deal.forecast_category === "commit"
                            ? "default"
                            : "secondary"
                        }
                        className="text-[10px] uppercase"
                      >
                        {deal.forecast_category}
                      </Badge>
                    </td>

                    <td className="py-2 px-3.5 font-mono text-muted-foreground">
                      {deal.expected_close_date ? (
                        <span
                          className={`inline-flex items-center gap-1 ${
                            overdue ? "text-warning font-semibold" : ""
                          }`}
                        >
                          {overdue && <AlertTriangle className="h-3 w-3" aria-hidden="true" />}
                          <span>{deal.expected_close_date}</span>
                          {overdue && <span className="text-[10px] uppercase">(Vencido)</span>}
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot className="bg-muted/40 border-t border-border font-mono text-xs">
              <tr>
                <td className="py-2.5 px-3.5 font-semibold text-foreground">
                  TOTAL ({activeDeals.length} activos · {commitCount} en Commit)
                </td>
                <td className="py-2.5 px-3.5 text-muted-foreground">
                  Ticket Promedio: ${avgTicket.toLocaleString("en-US")}
                </td>
                <td className="py-2.5 px-3.5 text-right font-bold text-foreground">
                  ${grossTotal.toLocaleString("en-US")}
                </td>
                <td className="py-2.5 px-3.5 text-right text-muted-foreground">Ponderado:</td>
                <td className="py-2.5 px-3.5 text-right font-bold text-primary">
                  ${Math.round(weightedTotal).toLocaleString("en-US")}
                </td>
                <td colSpan={2} className="py-2.5 px-3.5 text-right text-muted-foreground">
                  Atajos: j/k navegar · Espacio abrir · Click en monto para editar
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </div>
  );
}
