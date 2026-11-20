"use client";

import React, { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  AlertCircle,
  Briefcase,
  Mail,
  Phone,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Users,
} from "lucide-react";
import { Contact } from "../../types/crm";
import { ApiError, createContact, deleteContact, fetchContacts } from "../../lib/api-client";
import { useAuth } from "../../lib/auth-context";
import { ContactForm, ContactFormData } from "../../components/features/contacts/contact-form";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";

function ContactsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { accessToken, user } = useAuth();

  const [contacts, setContacts] = useState<Contact[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [stageFilter, setStageFilter] = useState<string>("all");
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

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
      const data = await fetchContacts(accessToken ?? undefined);
      setContacts(data);
    } catch (err: unknown) {
      const msg =
        err instanceof ApiError ? err.message : "Error al conectar con la API de contactos.";
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    let active = true;
    async function initContacts() {
      try {
        const data = await fetchContacts(accessToken ?? undefined);
        if (active) setContacts(data);
      } catch (err: unknown) {
        if (active) {
          const msg =
            err instanceof ApiError ? err.message : "Error al conectar con la API de contactos.";
          setError(msg);
        }
      } finally {
        if (active) setIsLoading(false);
      }
    }
    void initContacts();
    return () => {
      active = false;
    };
  }, [accessToken]);

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

  const handleDeleteContact = async (id: string) => {
    setError(null);
    try {
      await deleteContact(id, accessToken ?? undefined);
      setContacts((prev) => prev.filter((c) => c.id !== id));
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo eliminar el contacto.");
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

  const getStageBadgeVariant = (stage: string) => {
    switch (stage) {
      case "customer":
        return "success";
      case "sales_qualified":
        return "default";
      case "marketing_qualified":
        return "secondary";
      case "churned":
        return "destructive";
      default:
        return "outline";
    }
  };

  const canManageDelete = user?.role === "admin" || user?.role === "sales_manager";

  return (
    <div className="flex flex-col h-full p-6 gap-6">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-border">
        <div className="flex flex-col">
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-foreground">Directorio de Contactos</h1>
            <Badge variant="secondary" className="font-mono text-xs">
              {contacts.length} registros
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Personas y clientes potenciales aislados en tu tenant mediante PostgreSQL RLS.
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

          {user?.role !== "readonly" && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => setIsCreateModalOpen(true)}
              className="gap-1.5"
            >
              <Plus className="h-4 w-4" />
              <span>Nuevo Contacto</span>
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
            placeholder="Buscar por nombre, correo electrónico o cargo..."
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

      <div className="flex-1 bg-card border border-border rounded-xl shadow-card overflow-hidden flex flex-col">
        {isLoading ? (
          <div className="p-12 text-center text-xs text-muted-foreground animate-pulse">
            Cargando directorio de contactos desde PostgreSQL (RLS)...
          </div>
        ) : filteredContacts.length === 0 ? (
          <div className="p-12 text-center flex flex-col items-center justify-center gap-2">
            <Users className="h-8 w-8 text-muted-foreground/60" aria-hidden="true" />
            <h3 className="text-sm font-medium text-foreground">No se encontraron contactos</h3>
            <p className="text-xs text-muted-foreground max-w-sm">
              {searchQuery || stageFilter !== "all"
                ? "No hay coincidencias con los filtros actuales."
                : "Aún no hay contactos registrados en este tenant."}
            </p>
            {!searchQuery && stageFilter === "all" && user?.role !== "readonly" && (
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
            <table className="w-full text-left text-xs" aria-label="Lista de contactos">
              <thead className="bg-muted/50 border-b border-border text-muted-foreground font-medium uppercase tracking-wider text-[11px]">
                <tr>
                  <th scope="col" className="py-3 px-4">
                    Nombre
                  </th>
                  <th scope="col" className="py-3 px-4">
                    Correo Electrónico
                  </th>
                  <th scope="col" className="py-3 px-4">
                    Cargo
                  </th>
                  <th scope="col" className="py-3 px-4">
                    Teléfono
                  </th>
                  <th scope="col" className="py-3 px-4">
                    Etapa
                  </th>
                  <th scope="col" className="py-3 px-4">
                    Lead Score
                  </th>
                  <th scope="col" className="py-3 px-4">
                    Fecha de Alta
                  </th>
                  {canManageDelete && (
                    <th scope="col" className="py-3 px-4 text-right">
                      Acciones
                    </th>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredContacts.map((contact) => (
                  <tr key={contact.id} className="hover:bg-muted/20 transition-colors">
                    <td className="py-3 px-4 font-medium text-foreground">
                      {contact.first_name} {contact.last_name}
                    </td>
                    <td className="py-3 px-4 text-muted-foreground">
                      <div className="flex items-center gap-1.5">
                        <Mail className="h-3.5 w-3.5 text-muted-foreground/70" />
                        <span>{contact.email}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-muted-foreground">
                      {contact.job_title ? (
                        <div className="flex items-center gap-1.5">
                          <Briefcase className="h-3.5 w-3.5 text-muted-foreground/70" />
                          <span>{contact.job_title}</span>
                        </div>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-3 px-4 text-muted-foreground">
                      {contact.phone ? (
                        <div className="flex items-center gap-1.5 font-mono">
                          <Phone className="h-3.5 w-3.5 text-muted-foreground/70" />
                          <span>{contact.phone}</span>
                        </div>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <Badge
                        variant={getStageBadgeVariant(contact.lifecycle_stage)}
                        className="capitalize text-[10px]"
                      >
                        {contact.lifecycle_stage.replace("_", " ")}
                      </Badge>
                    </td>
                    <td className="py-3 px-4 font-mono font-semibold text-foreground">
                      {contact.lead_score}
                    </td>
                    <td className="py-3 px-4 text-muted-foreground">
                      {new Date(contact.created_at).toLocaleDateString()}
                    </td>
                    {canManageDelete && (
                      <td className="py-3 px-4 text-right">
                        <button
                          type="button"
                          onClick={() => handleDeleteContact(contact.id)}
                          aria-label={`Eliminar contacto ${contact.first_name} ${contact.last_name}`}
                          className="p-1.5 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

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
              onSubmit={handleCreateContactSubmit}
              onCancel={closeCreateModal}
              isLoading={isSubmitting}
            />
          </div>
        </div>
      )}
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
