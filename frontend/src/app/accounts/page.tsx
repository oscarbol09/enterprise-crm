"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Building2,
  Calendar,
  Globe,
  Plus,
  RefreshCw,
  Search,
  UserPlus,
  X,
} from "lucide-react";
import { Account, CompanyAffiliation, Contact, InteractionItem } from "../../types/crm";
import {
  ApiError,
  createAccount,
  createAccountAffiliation,
  fetchAccountAffiliations,
  fetchAccountTimeline,
  fetchAccounts,
  fetchContacts,
} from "../../lib/api-client";
import { useAuth } from "../../lib/auth-context";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";

export default function AccountsPage() {
  const { accessToken, user } = useAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Create Account Modal
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [newIndustry, setNewIndustry] = useState("");
  const [newWebsite, setNewWebsite] = useState("");
  const [newRevenue, setNewRevenue] = useState("");
  const [newEmployees, setNewEmployees] = useState("");
  const [isCreating, setIsCreating] = useState(false);

  // Account Peek Drawer (Hierarchical Roll-up Timeline & Affiliations)
  const [selectedAccount, setSelectedAccount] = useState<Account | null>(null);
  const [rollupTimeline, setRollupTimeline] = useState<InteractionItem[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [affiliations, setAffiliations] = useState<CompanyAffiliation[]>([]);
  const [affContactId, setAffContactId] = useState("");
  const [affRoleTitle, setAffRoleTitle] = useState("");

  const loadAccounts = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [accList, contactList] = await Promise.all([
        fetchAccounts(accessToken ?? undefined),
        fetchContacts(accessToken ?? undefined).catch(() => []),
      ]);
      setAccounts(accList);
      setContacts(contactList);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Error al cargar directorio de empresas.");
    } finally {
      setIsLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    let active = true;
    async function initAccounts() {
      try {
        const [accList, contactList] = await Promise.all([
          fetchAccounts(accessToken ?? undefined),
          fetchContacts(accessToken ?? undefined).catch(() => []),
        ]);
        if (active) {
          setAccounts(accList);
          setContacts(contactList);
        }
      } catch (err: unknown) {
        if (active) {
          setError(err instanceof ApiError ? err.message : "Error al cargar directorio de empresas.");
        }
      } finally {
        if (active) setIsLoading(false);
      }
    }
    void initAccounts();
    return () => {
      active = false;
    };
  }, [accessToken]);

  const handleCreateAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setIsCreating(true);
    setError(null);
    try {
      await createAccount(
        {
          name: newName.trim(),
          industry: newIndustry.trim() || undefined,
          website: newWebsite.trim() || undefined,
          annual_revenue: newRevenue ? Number(newRevenue) : undefined,
          employee_count: newEmployees ? Number(newEmployees) : undefined,
        },
        accessToken ?? undefined
      );
      setNewName("");
      setNewIndustry("");
      setNewWebsite("");
      setNewRevenue("");
      setNewEmployees("");
      setIsCreateOpen(false);
      await loadAccounts();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo crear la empresa.");
    } finally {
      setIsCreating(false);
    }
  };

  const openAccountDrawer = async (account: Account) => {
    setSelectedAccount(account);
    try {
      const [tl, affs] = await Promise.all([
        fetchAccountTimeline(account.id, undefined, accessToken ?? undefined),
        fetchAccountAffiliations(account.id, accessToken ?? undefined),
      ]);
      setRollupTimeline(tl.items);
      setNextCursor(tl.next_cursor ?? null);
      setAffiliations(affs);
    } catch {
      setRollupTimeline([]);
      setNextCursor(null);
      setAffiliations([]);
    }
  };

  const handleLoadMoreRollup = async () => {
    if (!selectedAccount || !nextCursor) return;
    try {
      const more = await fetchAccountTimeline(
        selectedAccount.id,
        nextCursor,
        accessToken ?? undefined
      );
      setRollupTimeline((prev) => [...prev, ...more.items]);
      setNextCursor(more.next_cursor ?? null);
    } catch {
      setNextCursor(null);
    }
  };

  const handleAddAffiliation = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAccount || !affContactId) return;
    try {
      const created = await createAccountAffiliation(
        selectedAccount.id,
        {
          contact_id: affContactId,
          role_title: affRoleTitle.trim() || undefined,
        },
        accessToken ?? undefined
      );
      setAffiliations((prev) => [...prev, created]);
      setAffContactId("");
      setAffRoleTitle("");
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo afiliar el contacto.");
    }
  };

  const filtered = accounts.filter((a) => {
    const q = searchQuery.toLowerCase();
    return (
      a.name.toLowerCase().includes(q) ||
      (a.industry && a.industry.toLowerCase().includes(q)) ||
      (a.website && a.website.toLowerCase().includes(q))
    );
  });

  return (
    <div className="flex flex-col h-full p-6 gap-5">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-border">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight text-foreground">Empresas</h1>
            <Badge variant="secondary" className="font-mono text-xs tabular-nums">
              {accounts.length} cuentas
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Selecciona una empresa para ver la actividad consolidada de sus contactos, oportunidades
            y equipo afiliado.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadAccounts} isLoading={isLoading} className="gap-1.5">
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Actualizar</span>
          </Button>
          {user?.role !== "readonly" && (
            <Button variant="primary" size="sm" onClick={() => setIsCreateOpen(true)} className="gap-1.5">
              <Plus className="h-4 w-4" />
              <span>Nueva Empresa</span>
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div role="alert" className="p-3 text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-md flex items-center gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
        <input
          type="text"
          aria-label="Buscar empresas"
          placeholder="Buscar por razón social, industria o dominio web..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full h-9 pl-9 pr-3 bg-card border border-border rounded-md text-xs"
        />
      </div>

      <div className="flex-1 bg-card border border-border rounded-lg shadow-card overflow-hidden">
        {isLoading ? (
          <div className="p-12 text-center text-xs text-muted-foreground">
            Cargando directorio de empresas...
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center flex flex-col items-center gap-2">
            <Building2 className="h-8 w-8 text-muted-foreground/60" />
            <h3 className="text-sm font-medium text-foreground">Sin empresas registradas</h3>
            <p className="text-xs text-muted-foreground">
              Registra una organización para agrupar múltiples contactos y oportunidades.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs tabular-nums" aria-label="Tabla de empresas">
              <thead className="bg-muted/50 border-b border-border text-muted-foreground font-medium uppercase tracking-wider text-[11px]">
                <tr>
                  <th scope="col" className="py-2.5 px-4">Empresa</th>
                  <th scope="col" className="py-2.5 px-4">Industria</th>
                  <th scope="col" className="py-2.5 px-4">Sitio Web</th>
                  <th scope="col" className="py-2.5 px-4 text-right">Facturación Anual</th>
                  <th scope="col" className="py-2.5 px-4 text-right">Empleados</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filtered.map((acc) => (
                  <tr
                    key={acc.id}
                    onClick={() => void openAccountDrawer(acc)}
                    className="hover:bg-muted/25 transition-colors cursor-pointer"
                  >
                    <td className="py-2.5 px-4 font-semibold text-foreground">{acc.name}</td>
                    <td className="py-2.5 px-4 text-muted-foreground">{acc.industry || "—"}</td>
                    <td className="py-2.5 px-4 text-muted-foreground">
                      {acc.website ? (
                        <span className="inline-flex items-center gap-1 font-mono text-[11px]">
                          <Globe className="h-3 w-3" />
                          <span>{acc.website}</span>
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-foreground">
                      {acc.annual_revenue
                        ? `$${Number(acc.annual_revenue).toLocaleString("en-US")}`
                        : "—"}
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono text-muted-foreground">
                      {acc.employee_count ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create Account Modal */}
      {isCreateOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Registrar empresa"
          onClick={() => setIsCreateOpen(false)}
        >
          <form
            onSubmit={handleCreateAccount}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md p-6 bg-card border border-border rounded-xl shadow-elevated flex flex-col gap-4"
          >
            <div className="flex items-center justify-between pb-2 border-b border-border">
              <h2 className="text-base font-semibold text-foreground">Nueva Empresa</h2>
              <button type="button" onClick={() => setIsCreateOpen(false)} className="p-1 text-muted-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="acc-name" className="text-xs font-medium">Nombre Comercial *</label>
              <input
                id="acc-name"
                required
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Ej. Nordic Cloud Systems"
                className="h-9 px-3 bg-background border border-border rounded text-xs"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <label htmlFor="acc-ind" className="text-xs font-medium">Industria</label>
                <input
                  id="acc-ind"
                  value={newIndustry}
                  onChange={(e) => setNewIndustry(e.target.value)}
                  placeholder="Cloud / FinTech"
                  className="h-9 px-3 bg-background border border-border rounded text-xs"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="acc-web" className="text-xs font-medium">Dominio / Web</label>
                <input
                  id="acc-web"
                  value={newWebsite}
                  onChange={(e) => setNewWebsite(e.target.value)}
                  placeholder="https://empresa.com"
                  className="h-9 px-3 bg-background border border-border rounded text-xs font-mono"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <label htmlFor="acc-rev" className="text-xs font-medium">Facturación Anual (USD)</label>
                <input
                  id="acc-rev"
                  type="number"
                  min={0}
                  value={newRevenue}
                  onChange={(e) => setNewRevenue(e.target.value)}
                  className="h-9 px-3 bg-background border border-border rounded text-xs font-mono"
                />
              </div>
              <div className="flex flex-col gap-1">
                <label htmlFor="acc-emp" className="text-xs font-medium">Nº Empleados</label>
                <input
                  id="acc-emp"
                  type="number"
                  min={1}
                  value={newEmployees}
                  onChange={(e) => setNewEmployees(e.target.value)}
                  className="h-9 px-3 bg-background border border-border rounded text-xs font-mono"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2 border-t border-border">
              <Button type="button" variant="ghost" size="sm" onClick={() => setIsCreateOpen(false)}>
                Cancelar
              </Button>
              <Button type="submit" variant="primary" size="sm" isLoading={isCreating}>
                Guardar Empresa
              </Button>
            </div>
          </form>
        </div>
      )}

      {/* Account Roll-Up Peek Drawer */}
      {selectedAccount && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-background/50 backdrop-blur-[1px]"
          role="dialog"
          aria-modal="true"
          aria-label={`Timeline Roll-Up de ${selectedAccount.name}`}
          onClick={() => setSelectedAccount(null)}
        >
          <aside
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-lg h-full bg-card border-l border-border shadow-elevated flex flex-col overflow-hidden"
          >
            <header className="px-5 py-4 border-b border-border flex items-start justify-between bg-muted/20">
              <div>
                <h2 className="text-base font-bold text-foreground">{selectedAccount.name}</h2>
                <p className="text-xs text-muted-foreground font-mono">
                  {selectedAccount.industry || "B2B"} · {selectedAccount.website || "Sin dominio"}
                </p>
              </div>
              <button type="button" onClick={() => setSelectedAccount(null)} className="p-1 text-muted-foreground">
                <X className="h-4 w-4" />
              </button>
            </header>

            <div className="p-4 border-b border-border">
              <form onSubmit={handleAddAffiliation} className="flex items-center gap-2">
                <select
                  aria-label="Afiliar contacto a esta empresa"
                  value={affContactId}
                  onChange={(e) => setAffContactId(e.target.value)}
                  className="flex-1 h-8 px-2 bg-background border border-border rounded text-xs"
                >
                  <option value="">Afiliar contacto existente...</option>
                  {contacts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.first_name} {c.last_name} ({c.email})
                    </option>
                  ))}
                </select>
                <input
                  type="text"
                  value={affRoleTitle}
                  onChange={(e) => setAffRoleTitle(e.target.value)}
                  placeholder="Rol (ej. Advisor)"
                  className="w-32 h-8 px-2 bg-background border border-border rounded text-xs"
                />
                <Button type="submit" variant="outline" size="sm" disabled={!affContactId} className="h-8 text-xs gap-1">
                  <UserPlus className="h-3.5 w-3.5" />
                  <span>Afiliar</span>
                </Button>
              </form>
            </div>

            <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-4">
              {affiliations.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Personas Afiliadas ({affiliations.length})
                  </h3>
                  <div className="flex flex-wrap gap-1.5">
                    {affiliations.map((aff) => {
                      const c = contacts.find((x) => x.id === aff.contact_id);
                      return (
                        <Badge key={aff.id} variant={aff.is_primary ? "default" : "secondary"} className="text-[11px]">
                          {c ? `${c.first_name} ${c.last_name}` : aff.contact_id}
                          {aff.role_title ? ` (${aff.role_title})` : ""}
                        </Badge>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-2">
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Roll-Up Timeline Consolidado ({rollupTimeline.length})
                </h3>
                {rollupTimeline.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    No hay interacciones registradas en esta cuenta, sus contactos o sus oportunidades.
                  </p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {rollupTimeline.map((item) => (
                      <li key={item.id} className="p-3 rounded-lg bg-muted/30 border border-border text-xs flex flex-col gap-1">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-foreground">{item.subject}</span>
                          <span className="text-[10px] text-muted-foreground flex items-center gap-1 tabular-nums">
                            <Calendar className="h-3 w-3" />
                            {new Date(item.occurred_at).toLocaleDateString()}
                          </span>
                        </div>
                        <p className="text-muted-foreground">{item.content_body}</p>
                      </li>
                    ))}
                  </ul>
                )}
                {nextCursor && (
                  <Button type="button" variant="outline" size="sm" onClick={handleLoadMoreRollup} className="text-xs self-center mt-2">
                    Cargar más del cursor
                  </Button>
                )}
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
