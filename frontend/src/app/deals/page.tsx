"use client";

import React, { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertCircle,
  Kanban,
  Layers,
  Plus,
  RefreshCw,
  Table2,
  X,
} from "lucide-react";
import { Account, Contact, Deal, PipelineStage } from "../../types/crm";
import {
  ApiError,
  bootstrapPipeline,
  createDeal,
  fetchAccounts,
  fetchContacts,
  fetchDeals,
  fetchPipelineStages,
} from "../../lib/api-client";
import { useAuth } from "../../lib/auth-context";
import { DealKanbanBoard } from "../../components/features/deals/deal-kanban-board";
import { DealDataGrid } from "../../components/features/deals/deal-data-grid";
import { DealPeekDrawer } from "../../components/features/deals/deal-peek-drawer";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";

function DealsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { accessToken, user } = useAuth();

  const [viewMode, setViewMode] = useState<"kanban" | "table">("kanban");
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Create Deal Modal (Progressive disclosure: Title + Amount + Currency + Stage)
  const [isCreateOpen, setIsCreateOpen] = useState<boolean>(false);
  const [newTitle, setNewTitle] = useState("");
  const [newAmount, setNewAmount] = useState("25000");
  const [newCurrency, setNewCurrency] = useState("USD");
  const [newStageId, setNewStageId] = useState("");
  const [newContactId, setNewContactId] = useState("");
  const [newAccountId, setNewAccountId] = useState("");
  const [newCloseDate, setNewCloseDate] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  // Selected Deal for Slide-over Peek Drawer
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);

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
      const [fetchedStages, fetchedDeals, fetchedContacts, fetchedAccounts] = await Promise.all([
        fetchPipelineStages(accessToken ?? undefined),
        fetchDeals(accessToken ?? undefined),
        fetchContacts(accessToken ?? undefined),
        fetchAccounts(accessToken ?? undefined).catch(() => []),
      ]);
      setStages(fetchedStages);
      setDeals(fetchedDeals);
      setContacts(fetchedContacts);
      setAccounts(fetchedAccounts);
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
        const [fetchedStages, fetchedDeals, fetchedContacts, fetchedAccounts] = await Promise.all([
          fetchPipelineStages(accessToken ?? undefined),
          fetchDeals(accessToken ?? undefined),
          fetchContacts(accessToken ?? undefined),
          fetchAccounts(accessToken ?? undefined).catch(() => []),
        ]);
        if (!active) return;
        setStages(fetchedStages);
        setDeals(fetchedDeals);
        setContacts(fetchedContacts);
        setAccounts(fetchedAccounts);
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
          currency: newCurrency,
          contact_id: newContactId || undefined,
          account_id: newAccountId || undefined,
          expected_close_date: newCloseDate || undefined,
        },
        accessToken ?? undefined
      );
      setNewTitle("");
      setNewCloseDate("");
      setNewCurrency("USD");
      closeCreateModal();
      await loadPipelineData();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Error al crear la oportunidad.");
    } finally {
      setIsCreating(false);
    }
  };

  const handleNavigateDealInDrawer = (direction: "prev" | "next") => {
    if (!selectedDeal || deals.length <= 1) return;
    const idx = deals.findIndex((d) => d.id === selectedDeal.id);
    if (idx === -1) return;
    const nextIdx =
      direction === "next"
        ? (idx + 1) % deals.length
        : (idx - 1 + deals.length) % deals.length;
    setSelectedDeal(deals[nextIdx]);
  };

  const activeDeals = deals.filter((d) => !d.is_lost);
  const totalPipelineValue = activeDeals.reduce(
    (acc, d) => acc + Number(d.normalized_amount_usd ?? d.amount),
    0
  );
  const weightedPipelineValue = activeDeals.reduce(
    (acc, d) => acc + Number(d.normalized_amount_usd ?? d.amount) * Number(d.win_probability),
    0
  );
  const commitPipelineValue = activeDeals
    .filter((d) => d.forecast_category === "commit" || d.is_won)
    .reduce((acc, d) => acc + Number(d.normalized_amount_usd ?? d.amount), 0);

  return (
    <div className="flex flex-col h-full p-6 gap-5">
      <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4 pb-4 border-b border-border">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-foreground">Pipeline de Ventas</h1>
            <Badge variant="secondary" className="font-mono text-xs tabular-nums">
              {deals.length} oportunidades
            </Badge>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground tabular-nums">
            <span>
              Bruto Activo:{" "}
              <strong className="font-mono text-foreground">
                ${totalPipelineValue.toLocaleString("en-US", { minimumFractionDigits: 0 })} USD
              </strong>
            </span>
            <span>·</span>
            <span>
              Ponderado:{" "}
              <strong className="font-mono text-primary">
                ${Math.round(weightedPipelineValue).toLocaleString("en-US")} USD
              </strong>
            </span>
            <span>·</span>
            <span>
              En Commit / Ganado:{" "}
              <strong className="font-mono text-foreground">
                ${commitPipelineValue.toLocaleString("en-US", { minimumFractionDigits: 0 })} USD
              </strong>
            </span>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Kanban vs High-Density Data Grid Switcher */}
          <div
            className="inline-flex items-center p-0.5 bg-muted border border-border rounded-lg"
            role="group"
            aria-label="Cambiar vista del pipeline"
          >
            <button
              type="button"
              onClick={() => setViewMode("kanban")}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors ${
                viewMode === "kanban"
                  ? "bg-card text-foreground shadow-subtle"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Kanban className="h-3.5 w-3.5" />
              <span>Kanban</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode("table")}
              className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors ${
                viewMode === "table"
                  ? "bg-card text-foreground shadow-subtle"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <Table2 className="h-3.5 w-3.5" />
              <span>Tabla Densa</span>
            </button>
          </div>

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
        <div className="flex flex-col items-center justify-center p-12 border border-dashed border-border rounded-lg bg-card text-center gap-3">
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
      ) : viewMode === "kanban" ? (
        <div className="flex-1 min-h-0">
          <DealKanbanBoard
            stages={stages}
            initialDeals={deals}
            authToken={accessToken ?? undefined}
            isLoading={isLoading}
            onDealClick={(deal) => setSelectedDeal(deal)}
            onCreateDeal={user?.role === "readonly" ? undefined : handleOpenCreateModal}
            onDealMoved={(updated) => {
              setDeals((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
              if (selectedDeal?.id === updated.id) setSelectedDeal(updated);
            }}
          />
        </div>
      ) : (
        <div className="flex-1 min-h-0">
          <DealDataGrid
            stages={stages}
            deals={deals}
            authToken={accessToken ?? undefined}
            isReadonly={user?.role === "readonly"}
            onDealClick={(deal) => setSelectedDeal(deal)}
            onDealUpdated={(updated) => {
              setDeals((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
              if (selectedDeal?.id === updated.id) setSelectedDeal(updated);
            }}
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
            className="w-full max-w-md p-6 bg-card border border-border rounded-lg shadow-elevated flex flex-col gap-4"
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

            <div className="grid grid-cols-3 gap-2">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="deal-amount" className="text-xs font-medium">
                  Monto
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
                <label htmlFor="deal-currency" className="text-xs font-medium">
                  Divisa
                </label>
                <select
                  id="deal-currency"
                  value={newCurrency}
                  onChange={(e) => setNewCurrency(e.target.value)}
                  className="h-10 px-2 bg-background border border-border rounded-md text-xs font-mono focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="USD">USD ($)</option>
                  <option value="EUR">EUR (€)</option>
                  <option value="MXN">MXN ($)</option>
                  <option value="COP">COP ($)</option>
                  <option value="GBP">GBP (£)</option>
                  <option value="BRL">BRL (R$)</option>
                </select>
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

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="deal-account" className="text-xs font-medium">
                  Empresa (opcional)
                </label>
                <select
                  id="deal-account"
                  value={newAccountId}
                  onChange={(e) => setNewAccountId(e.target.value)}
                  className="h-10 px-2 bg-background border border-border rounded-md text-xs focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="">Auto-detectar por contacto</option>
                  {accounts.map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="deal-close-date" className="text-xs font-medium">
                  Fecha Estimada Cierre
                </label>
                <input
                  id="deal-close-date"
                  type="date"
                  value={newCloseDate}
                  onChange={(e) => setNewCloseDate(e.target.value)}
                  className="h-10 px-2.5 bg-background border border-border rounded-md text-xs font-mono focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="deal-contact" className="text-xs font-medium">
                Contacto Champion (opcional)
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

      {/* Slide-over Peek Drawer (Replaces centered read-only modal) */}
      <DealPeekDrawer
        deal={selectedDeal}
        stages={stages}
        contacts={contacts}
        authToken={accessToken ?? undefined}
        onClose={() => setSelectedDeal(null)}
        onNavigateDeal={deals.length > 1 ? handleNavigateDealInDrawer : undefined}
      />
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
