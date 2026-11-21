"use client";

import React, { useCallback, useEffect, useState } from "react";
import { AlertCircle, AlertTriangle, Camera, Download, RefreshCw } from "lucide-react";
import {
  AttributionAnalytics,
  ForecastAnalytics,
  FunnelAnalytics,
  WaterfallBridge,
  WinLossAnalytics,
} from "../../../types/crm";
import {
  ApiError,
  capturePipelineSnapshot,
  exportEntityCsv,
  fetchAttributionAnalytics,
  fetchForecastAnalytics,
  fetchFunnelAnalytics,
  fetchWaterfallBridge,
  fetchWinLossAnalytics,
} from "../../../lib/api-client";
import { Badge } from "../../ui/badge";
import { Button } from "../../ui/button";

interface RevenueReportsDashboardProps {
  authToken?: string;
}

function fmtUsd(value: number): string {
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

export function RevenueReportsDashboard({ authToken }: RevenueReportsDashboardProps) {
  const [quotaInput, setQuotaInput] = useState<string>("250000");
  const [forecast, setForecast] = useState<ForecastAnalytics | null>(null);
  const [funnel, setFunnel] = useState<FunnelAnalytics | null>(null);
  const [attribution, setAttribution] = useState<AttributionAnalytics | null>(null);
  const [waterfall, setWaterfall] = useState<WaterfallBridge | null>(null);
  const [winLoss, setWinLoss] = useState<WinLossAnalytics | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isCapturingSnapshot, setIsCapturingSnapshot] = useState<boolean>(false);
  const [exportingEntity, setExportingEntity] = useState<string | null>(null);
  const [exportNotice, setExportNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadReports = useCallback(
    async (explicitQuota?: number) => {
      setIsLoading(true);
      setError(null);
      const parsedQuota =
        explicitQuota !== undefined ? explicitQuota : Number(quotaInput) > 0 ? Number(quotaInput) : undefined;
      try {
        const [fRes, funRes, attrRes, wfRes, wlRes] = await Promise.all([
          fetchForecastAnalytics(parsedQuota, 14, authToken),
          fetchFunnelAnalytics(authToken),
          fetchAttributionAnalytics(authToken),
          fetchWaterfallBridge(undefined, undefined, authToken).catch(() => null),
          fetchWinLossAnalytics(authToken).catch(() => null),
        ]);
        setForecast(fRes);
        setFunnel(funRes);
        setAttribution(attrRes);
        setWaterfall(wfRes);
        setWinLoss(wlRes);
      } catch (err: unknown) {
        setError(err instanceof ApiError ? err.message : "No se pudieron cargar los reportes financieros.");
      } finally {
        setIsLoading(false);
      }
    },
    [authToken, quotaInput]
  );

  useEffect(() => {
    let active = true;
    async function initReports() {
      try {
        const [fRes, funRes, attrRes, wfRes, wlRes] = await Promise.all([
          fetchForecastAnalytics(250000, 14, authToken),
          fetchFunnelAnalytics(authToken),
          fetchAttributionAnalytics(authToken),
          fetchWaterfallBridge(undefined, undefined, authToken).catch(() => null),
          fetchWinLossAnalytics(authToken).catch(() => null),
        ]);
        if (!active) return;
        setForecast(fRes);
        setFunnel(funRes);
        setAttribution(attrRes);
        setWaterfall(wfRes);
        setWinLoss(wlRes);
      } catch (err: unknown) {
        if (active) {
          setError(err instanceof ApiError ? err.message : "No se pudieron cargar los reportes financieros.");
        }
      } finally {
        if (active) setIsLoading(false);
      }
    }
    void initReports();
    return () => {
      active = false;
    };
  }, [authToken]);

  const handleCaptureSnapshot = async () => {
    setIsCapturingSnapshot(true);
    setError(null);
    setExportNotice(null);
    try {
      const snap = await capturePipelineSnapshot(undefined, authToken);
      setExportNotice(
        `Snapshot capturado (${snap.snapshot_date}): ${snap.captured_deals} tratos · ${fmtUsd(snap.total_open_usd)} abierto.`
      );
      await loadReports();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo capturar el snapshot.");
    } finally {
      setIsCapturingSnapshot(false);
    }
  };

  const handleApplyQuota = (e: React.FormEvent) => {
    e.preventDefault();
    const numeric = Number(quotaInput);
    void loadReports(numeric > 0 ? numeric : undefined);
  };

  const handleExportCsv = async (entity: "deals" | "contacts" | "accounts") => {
    setExportingEntity(entity);
    setExportNotice(null);
    setError(null);
    try {
      const csvText = await exportEntityCsv(entity, authToken);
      if (typeof window !== "undefined" && typeof URL.createObjectURL === "function") {
        const blob = new Blob([csvText], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `crm_${entity}_export.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }
      setExportNotice(`Exportación CSV de ${entity} descargada con protección contra inyección de fórmulas.`);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : `No se pudo exportar ${entity}.`);
    } finally {
      setExportingEntity(null);
    }
  };

  const coverageRatio = forecast?.pipeline_coverage_ratio ?? null;
  const coverageHealthy = coverageRatio !== null && coverageRatio >= 3;

  return (
    <div className="flex flex-col gap-6 p-6 max-w-6xl w-full mx-auto">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-border">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-foreground">
            Reportes de Ingresos y Forecast
          </h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Cifras normalizadas en USD, velocidad comercial, embudo real por etapa y atribución de ingresos por canal.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <form onSubmit={handleApplyQuota} className="flex items-center gap-1.5">
            <label htmlFor="quota-input" className="text-xs text-muted-foreground">
              Meta USD:
            </label>
            <input
              id="quota-input"
              type="number"
              min={0}
              step="1000"
              value={quotaInput}
              onChange={(e) => setQuotaInput(e.target.value)}
              className="w-28 h-8 px-2 bg-card border border-border rounded-md text-xs font-mono tabular-nums"
            />
            <Button type="submit" variant="outline" size="sm">
              Calcular
            </Button>
          </form>

          <Button
            variant="outline"
            size="sm"
            onClick={() => void handleCaptureSnapshot()}
            isLoading={isCapturingSnapshot}
            className="gap-1.5"
          >
            <Camera className="h-3.5 w-3.5" />
            <span>Capturar Snapshot</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void handleExportCsv("deals")}
            isLoading={exportingEntity === "deals"}
            className="gap-1.5"
          >
            <Download className="h-3.5 w-3.5" />
            <span>Deals CSV</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void handleExportCsv("contacts")}
            isLoading={exportingEntity === "contacts"}
            className="gap-1.5"
          >
            <Download className="h-3.5 w-3.5" />
            <span>Contactos CSV</span>
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => void loadReports()}
            isLoading={isLoading}
            className="gap-1.5"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Actualizar</span>
          </Button>
        </div>
      </div>

      {exportNotice && (
        <div
          role="status"
          className="p-3 text-xs text-foreground bg-muted border border-border rounded-md flex items-center justify-between"
        >
          <span>{exportNotice}</span>
          <button
            type="button"
            onClick={() => setExportNotice(null)}
            className="text-muted-foreground hover:text-foreground"
          >
            Cerrar
          </button>
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 p-3 text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-md"
        >
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {isLoading || !forecast ? (
        <div className="p-10 text-center text-xs text-muted-foreground bg-card border border-border rounded-lg">
          Calculando indicadores financieros del periodo...
        </div>
      ) : (
        <>
          {/* Core Financial Metrics Strip */}
          <section
            aria-label="Resumen financiero del pipeline"
            className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3"
          >
            <div className="p-3.5 bg-card border border-border rounded-lg shadow-subtle flex flex-col gap-1">
              <span className="text-[11px] text-muted-foreground">Cerrado Ganado</span>
              <span className="text-lg font-bold font-mono text-success tabular-nums">
                {fmtUsd(forecast.closed_won_usd)}
              </span>
              <span className="text-[11px] text-muted-foreground tabular-nums">
                {forecast.won_deals_count} ganados
              </span>
            </div>

            <div className="p-3.5 bg-card border border-border rounded-lg shadow-subtle flex flex-col gap-1">
              <span className="text-[11px] text-muted-foreground">Proyección Total</span>
              <span className="text-lg font-bold font-mono text-foreground tabular-nums">
                {fmtUsd(forecast.total_projected_usd)}
              </span>
              <span className="text-[11px] text-muted-foreground tabular-nums">
                Ponderado: {fmtUsd(forecast.weighted_open_usd)}
              </span>
            </div>

            <div className="p-3.5 bg-card border border-border rounded-lg shadow-subtle flex flex-col gap-1">
              <span className="text-[11px] text-muted-foreground">Cobertura vs Meta</span>
              <div className="flex items-center gap-1.5">
                <span className="text-lg font-bold font-mono text-foreground tabular-nums">
                  {coverageRatio !== null ? `${coverageRatio.toFixed(2)}x` : "—"}
                </span>
                {coverageRatio !== null && (
                  <Badge variant={coverageHealthy ? "success" : "warning"}>
                    {coverageHealthy ? "Sana" : "<3x"}
                  </Badge>
                )}
              </div>
              <span className="text-[11px] text-muted-foreground tabular-nums">
                Abierto: {fmtUsd(forecast.open_pipeline_usd)}
              </span>
            </div>

            <div className="p-3.5 bg-card border border-border rounded-lg shadow-subtle flex flex-col gap-1">
              <span className="text-[11px] text-muted-foreground">Velocidad Comercial</span>
              <span className="text-lg font-bold font-mono text-primary tabular-nums">
                {fmtUsd(forecast.sales_velocity_usd_per_day)}/d
              </span>
              <span className="text-[11px] text-muted-foreground tabular-nums">
                Ciclo: {forecast.avg_sales_cycle_days.toFixed(1)} días
              </span>
            </div>

            <div className="p-3.5 bg-card border border-border rounded-lg shadow-subtle flex flex-col gap-1">
              <span className="text-[11px] text-muted-foreground">Tasa de Cierre</span>
              <span className="text-lg font-bold font-mono text-foreground tabular-nums">
                {Math.round(forecast.win_rate * 100)}%
              </span>
              <span className="text-[11px] text-muted-foreground tabular-nums">
                Ticket: {fmtUsd(forecast.avg_won_deal_usd)}
              </span>
            </div>

            <div className="p-3.5 bg-card border border-border rounded-lg shadow-subtle flex flex-col gap-1">
              <span className="text-[11px] text-muted-foreground">USD en Riesgo</span>
              <span className="text-lg font-bold font-mono text-warning tabular-nums">
                {fmtUsd(forecast.usd_at_risk)}
              </span>
              <span className="text-[11px] text-muted-foreground tabular-nums">
                {forecast.at_risk_deals.length} tratos con alerta
              </span>
            </div>
          </section>

          {/* Forecast by Period + Risk Radar */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            <section className="bg-card border border-border rounded-lg shadow-card overflow-hidden flex flex-col">
              <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                <h2 className="text-sm font-semibold text-foreground">Forecast por Período (USD)</h2>
                <span className="text-[11px] font-mono text-muted-foreground">
                  Commit: {fmtUsd(forecast.commit_usd)}
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs tabular-nums" aria-label="Forecast por periodo">
                  <thead className="bg-muted/50 border-b border-border text-[11px] text-muted-foreground uppercase">
                    <tr>
                      <th className="py-2 px-3">Período</th>
                      <th className="py-2 px-3 text-right">Ganado</th>
                      <th className="py-2 px-3 text-right">Commit</th>
                      <th className="py-2 px-3 text-right">Ponderado</th>
                      <th className="py-2 px-3 text-right">Tratos</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border font-mono">
                    {forecast.by_period.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="py-6 text-center text-muted-foreground font-sans">
                          Sin oportunidades registradas.
                        </td>
                      </tr>
                    ) : (
                      forecast.by_period.map((row) => (
                        <tr key={row.period} className="hover:bg-muted/20">
                          <td className="py-2 px-3 font-medium text-foreground">{row.period}</td>
                          <td className="py-2 px-3 text-right text-success">
                            {fmtUsd(row.closed_won_usd)}
                          </td>
                          <td className="py-2 px-3 text-right text-foreground">
                            {fmtUsd(row.commit_usd)}
                          </td>
                          <td className="py-2 px-3 text-right text-primary font-semibold">
                            {fmtUsd(row.weighted_open_usd)}
                          </td>
                          <td className="py-2 px-3 text-right text-muted-foreground">
                            {row.deal_count}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>

            <section className="bg-card border border-border rounded-lg shadow-card overflow-hidden flex flex-col">
              <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                <h2 className="text-sm font-semibold text-foreground">
                  Radar de Riesgo (Slippage y Vencidos)
                </h2>
                <Badge variant={forecast.at_risk_deals.length > 0 ? "warning" : "success"}>
                  {forecast.at_risk_deals.length} alertas
                </Badge>
              </div>
              {forecast.at_risk_deals.length === 0 ? (
                <div className="p-6 text-xs text-muted-foreground">
                  No hay oportunidades abiertas con fecha vencida o estancamiento superior a 14 días.
                </div>
              ) : (
                <ul className="divide-y divide-border">
                  {forecast.at_risk_deals.map((item) => (
                    <li
                      key={item.deal_id}
                      className="px-4 py-2.5 text-xs flex items-center justify-between gap-3"
                    >
                      <div className="flex flex-col min-w-0">
                        <span className="font-medium text-foreground truncate">{item.title}</span>
                        <span className="text-[11px] text-warning flex items-center gap-1">
                          <AlertTriangle className="h-3 w-3 shrink-0" />
                          <span>{item.risk_reasons.join(" · ")}</span>
                        </span>
                      </div>
                      <span className="font-mono font-semibold text-foreground shrink-0 tabular-nums">
                        {fmtUsd(item.normalized_amount_usd)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          {/* Revenue Attribution by Source Channel */}
          {attribution && (
            <section className="bg-card border border-border rounded-lg shadow-card overflow-hidden">
              <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-foreground">
                    Atribución de Ingresos por Canal (Leads vs. Ingresos Reales)
                  </h2>
                </div>
                <span className="text-[11px] font-mono text-muted-foreground tabular-nums">
                  {attribution.total_leads} contactos · {fmtUsd(attribution.total_closed_won_usd)} ganados
                </span>
              </div>
              <div className="overflow-x-auto">
                <table
                  className="w-full text-left text-xs tabular-nums"
                  aria-label="Tabla de atribución por canal"
                >
                  <thead className="bg-muted/50 border-b border-border text-[11px] text-muted-foreground uppercase">
                    <tr>
                      <th className="py-2 px-4">Canal</th>
                      <th className="py-2 px-4 text-right">Leads</th>
                      <th className="py-2 px-4 text-right">Oportunidades</th>
                      <th className="py-2 px-4 text-right">Ganados</th>
                      <th className="py-2 px-4 text-right">Win Rate</th>
                      <th className="py-2 px-4 text-right">Pipeline Generado</th>
                      <th className="py-2 px-4 text-right">Ingresos Ganados (USD)</th>
                      <th className="py-2 px-4 text-right">Participación</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border font-mono">
                    {attribution.channels.map((ch) => (
                      <tr key={ch.source_channel} className="hover:bg-muted/20">
                        <td className="py-2 px-4 font-sans font-medium text-foreground capitalize">
                          {ch.source_channel.replace(/_/g, " ")}
                        </td>
                        <td className="py-2 px-4 text-right text-muted-foreground">
                          {ch.leads_count}
                        </td>
                        <td className="py-2 px-4 text-right text-muted-foreground">
                          {ch.opportunities_count}
                        </td>
                        <td className="py-2 px-4 text-right text-foreground">
                          {ch.won_deals_count}
                        </td>
                        <td className="py-2 px-4 text-right text-muted-foreground">
                          {Math.round(ch.win_rate * 100)}%
                        </td>
                        <td className="py-2 px-4 text-right text-muted-foreground">
                          {fmtUsd(ch.pipeline_generated_usd)}
                        </td>
                        <td className="py-2 px-4 text-right font-semibold text-success">
                          {fmtUsd(ch.closed_won_revenue_usd)}
                        </td>
                        <td className="py-2 px-4 text-right text-foreground">
                          {ch.revenue_share_pct.toFixed(1)}%
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Stage Conversion Funnel */}
          {funnel && (
            <section className="bg-card border border-border rounded-lg shadow-card overflow-hidden">
              <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                <h2 className="text-sm font-semibold text-foreground">
                  Embudo de Conversión y Permanencia por Etapa
                </h2>
                {funnel.bottleneck_stage_name && (
                  <Badge variant="warning">Cuello de botella: {funnel.bottleneck_stage_name}</Badge>
                )}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs tabular-nums" aria-label="Embudo de conversión">
                  <thead className="bg-muted/50 border-b border-border text-[11px] text-muted-foreground uppercase">
                    <tr>
                      <th className="py-2 px-4">Etapa</th>
                      <th className="py-2 px-4 text-right">Tratos Ingresados</th>
                      <th className="py-2 px-4 text-right">Activos Hoy</th>
                      <th className="py-2 px-4 text-right">Conversión a Siguiente</th>
                      <th className="py-2 px-4 text-right">Permanencia Promedio</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border font-mono">
                    {funnel.stages.map((st) => (
                      <tr key={st.stage_id} className="hover:bg-muted/20">
                        <td className="py-2 px-4 font-sans font-medium text-foreground">
                          {st.stage_name}
                        </td>
                        <td className="py-2 px-4 text-right text-foreground">{st.deals_entered}</td>
                        <td className="py-2 px-4 text-right text-muted-foreground">
                          {st.current_open_deals}
                        </td>
                        <td className="py-2 px-4 text-right text-primary">
                          {st.is_closed_won || st.is_closed_lost
                            ? "—"
                            : `${st.conversion_to_next_pct.toFixed(1)}%`}
                        </td>
                        <td className="py-2 px-4 text-right text-muted-foreground">
                          {st.avg_dwell_days.toFixed(1)} días
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Pipeline Waterfall Bridge & Structured Win/Loss Matrix */}
          {(waterfall || winLoss) && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {waterfall && (
                <section className="bg-card border border-border rounded-lg shadow-card overflow-hidden flex flex-col">
                  <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                    <h2 className="text-sm font-semibold text-foreground">
                      Puente de Pipeline (Waterfall)
                    </h2>
                    <span className="text-[11px] font-mono text-muted-foreground">
                      {waterfall.from_date} → {waterfall.to_date}
                    </span>
                  </div>
                  <div className="p-4 grid grid-cols-2 sm:grid-cols-4 gap-2.5 font-mono text-xs tabular-nums">
                    <div className="p-2.5 bg-muted/40 border border-border rounded">
                      <div className="text-[10px] font-sans text-muted-foreground">Inicial</div>
                      <div className="font-semibold text-foreground">
                        {fmtUsd(waterfall.starting_open_usd)}
                      </div>
                    </div>
                    <div className="p-2.5 bg-muted/40 border border-border rounded">
                      <div className="text-[10px] font-sans text-muted-foreground">+ Nuevos</div>
                      <div className="font-semibold text-success">
                        +{fmtUsd(waterfall.new_deals_usd)}
                      </div>
                    </div>
                    <div className="p-2.5 bg-muted/40 border border-border rounded">
                      <div className="text-[10px] font-sans text-muted-foreground">+ Expansión</div>
                      <div className="font-semibold text-success">
                        +{fmtUsd(waterfall.expansion_usd)}
                      </div>
                    </div>
                    <div className="p-2.5 bg-muted/40 border border-border rounded">
                      <div className="text-[10px] font-sans text-muted-foreground">- Contracción</div>
                      <div className="font-semibold text-warning">
                        -{fmtUsd(waterfall.contraction_usd)}
                      </div>
                    </div>
                    <div className="p-2.5 bg-muted/40 border border-border rounded">
                      <div className="text-[10px] font-sans text-muted-foreground">- Ganados</div>
                      <div className="font-semibold text-primary">
                        -{fmtUsd(waterfall.closed_won_usd)}
                      </div>
                    </div>
                    <div className="p-2.5 bg-muted/40 border border-border rounded">
                      <div className="text-[10px] font-sans text-muted-foreground">- Perdidos</div>
                      <div className="font-semibold text-destructive">
                        -{fmtUsd(waterfall.closed_lost_usd)}
                      </div>
                    </div>
                    <div className="p-2.5 bg-primary/10 border border-primary/25 rounded col-span-2">
                      <div className="text-[10px] font-sans text-muted-foreground">
                        = Pipeline Final ({waterfall.slipped_deals_count} pospuestos)
                      </div>
                      <div className="font-bold text-foreground">
                        {fmtUsd(waterfall.ending_open_usd)}
                      </div>
                    </div>
                  </div>
                </section>
              )}

              {winLoss && (
                <section className="bg-card border border-border rounded-lg shadow-card overflow-hidden flex flex-col">
                  <div className="px-4 py-3 border-b border-border flex items-center justify-between">
                    <h2 className="text-sm font-semibold text-foreground">
                      Matriz Win/Loss (Motivos y Competidores)
                    </h2>
                    <span className="text-[11px] font-mono text-destructive tabular-nums">
                      {winLoss.total_lost_deals} perdidos · {fmtUsd(winLoss.total_lost_usd)}
                    </span>
                  </div>
                  <div className="p-4 flex flex-col gap-3 text-xs">
                    {winLoss.by_category.length === 0 ? (
                      <p className="text-muted-foreground">
                        No hay oportunidades perdidas registradas aún.
                      </p>
                    ) : (
                      <div className="flex flex-col gap-1.5">
                        <span className="text-[11px] font-medium text-muted-foreground uppercase">
                          Por categoría de pérdida
                        </span>
                        {winLoss.by_category.map((item) => (
                          <div
                            key={item.category}
                            className="flex items-center justify-between py-1 border-b border-border/50 tabular-nums"
                          >
                            <span className="capitalize text-foreground">
                              {item.category.replace(/_/g, " ")} ({item.lost_deals_count})
                            </span>
                            <span className="font-mono font-semibold text-destructive">
                              {fmtUsd(item.lost_usd)}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}

                    {winLoss.by_competitor.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {winLoss.by_competitor.map((c) => (
                          <Badge key={c.name} variant="outline" className="font-mono">
                            vs {c.name}: {fmtUsd(c.lost_usd)}
                          </Badge>
                        ))}
                      </div>
                    )}

                    {winLoss.by_missing_feature.length > 0 && (
                      <div className="flex flex-wrap gap-1.5">
                        {winLoss.by_missing_feature.map((f) => (
                          <Badge key={f.name} variant="warning" className="font-mono">
                            Brecha {f.name}: {fmtUsd(f.lost_usd)}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                </section>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
