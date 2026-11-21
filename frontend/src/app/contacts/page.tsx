"use client";

import React, { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertCircle,
  Briefcase,
  Building2,
  Calendar,
  Check,
  Edit3,
  GitMerge,
  Mail,
  Phone,
  Plus,
  RefreshCw,
  Search,
  Send,
  Trash2,
  Upload,
  Users,
  X,
} from "lucide-react";
import { Account, CompanyAffiliation, Contact, InteractionItem } from "../../types/crm";
import {
  ApiError,
  createContact,
  createInteraction,
  deleteContact,
  fetchAccounts,
  fetchContactAffiliations,
  fetchContactTimeline,
  fetchContacts,
  mergeContacts,
  restoreContact,
  updateContact,
} from "../../lib/api-client";
import { useAuth } from "../../lib/auth-context";
import { ContactForm, ContactFormData } from "../../components/features/contacts/contact-form";
import { CsvImportModal } from "../../components/features/contacts/csv-import-modal";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";

function ContactsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { accessToken, user } = useAuth();

  const [contacts, setContacts] = useState<Contact[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>(() => searchParams.get("q") || "");
  const [stageFilter, setStageFilter] = useState<string>("all");
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [isImportModalOpen, setIsImportModalOpen] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Inline Editing & Soft-Delete Undo state
  const [editingJobId, setEditingJobId] = useState<string | null>(null);
  const [jobTitleDraft, setJobTitleDraft] = useState<string>("");
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [lastDeletedContact, setLastDeletedContact] = useState<{ id: string; name: string } | null>(
    null
  );
  const [isRestoring, setIsRestoring] = useState<boolean>(false);

  // Contact Peek Drawer state
  const [selectedContact, setSelectedContact] = useState<Contact | null>(null);
  const [contactTimeline, setContactTimeline] = useState<InteractionItem[]>([]);
  const [timelineCursor, setTimelineCursor] = useState<string | null>(null);
  const [contactAffiliations, setContactAffiliations] = useState<CompanyAffiliation[]>([]);
  const [quickNoteText, setQuickNoteText] = useState("");
  const [mergeSourceId, setMergeSourceId] = useState("");
  const [isMerging, setIsMerging] = useState(false);

  const wantsNewFromQuery = searchParams.get("new") === "1";
  const showCreateModal = isCreateModalOpen || wantsNewFromQuery;

  const closeCreateModal = () => {
    setIsCreateModalOpen(false);
    if (wantsNewFromQuery) {
      router.replace("/contacts");
    }
  };

  const loadContacts = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [contactList, accountList] = await Promise.all([
        fetchContacts(accessToken ?? undefined, {
          q: searchQuery,
          lifecycle_stage: stageFilter,
        }),
        fetchAccounts(accessToken ?? undefined).catch(() => []),
      ]);
      setContacts(contactList);
      setAccounts(accountList);
    } catch (err: unknown) {
      const msg =
        err instanceof ApiError ? err.message : "Error al conectar con la API de contactos.";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [accessToken, searchQuery, stageFilter]);

  useEffect(() => {
    let active = true;
    const delayMs = searchQuery.trim().length > 0 ? 250 : 0;

    const timer = setTimeout(() => {
      void (async () => {
        try {
          const [contactList, accountList] = await Promise.all([
            fetchContacts(accessToken ?? undefined, {
              q: searchQuery,
              lifecycle_stage: stageFilter,
            }),
            fetchAccounts(accessToken ?? undefined).catch(() => []),
          ]);
          if (active) {
            setContacts(contactList);
            setAccounts(accountList);
          }
        } catch (err: unknown) {
          if (active) {
            const msg =
              err instanceof ApiError ? err.message : "Error al conectar con la API de contactos.";
            setError(msg);
          }
        } finally {
          if (active) setIsLoading(false);
        }
      })();
    }, delayMs);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [accessToken, searchQuery, stageFilter]);

  const openContactDrawer = async (contact: Contact) => {
    setSelectedContact(contact);
    setMergeSourceId("");
    try {
      const [tl, affs] = await Promise.all([
        fetchContactTimeline(contact.id, undefined, accessToken ?? undefined).catch(() => ({
          items: [],
          next_cursor: null,
        })),
        fetchContactAffiliations(contact.id, accessToken ?? undefined).catch(() => []),
      ]);
      setContactTimeline(tl.items);
      setTimelineCursor(tl.next_cursor ?? null);
      setContactAffiliations(affs);
    } catch {
      setContactTimeline([]);
      setContactAffiliations([]);
    }
  };

  const handleLoadMoreTimeline = async () => {
    if (!selectedContact || !timelineCursor) return;
    try {
      const next = await fetchContactTimeline(
        selectedContact.id,
        timelineCursor,
        accessToken ?? undefined
      );
      setContactTimeline((prev) => [...prev, ...next.items]);
      setTimelineCursor(next.next_cursor ?? null);
    } catch {
      setTimelineCursor(null);
    }
  };

  const handleQuickNoteSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedContact || !quickNoteText.trim()) return;
    try {
      const created = await createInteraction(
        {
          contact_id: selectedContact.id,
          account_id: selectedContact.account_id ?? undefined,
          type: "note",
          direction: "outbound",
          subject: `Nota rápida: ${quickNoteText.trim().slice(0, 60)}`,
          content_body: quickNoteText.trim(),
        },
        accessToken ?? undefined
      );
      setContactTimeline((prev) => [created, ...prev]);
      setQuickNoteText("");
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo registrar la nota.");
    }
  };

  const handleMergeDuplicate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedContact || !mergeSourceId) return;
    setIsMerging(true);
    setError(null);
    try {
      const merged = await mergeContacts(
        selectedContact.id,
        mergeSourceId,
        accessToken ?? undefined
      );
      setSelectedContact(merged);
      setMergeSourceId("");
      await loadContacts();
      await openContactDrawer(merged);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo fusionar el contacto.");
    } finally {
      setIsMerging(false);
    }
  };

  const handleCreateContactSubmit = async (formData: ContactFormData) => {
    setIsSubmitting(true);
    try {
      await createContact(
        {
          first_name: formData.first_name,
          last_name: formData.last_name,
          email: formData.email,
          phone: formData.phone || undefined,
          job_title: formData.job_title || undefined,
          account_id: formData.account_id || undefined,
          lifecycle_stage: formData.lifecycle_stage,
        },
        accessToken ?? undefined
      );
      closeCreateModal();
      await loadContacts();
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleInlineStageChange = async (contact: Contact, newStage: string) => {
    if (contact.lifecycle_stage === newStage) return;
    try {
      const updated = await updateContact(
        contact.id,
        { lifecycle_stage: newStage },
        accessToken ?? undefined
      );
      setContacts((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo actualizar la etapa.");
    }
  };

  const handleInlineJobTitleSave = async (contact: Contact) => {
    try {
      const updated = await updateContact(
        contact.id,
        { job_title: jobTitleDraft.trim() || undefined },
        accessToken ?? undefined
      );
      setContacts((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
      setEditingJobId(null);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo actualizar el cargo.");
    }
  };

  const handleDeleteContact = async (id: string) => {
    setError(null);
    const target = contacts.find((c) => c.id === id);
    try {
      await deleteContact(id, accessToken ?? undefined);
      setContacts((prev) => prev.filter((c) => c.id !== id));
      setPendingDeleteId(null);
      if (target) {
        setLastDeletedContact({ id: target.id, name: `${target.first_name} ${target.last_name}` });
      }
      if (selectedContact?.id === id) setSelectedContact(null);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo eliminar el contacto.");
    }
  };

  const handleRestoreDeletedContact = async () => {
    if (!lastDeletedContact) return;
    setIsRestoring(true);
    setError(null);
    try {
      const restored = await restoreContact(lastDeletedContact.id, accessToken ?? undefined);
      setContacts((prev) => [restored, ...prev.filter((c) => c.id !== restored.id)]);
      setLastDeletedContact(null);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo restaurar el contacto.");
    } finally {
      setIsRestoring(false);
    }
  };

  const filteredContacts = contacts.filter((c) => {
    if (stageFilter !== "all" && c.lifecycle_stage !== stageFilter) return false;
    const q = searchQuery.toLowerCase();
    const fullName = `${c.first_name} ${c.last_name}`.toLowerCase();
    return (
      fullName.includes(q) ||
      c.email.toLowerCase().includes(q) ||
      (c.job_title && c.job_title.toLowerCase().includes(q))
    );
  });

  const canManageDelete = user?.role === "admin" || user?.role === "sales_manager";
  const isReadonly = user?.role === "readonly";

  return (
    <div className="flex flex-col h-full p-6 gap-5">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-border">
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-foreground">Directorio de Contactos</h1>
            <Badge variant="secondary" className="font-mono text-xs tabular-nums">
              {contacts.length} registros
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Edita cargos y etapas inline o haz clic en una fila para abrir el timeline y fusionar duplicados.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={loadContacts}
            isLoading={isLoading}
            className="gap-1.5"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Actualizar</span>
          </Button>

          {!isReadonly && (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsImportModalOpen(true)}
                className="gap-1.5"
              >
                <Upload className="h-3.5 w-3.5" />
                <span>Importar CSV</span>
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => setIsCreateModalOpen(true)}
                className="gap-1.5"
              >
                <Plus className="h-4 w-4" />
                <span>Nuevo Contacto</span>
              </Button>
            </>
          )}
        </div>
      </div>

      {lastDeletedContact && (
        <div
          role="status"
          className="flex items-center justify-between p-3 text-xs bg-muted border border-border rounded-md"
        >
          <span>
            Contacto <strong>{lastDeletedContact.name}</strong> archivado.
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              isLoading={isRestoring}
              onClick={handleRestoreDeletedContact}
              className="h-7 text-xs"
            >
              Deshacer eliminación
            </Button>
            <button
              type="button"
              onClick={() => setLastDeletedContact(null)}
              className="text-muted-foreground hover:text-foreground px-1"
            >
              Cerrar
            </button>
          </div>
        </div>
      )}

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
            onClick={loadContacts}
            className="text-destructive hover:bg-destructive/10 h-7 text-xs"
          >
            Reintentar
          </Button>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[240px] max-w-md">
          <Search
            className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground"
            aria-hidden="true"
          />
          <input
            type="text"
            aria-label="Buscar contactos"
            placeholder="Buscar por nombre, correo electrónico o cargo (Atajo: /)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full h-9 pl-9 pr-3 bg-card border border-border rounded-md text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>

        <select
          aria-label="Filtrar por etapa"
          value={stageFilter}
          onChange={(e) => setStageFilter(e.target.value)}
          className="h-9 px-3 bg-card border border-border rounded-md text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <option value="all">Todas las etapas</option>
          <option value="lead">Lead</option>
          <option value="marketing_qualified">MQL</option>
          <option value="sales_qualified">SQL</option>
          <option value="customer">Customer</option>
          <option value="churned">Churned</option>
        </select>
      </div>

      <div className="flex-1 bg-card border border-border rounded-lg shadow-card overflow-hidden flex flex-col">
        {isLoading ? (
          <div className="p-12 text-center text-xs text-muted-foreground">
            Cargando directorio de contactos...
          </div>
        ) : filteredContacts.length === 0 ? (
          <div className="p-12 text-center flex flex-col items-center justify-center gap-2">
            <Users className="h-8 w-8 text-muted-foreground/60" aria-hidden="true" />
            <h3 className="text-sm font-medium text-foreground">No se encontraron contactos</h3>
            <p className="text-xs text-muted-foreground max-w-sm">
              {searchQuery || stageFilter !== "all"
                ? "No hay coincidencias con los filtros actuales."
                : "Presiona la tecla C o el botón inferior para registrar tu primer contacto."}
            </p>
            {!searchQuery && stageFilter === "all" && !isReadonly && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsCreateModalOpen(true)}
                className="mt-2 text-xs gap-1.5"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>Registrar primer contacto</span>
              </Button>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs tabular-nums" aria-label="Lista de contactos">
              <thead className="bg-muted/50 border-b border-border text-muted-foreground font-medium uppercase tracking-wider text-[11px]">
                <tr>
                  <th scope="col" className="py-2.5 px-4">
                    Nombre
                  </th>
                  <th scope="col" className="py-2.5 px-4">
                    Correo Electrónico
                  </th>
                  <th scope="col" className="py-2.5 px-4">
                    Empresa
                  </th>
                  <th scope="col" className="py-2.5 px-4">
                    Cargo (Inline)
                  </th>
                  <th scope="col" className="py-2.5 px-4">
                    Teléfono
                  </th>
                  <th scope="col" className="py-2.5 px-4">
                    Etapa (Inline)
                  </th>
                  <th scope="col" className="py-2.5 px-4 text-right">
                    Lead Score
                  </th>
                  {canManageDelete && (
                    <th scope="col" className="py-2.5 px-4 text-right">
                      Acciones
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredContacts.map((contact) => {
                  const accountName = accounts.find((a) => a.id === contact.account_id)?.name;
                  const isEditingJob = editingJobId === contact.id;

                  return (
                    <tr
                      key={contact.id}
                      onClick={() => void openContactDrawer(contact)}
                      className="hover:bg-muted/25 transition-colors cursor-pointer"
                    >
                      <td className="py-2.5 px-4 font-medium text-foreground">
                        {contact.first_name} {contact.last_name}
                      </td>
                      <td className="py-2.5 px-4 text-muted-foreground">
                        <div className="flex items-center gap-1.5">
                          <Mail className="h-3.5 w-3.5 text-muted-foreground/70" />
                          <span>{contact.email}</span>
                        </div>
                      </td>
                      <td className="py-2.5 px-4 text-muted-foreground">
                        {accountName ? (
                          <span className="inline-flex items-center gap-1 text-foreground">
                            <Building2 className="h-3 w-3 text-muted-foreground" />
                            <span>{accountName}</span>
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td
                        className="py-2.5 px-4 text-muted-foreground"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {isEditingJob ? (
                          <div className="inline-flex items-center gap-1">
                            <input
                              type="text"
                              aria-label={`Cargo de ${contact.first_name}`}
                              value={jobTitleDraft}
                              onChange={(e) => setJobTitleDraft(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") {
                                  e.preventDefault();
                                  void handleInlineJobTitleSave(contact);
                                } else if (e.key === "Escape") {
                                  setEditingJobId(null);
                                }
                              }}
                              className="h-7 px-2 bg-background border border-primary rounded text-xs text-foreground"
                              autoFocus
                            />
                            <button
                              type="button"
                              onClick={() => void handleInlineJobTitleSave(contact)}
                              className="p-1 text-success"
                              aria-label="Guardar cargo"
                            >
                              <Check className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        ) : (
                          <button
                            type="button"
                            disabled={isReadonly}
                            onClick={() => {
                              setEditingJobId(contact.id);
                              setJobTitleDraft(contact.job_title || "");
                            }}
                            aria-label={`Editar cargo de ${contact.first_name} ${contact.last_name}`}
                            className="inline-flex items-center gap-1.5 hover:text-foreground rounded px-1 py-0.5 hover:bg-muted transition-colors"
                          >
                            <Briefcase className="h-3.5 w-3.5 text-muted-foreground/70" />
                            <span>{contact.job_title || "Añadir cargo"}</span>
                            {!isReadonly && <Edit3 className="h-3 w-3 opacity-60" />}
                          </button>
                        )}
                      </td>
                      <td className="py-2.5 px-4 text-muted-foreground">
                        {contact.phone ? (
                          <div className="flex items-center gap-1.5 font-mono">
                            <Phone className="h-3.5 w-3.5 text-muted-foreground/70" />
                            <span>{contact.phone}</span>
                          </div>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-2.5 px-4" onClick={(e) => e.stopPropagation()}>
                        <select
                          aria-label={`Cambiar etapa de ${contact.first_name} ${contact.last_name}`}
                          disabled={isReadonly}
                          value={contact.lifecycle_stage}
                          onChange={(e) => void handleInlineStageChange(contact, e.target.value)}
                          className="h-7 px-2 bg-background border border-border rounded text-xs capitalize text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                        >
                          <option value="lead">Lead</option>
                          <option value="marketing_qualified">MQL</option>
                          <option value="sales_qualified">SQL</option>
                          <option value="customer">Customer</option>
                          <option value="churned">Churned</option>
                        </select>
                      </td>
                      <td className="py-2.5 px-4 text-right font-mono font-semibold text-foreground">
                        {contact.lead_score}
                      </td>
                      {canManageDelete && (
                        <td
                          className="py-2.5 px-4 text-right"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {pendingDeleteId === contact.id ? (
                            <div className="inline-flex items-center gap-1">
                              <Button
                                variant="destructive"
                                size="sm"
                                onClick={() => void handleDeleteContact(contact.id)}
                                className="h-7 px-2 text-[11px]"
                              >
                                Confirmar
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => setPendingDeleteId(null)}
                                className="h-7 px-1.5 text-[11px]"
                              >
                                Cancelar
                              </Button>
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={() => setPendingDeleteId(contact.id)}
                              aria-label={`Eliminar contacto ${contact.first_name} ${contact.last_name}`}
                              className="p-1.5 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Contact Create Modal */}
      {showCreateModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Registrar contacto"
          onClick={closeCreateModal}
        >
          <div onClick={(e) => e.stopPropagation()} className="w-full max-w-2xl">
            <ContactForm
              accounts={accounts}
              onSubmit={handleCreateContactSubmit}
              onCancel={closeCreateModal}
              isLoading={isSubmitting}
            />
          </div>
        </div>
      )}

      {/* Slide-over Contact Peek Drawer */}
      {selectedContact && (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-background/50 backdrop-blur-[1px]"
          role="dialog"
          aria-modal="true"
          aria-label={`Ficha de ${selectedContact.first_name} ${selectedContact.last_name}`}
          onClick={() => setSelectedContact(null)}
        >
          <aside
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-lg h-full bg-card border-l border-border shadow-elevated flex flex-col overflow-hidden"
          >
            <header className="px-5 py-4 border-b border-border flex items-start justify-between bg-muted/20">
              <div>
                <h2 className="text-base font-bold text-foreground">
                  {selectedContact.first_name} {selectedContact.last_name}
                </h2>
                <p className="text-xs text-muted-foreground font-mono">
                  {selectedContact.email} · Score {selectedContact.lead_score}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedContact(null)}
                aria-label="Cerrar ficha de contacto"
                className="p-1.5 text-muted-foreground hover:text-foreground"
              >
                <X className="h-4 w-4" />
              </button>
            </header>

            <div className="p-4 border-b border-border flex flex-col gap-3">
              <form onSubmit={handleQuickNoteSubmit} className="flex gap-2">
                <input
                  type="text"
                  value={quickNoteText}
                  onChange={(e) => setQuickNoteText(e.target.value)}
                  placeholder="Registrar nota o llamada rápida en este contacto..."
                  className="flex-1 h-8 px-2.5 bg-background border border-border rounded text-xs"
                />
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  disabled={!quickNoteText.trim()}
                  className="h-8 text-xs gap-1"
                >
                  <Send className="h-3 w-3" />
                  <span>Guardar</span>
                </Button>
              </form>

              {/* Non-Destructive Contact Merge Tool */}
              {canManageDelete && contacts.length > 1 && (
                <form
                  onSubmit={handleMergeDuplicate}
                  className="flex items-center gap-2 pt-2 border-t border-border/60"
                >
                  <GitMerge className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                  <select
                    aria-label="Seleccionar contacto duplicado para fusionar"
                    value={mergeSourceId}
                    onChange={(e) => setMergeSourceId(e.target.value)}
                    className="flex-1 h-7 px-2 bg-background border border-border rounded text-[11px]"
                  >
                    <option value="">Fusionar duplicado dentro de este contacto...</option>
                    {contacts
                      .filter((c) => c.id !== selectedContact.id)
                      .map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.first_name} {c.last_name} ({c.email})
                        </option>
                      ))}
                  </select>
                  <Button
                    type="submit"
                    variant="outline"
                    size="sm"
                    isLoading={isMerging}
                    disabled={!mergeSourceId}
                    className="h-7 text-[11px]"
                  >
                    Fusionar
                  </Button>
                </form>
              )}
            </div>

            <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-4">
              {contactAffiliations.length > 0 && (
                <div className="flex flex-col gap-1.5">
                  <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                    Afiliaciones de Empresa ({contactAffiliations.length})
                  </h3>
                  <div className="flex flex-wrap gap-1.5">
                    {contactAffiliations.map((aff) => {
                      const accName =
                        accounts.find((a) => a.id === aff.account_id)?.name || aff.account_id;
                      return (
                        <Badge
                          key={aff.id}
                          variant={aff.is_primary ? "default" : "secondary"}
                          className="text-[11px]"
                        >
                          {accName} {aff.role_title ? `· ${aff.role_title}` : ""}
                        </Badge>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-2">
                <h3 className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                  Timeline de Interacciones ({contactTimeline.length})
                </h3>
                {contactTimeline.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    Sin interacciones registradas para este contacto.
                  </p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {contactTimeline.map((item) => (
                      <li
                        key={item.id}
                        className="p-3 rounded-lg bg-muted/30 border border-border text-xs flex flex-col gap-1"
                      >
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

                {timelineCursor && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleLoadMoreTimeline}
                    className="text-xs self-center mt-2"
                  >
                    Cargar siguientes actividades
                  </Button>
                )}
              </div>
            </div>
          </aside>
        </div>
      )}
      <CsvImportModal
        isOpen={isImportModalOpen}
        authToken={accessToken ?? undefined}
        onClose={() => setIsImportModalOpen(false)}
        onImported={loadContacts}
      />
    </div>
  );
}

export default function ContactsPage() {
  return (
    <Suspense
      fallback={
        <div className="p-6 text-xs text-muted-foreground">Cargando directorio de contactos...</div>
      }
    >
      <ContactsPageContent />
    </Suspense>
  );
}
