"use client";

import React, { useState } from "react";
import { AlertCircle, CheckCircle2, RotateCcw, Upload, X } from "lucide-react";
import { CSVImportResponse } from "../../../types/crm";
import { ApiError, importContactsCsv, rollbackImportBatch } from "../../../lib/api-client";
import { Badge } from "../../ui/badge";
import { Button } from "../../ui/button";

interface CsvImportModalProps {
  isOpen: boolean;
  authToken?: string;
  onClose: () => void;
  onImported: () => Promise<void> | void;
}

export function CsvImportModal({
  isOpen,
  authToken,
  onClose,
  onImported,
}: CsvImportModalProps) {
  const [csvContent, setCsvContent] = useState("");
  const [dedupeStrategy, setDedupeStrategy] = useState<"skip" | "update">("skip");
  const [preview, setPreview] = useState<CSVImportResponse | null>(null);
  const [rollbackNotice, setRollbackNotice] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isRollingBack, setIsRollingBack] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setCsvContent(text);
    setPreview(null);
    setRollbackNotice(null);
    setError(null);
  };

  const handleRunImport = async (dryRun: boolean) => {
    if (!csvContent.trim()) return;
    setIsRunning(true);
    setError(null);
    setRollbackNotice(null);
    try {
      const res = await importContactsCsv(
        {
          csv_content: csvContent,
          dry_run: dryRun,
          dedupe_strategy: dedupeStrategy,
        },
        authToken
      );
      setPreview(res);
      if (!dryRun) {
        await onImported();
      }
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo procesar el archivo CSV.");
    } finally {
      setIsRunning(false);
    }
  };

  const handleRollbackBatch = async () => {
    if (!preview?.import_batch_id) return;
    setIsRollingBack(true);
    setError(null);
    try {
      const rb = await rollbackImportBatch(preview.import_batch_id, authToken);
      setRollbackNotice(
        `Lote revertido: ${rb.reverted_contacts} contactos, ${rb.reverted_accounts} empresas y ${rb.reverted_deals} oportunidades deshechas.`
      );
      setPreview({ ...preview, import_batch_id: null });
      await onImported();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo deshacer la importación.");
    } finally {
      setIsRollingBack(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Importar contactos desde CSV"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-2xl bg-card border border-border rounded-lg shadow-elevated p-6 flex flex-col gap-4 max-h-[90vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between pb-3 border-b border-border">
          <div>
            <h2 className="text-base font-semibold text-foreground">
              Importación CSV con Validación Previa
            </h2>
            <p className="text-xs text-muted-foreground">
              Detecta automáticamente encabezados de HubSpot, Salesforce o Excel en español/inglés.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar importador CSV"
            className="p-1 text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <label className="inline-flex items-center gap-2 text-xs font-medium text-foreground cursor-pointer px-3 py-1.5 bg-muted border border-border rounded-md hover:bg-muted/80">
            <Upload className="h-3.5 w-3.5" />
            <span>Cargar archivo .csv</span>
            <input
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => void handleFileSelected(e)}
              className="sr-only"
            />
          </label>

          <div className="flex items-center gap-2 text-xs">
            <label htmlFor="dedupe-strategy" className="text-muted-foreground">
              Si el correo ya existe:
            </label>
            <select
              id="dedupe-strategy"
              value={dedupeStrategy}
              onChange={(e) => {
                setDedupeStrategy(e.target.value as "skip" | "update");
                setPreview(null);
              }}
              className="h-8 px-2 bg-background border border-border rounded-md text-xs"
            >
              <option value="skip">Omitir duplicado</option>
              <option value="update">Actualizar registro existente</option>
            </select>
          </div>
        </div>

        <textarea
          rows={5}
          aria-label="Contenido CSV de contactos"
          value={csvContent}
          onChange={(e) => {
            setCsvContent(e.target.value);
            setPreview(null);
          }}
          placeholder="First Name,Last Name,Email Address,Company Name,Title,Lead Source&#10;Ana,Torres,ana@empresa.com,Empresa SA,Directora,outbound"
          className="w-full p-3 bg-background border border-border rounded-md text-xs font-mono focus:outline-none focus:ring-2 focus:ring-primary"
        />

        {error && (
          <div
            role="alert"
            className="flex items-center gap-2 p-3 text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-md"
          >
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {preview && (
          <div className="p-4 rounded-md bg-muted/40 border border-border flex flex-col gap-2.5 text-xs">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-foreground flex items-center gap-1.5">
                <CheckCircle2 className="h-4 w-4 text-success" />
                {preview.dry_run
                  ? "Resultado de Simulación (Sin cambios en base de datos)"
                  : "Importación Aplicada"}
              </span>
              <Badge variant={preview.quarantined_count > 0 ? "warning" : "success"}>
                {preview.total_rows} filas evaluadas
              </Badge>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 font-mono tabular-nums">
              <div className="p-2 bg-card border border-border rounded">
                <div className="text-[10px] text-muted-foreground">Contactos</div>
                <div className="font-semibold text-success">
                  {preview.dry_run ? preview.would_create : preview.created_count}
                </div>
              </div>
              <div className="p-2 bg-card border border-border rounded">
                <div className="text-[10px] text-muted-foreground">Oportunidades</div>
                <div className="font-semibold text-foreground">
                  {preview.dry_run
                    ? preview.would_create_deals ?? 0
                    : preview.deals_created_count ?? 0}
                </div>
              </div>
              <div className="p-2 bg-card border border-border rounded">
                <div className="text-[10px] text-muted-foreground">Actualizar</div>
                <div className="font-semibold text-primary">
                  {preview.dry_run ? preview.would_update : preview.updated_count}
                </div>
              </div>
              <div className="p-2 bg-card border border-border rounded">
                <div className="text-[10px] text-muted-foreground">Omitir</div>
                <div className="font-semibold text-muted-foreground">
                  {preview.dry_run ? preview.would_skip : preview.skipped_count}
                </div>
              </div>
              <div className="p-2 bg-card border border-border rounded">
                <div className="text-[10px] text-muted-foreground">Cuarentena</div>
                <div className="font-semibold text-destructive">{preview.quarantined_count}</div>
              </div>
            </div>

            {!preview.dry_run && preview.import_batch_id && (
              <div className="flex items-center justify-between pt-2 border-t border-border">
                <span className="text-[11px] text-muted-foreground">
                  ¿Mapeo incorrecto? Puedes revertir todo este lote en 1 clic.
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  isLoading={isRollingBack}
                  onClick={() => void handleRollbackBatch()}
                  className="gap-1.5 text-destructive border-destructive/30 hover:bg-destructive/10"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  <span>Deshacer esta importación</span>
                </Button>
              </div>
            )}

            {rollbackNotice && (
              <div
                role="status"
                className="p-2.5 rounded bg-card border border-border text-xs text-foreground"
              >
                {rollbackNotice}
              </div>
            )}

            {preview.errors.length > 0 && (
              <div className="flex flex-col gap-1">
                <span className="font-medium text-destructive">
                  Filas en cuarentena (no importadas):
                </span>
                <ul className="max-h-28 overflow-y-auto flex flex-col gap-1 font-mono text-[11px] text-muted-foreground">
                  {preview.errors.map((err) => (
                    <li key={`${err.row}-${err.reason}`}>
                      Línea {err.row}: {err.reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
          <Button type="button" variant="ghost" size="sm" onClick={onClose}>
            Cerrar
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!csvContent.trim()}
            isLoading={isRunning}
            onClick={() => void handleRunImport(true)}
          >
            Validar (Dry-Run)
          </Button>
          <Button
            type="button"
            variant="primary"
            size="sm"
            disabled={!csvContent.trim() || !preview?.dry_run}
            isLoading={isRunning}
            onClick={() => void handleRunImport(false)}
          >
            Confirmar Importación
          </Button>
        </div>
      </div>
    </div>
  );
}
