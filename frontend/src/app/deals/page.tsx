"use client";

import React, { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertCircle,
  Calendar,
  Layers,
  Plus,
  RefreshCw,
  Sparkles,
  X,
} from "lucide-react";
import { Contact, Deal, InteractionItem, PipelineStage } from "../../types/crm";
import {
  ApiError,
  bootstrapPipeline,
  createDeal,
  fetchContacts,
  fetchDealInteractions,
  fetchDeals,
  fetchPipelineStages,
} from "../../lib/api-client";
import { useAuth } from "../../lib/auth-context";
import { DealKanbanBoard } from "../../components/features/deals/deal-kanban-board";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";

function DealsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { accessToken, user } = useAuth();

  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Create Deal Modal
  const [isCreateOpen, setIsCreateOpen] = useState<boolean>(false);
  const [newTitle, setNewTitle] = useState("");
  const [newAmount, setNewAmount] = useState("25000");
  const [newStageId, setNewStageId] = useState("");
  const [newContactId, setNewContactId] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  // Deal Detail Drawer/Modal
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);
  const [dealInteractions, setDealInteractions] = useState<InteractionItem[]>([]);
  const [isLoadingInteractions, setIsLoadingInteractions] = useState(false);

  const wantsNewFromQuery = searchParams.get("new") === "1";
  const showCreateModal = isCreateOpen || wantsNewFromQuery;

  const closeCreateModal = () => {
    setIsCreateOpen(false);
    if (wantsNewFromQuery) {
      router.replace("/deals");
    }
  };

  const loadPipelineData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [fetchedStages, fetchedDeals, fetchedContacts] = await Promise.all([
        fetchPipelineStages(accessToken ?? undefined),
        fetchDeals(accessToken ?? undefined),
        fetchContacts(accessToken ?? undefined),
      ]);
      setStages(fetchedStages);
      setDeals(fetchedDeals);
      setContacts(fetchedContacts);
      if (fetchedStages.length > 0 && !newStageId) {
        setNewStageId(fetchedStages[0].id);
      }
    } catch (err: unknown) {
      const msg =
        err instanceof ApiError ? err.message : "Error al conectar con la API de deals.";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, newStageId]);

  useEffect(() => {
    let active = true;
    async function initPipeline() {
      try {
        const [fetchedStages, fetchedDeals, fetchedContacts] = await Promise.all([
          fetchPipelineStages(accessToken ?? undefined),
          fetchDeals(accessToken ?? undefined),
          fetchContacts(accessToken ?? undefined),
        ]);
        if (!active) return;
        setStages(fetchedStages);
        setDeals(fetchedDeals);
        setContacts(fetchedContacts);
        if (fetchedStages.length > 0) {
          setNewStageId((prev) => prev || fetchedStages[0].id);
        }
      } catch (err: unknown) {
        if (active) {
          const msg =
            err instanceof ApiError ? err.message : "Error al conectar con la API de deals.";
          setError(msg);
        }
      } finally {
        if (active) setIsLoading(false);
      }
    }
    void initPipeline();
    return () => {
      active = false;
    };
  }, [accessToken]);

  const handleBootstrapPipeline = async () => {
    setError(null);
    try {
      const created = await bootstrapPipeline(accessToken ?? undefined);
      setStages(created);
      if (created.length > 0) setNewStageId(created[0].id);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo inicializar el pipeline.");
    }
  };

  const handleOpenCreateModal = (stageId?: string) => {
    if (stageId) {
      setNewStageId(stageId);
    } else if (stages.length > 0 && !newStageId) {
      setNewStageId(stages[0].id);
    }
    setIsCreateOpen(true);
  };

  const handleCreateDealSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim() || !newStageId) return;
    setIsCreating(true);
    setError(null);
    try {
      await createDeal(
        {
          title: newTitle.trim(),
          stage_id: newStageId,
          amount: Number(newAmount) || 0,
          currency: "USD",
          contact_id: newContactId || undefined,
        },
        accessToken ?? undefined
      );
      setNewTitle("");
      closeCreateModal();
      await loadPipelineData();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Error al crear la oportunidad.");
    } finally {
      setIsCreating(false);
    }
  };

  const handleOpenDealDetail = async (deal: Deal) => {
    setSelectedDeal(deal);
    setIsLoadingInteractions(true);
    try {
      const timeline = await fetchDealInteractions(deal.id, accessToken ?? undefined);
      setDealInteractions(timeline);
    } catch {
      setDealInteractions([]);
    } finally {
      setIsLoadingInteractions(false);
    }
  };

  const totalPipelineValue = deals.reduce(
    (acc, d) => acc + (d.is_lost ? 0 : Number(d.amount)),
    0
  );

  return (
    <div className="flex flex-col h-full p-6 gap-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-border">
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-foreground">Pipeline de Ventas</h1>
            <Badge variant="secondary" className="font-mono text-xs">
              {deals.length} oportunidades
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Valor activo total:{" "}
            <span className="font-semibold font-mono text-foreground">
              ${totalPipelineValue.toLocaleString("en-US", { minimumFractionDigits: 0 })} USD
            </span>
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={loadPipelineData}
            isLoading={isLoading}
            className="gap-1.5"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Actualizar</span>
          </Button>
          {stages.length > 0 && user?.role !== "readonly" && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => handleOpenCreateModal()}
              className="gap-1.5"
            >
              <Plus className="h-4 w-4" />
              <span>Nueva Oportunidad</span>
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-center justify-between p-3.5 text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-md"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={loadPipelineData}
            className="text-destructive hover:bg-destructive/10 h-7 text-xs"
          >
            Reintentar
          </Button>
        </div>
      )}

      {!isLoading && stages.length === 0 ? (
        <div className="flex flex-col items-center justify-center p-12 border border-dashed border-border rounded-xl bg-card text-center gap-3">
          <Layers className="h-8 w-8 text-muted-foreground/60" />
          <h2 className="text-sm font-semibold text-foreground">
            Este workspace aún no tiene etapas de pipeline configuradas
          </h2>
          <p className="text-xs text-muted-foreground max-w-md">
            Provisiona el pipeline comercial estándar de 6 etapas (Prospección a Cierre Ganado/Perdido).
          </p>
          {(user?.role === "admin" || user?.role === "sales_manager") && (
            <Button variant="primary" size="sm" onClick={handleBootstrapPipeline}>
              Crear Pipeline Comercial
            </Button>
          )}
        </div>
      ) : (
        <div className="flex-1 min-h-0">
          <DealKanbanBoard
            stages={stages}
            initialDeals={deals}
            authToken={accessToken ?? undefined}
            isLoading={isLoading}
            onDealClick={handleOpenDealDetail}
            onCreateDeal={user?.role === "readonly" ? undefined : handleOpenCreateModal}
            onDealMoved={(updated) =>
              setDeals((prev) => prev.map((d) => (d.id === updated.id ? updated : d)))
            }
          />
        </div>
      )}

      {/* Create Deal Modal */}
      {showCreateModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Crear nueva oportunidad"
          onClick={closeCreateModal}
        >
          <form
            onSubmit={handleCreateDealSubmit}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md p-6 bg-card border border-border rounded-xl shadow-elevated flex flex-col gap-4"
          >
            <div className="flex items-center justify-between pb-2 border-b border-border">
              <h2 className="text-base font-semibold text-foreground">Nueva Oportunidad</h2>
              <button
                type="button"
                onClick={closeCreateModal}
                aria-label="Cerrar modal"
                className="p-1 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="deal-title" className="text-xs font-medium">
                Título <span className="text-destructive">*</span>
              </label>
              <input
                id="deal-title"
                required
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="Ej. Licencia Anual Enterprise (500 asientos)"
                className="h-10 px-3 bg-background border border-border rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="deal-amount" className="text-xs font-medium">
                  Monto (USD)
                </label>
                <input
                  id="deal-amount"
                  type="number"
                  min={0}
                  step="100"
                  value={newAmount}
                  onChange={(e) => setNewAmount(e.target.value)}
                  className="h-10 px-3 bg-background border border-border rounded-md text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="deal-stage" className="text-xs font-medium">
                  Etapa Inicial
                </label>
                <select
                  id="deal-stage"
                  value={newStageId}
                  onChange={(e) => setNewStageId(e.target.value)}
                  className="h-10 px-2 bg-background border border-border rounded-md text-xs focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  {stages.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="deal-contact" className="text-xs font-medium">
                Contacto Asociado (opcional)
              </label>
              <select
                id="deal-contact"
                value={newContactId}
                onChange={(e) => setNewContactId(e.target.value)}
                className="h-10 px-2 bg-background border border-border rounded-md text-xs focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="">Sin contacto vinculado</option>
                {contacts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.first_name} {c.last_name} ({c.email})
                  </option>
                ))}
              </select>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-border">
              <Button type="button" variant="ghost" size="sm" onClick={closeCreateModal}>
                Cancelar
              </Button>
              <Button type="submit" variant="primary" size="sm" isLoading={isCreating}>
                Crear Oportunidad
              </Button>
            </div>
          </form>
        </div>
      )}

      {/* Deal Detail & Timeline Modal */}
      {selectedDeal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label={`Detalle de ${selectedDeal.title}`}
          onClick={() => setSelectedDeal(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-lg p-6 bg-card border border-border rounded-xl shadow-elevated flex flex-col gap-4 max-h-[85vh] overflow-y-auto"
          >
            <div className="flex items-start justify-between gap-2 pb-3 border-b border-border">
              <div>
                <h2 className="text-base font-bold text-foreground">{selectedDeal.title}</h2>
                <p className="text-xs text-muted-foreground font-mono mt-0.5">
                  ${Number(selectedDeal.amount).toLocaleString("en-US")} {selectedDeal.currency} ·
                  Probabilidad {Math.round(Number(selectedDeal.win_probability) * 100)}% ·
                  Forecast: {selectedDeal.forecast_category}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedDeal(null)}
                aria-label="Cerrar detalle"
                className="p-1 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {selectedDeal.loss_reason && (
              <div className="p-3 rounded-md bg-destructive/10 border border-destructive/20 text-xs text-destructive">
                <strong>Motivo de pérdida:</strong> {selectedDeal.loss_reason}
              </div>
            )}

            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Historial de Actividad
              </h3>
              {selectedDeal.contact_id && (
                <Link
                  href={`/ai?contactId=${selectedDeal.contact_id}&dealId=${selectedDeal.id}`}
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  <span>Analizar con Copilot IA</span>
                </Link>
              )}
            </div>

            {isLoadingInteractions ? (
              <p className="text-xs text-muted-foreground animate-pulse">Cargando timeline...</p>
            ) : dealInteractions.length === 0 ? (
              <p className="text-xs text-muted-foreground italic">
                Aún no hay interacciones registradas para esta oportunidad.
              </p>
            ) : (
              <ul className="flex flex-col gap-2">
                {dealInteractions.map((item) => (
                  <li
                    key={item.id}
                    className="p-3 rounded-lg bg-muted/40 border border-border text-xs flex flex-col gap-1"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-foreground">{item.subject}</span>
                      <span className="text-[10px] text-muted-foreground flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {new Date(item.occurred_at).toLocaleDateString()}
                      </span>
                    </div>
                    <p className="text-muted-foreground">{item.content_body}</p>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function DealsPage() {
  return (
    <Suspense
      fallback={
        <div className="p-6 text-xs text-muted-foreground">Cargando pipeline comercial...</div>
      }
    >
      <DealsPageContent />
    </Suspense>
  );
}
