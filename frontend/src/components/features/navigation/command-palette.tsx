"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  BarChart3,
  Building2,
  CheckSquare,
  ClipboardCheck,
  Command,
  DollarSign,
  KeyRound,
  Search,
  TrendingUp,
  UserPlus,
  Users,
} from "lucide-react";

import { Contact, Deal } from "../../../types/crm";
import { fetchContacts, fetchDeals } from "../../../lib/api-client";

interface CommandItem {
  id: string;
  category:
    | "Acciones Rápidas"
    | "Navegación"
    | "Automatización"
    | "Contactos"
    | "Oportunidades";
  title: string;
  subtitle?: string;
  icon: React.ComponentType<{ className?: string }>;
  shortcut?: string;
  onSelect: () => void;
}

interface CommandPaletteProps {
  isOpen?: boolean;
  authToken?: string;
  onClose?: () => void;
  onToggle?: () => void;
  onNavigate?: (path: string) => void;
}

function isEditableElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  return target.isContentEditable;
}

export function CommandPalette({
  isOpen: controlledIsOpen,
  authToken,
  onClose: controlledOnClose,
  onToggle: controlledOnToggle,
  onNavigate,
}: CommandPaletteProps) {
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [liveContacts, setLiveContacts] = useState<Contact[]>([]);
  const [liveDeals, setLiveDeals] = useState<Deal[]>([]);

  const isControlled = controlledIsOpen !== undefined;
  const isOpen = isControlled ? controlledIsOpen : internalIsOpen;
  const inputRef = useRef<HTMLInputElement>(null);

  const handleClose = useCallback(() => {
    if (isControlled) {
      controlledOnClose?.();
    } else {
      setInternalIsOpen(false);
    }
    setQuery("");
    setSelectedIndex(0);
  }, [isControlled, controlledOnClose]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (isControlled) {
          if (controlledOnToggle) {
            controlledOnToggle();
          } else if (isOpen) {
            controlledOnClose?.();
          }
        } else {
          setInternalIsOpen((prev) => !prev);
        }
        return;
      }

      if (e.key === "Escape" && isOpen) {
        e.preventDefault();
        handleClose();
        return;
      }

      // Single-key global shortcuts when not typing in an input/textarea and palette is closed
      if (!isOpen && !e.metaKey && !e.ctrlKey && !e.altKey && !isEditableElement(e.target)) {
        const key = e.key.toLowerCase();
        if (key === "c") {
          e.preventDefault();
          onNavigate?.("/contacts?new=1");
        } else if (key === "d") {
          e.preventDefault();
          onNavigate?.("/deals?new=1");
        } else if (key === "/") {
          const searchInput = document.querySelector<HTMLInputElement>(
            'input[type="search"], input[aria-label*="Buscar"]'
          );
          if (searchInput) {
            e.preventDefault();
            searchInput.focus();
          }
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isControlled, controlledOnClose, controlledOnToggle, handleClose, onNavigate]);

  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => inputRef.current?.focus(), 30);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  const commands: CommandItem[] = useMemo(
    () => [
      {
        id: "create-contact",
        category: "Acciones Rápidas",
        title: "Nuevo Contacto",
        subtitle: "Registrar persona o lead en el tenant",
        icon: UserPlus,
        shortcut: "C",
        onSelect: () => {
          onNavigate?.("/contacts?new=1");
          handleClose();
        },
      },
      {
        id: "create-deal",
        category: "Acciones Rápidas",
        title: "Nueva Oportunidad (Deal)",
        subtitle: "Abrir trato comercial en el pipeline",
        icon: DollarSign,
        shortcut: "D",
        onSelect: () => {
          onNavigate?.("/deals?new=1");
          handleClose();
        },
      },
      {
        id: "ai-summarize",
        category: "Automatización",
        title: "Revisión de Notas y Aprobaciones",
        subtitle: "Extraer compromisos, aprobar cambios pendientes y buscar en el historial",
        icon: ClipboardCheck,
        onSelect: () => {
          onNavigate?.("/ai");
          handleClose();
        },
      },
      {
        id: "nav-pipeline",
        category: "Navegación",
        title: "Ir a Pipeline de Ventas",
        subtitle: "Vista Kanban y tabla operativa con forecast multidivisa",
        icon: TrendingUp,
        onSelect: () => {
          onNavigate?.("/deals");
          handleClose();
        },
      },
      {
        id: "nav-contacts",
        category: "Navegación",
        title: "Ir a Contactos",
        subtitle: "Edición inline, fusión de duplicados e historial",
        icon: Users,
        onSelect: () => {
          onNavigate?.("/contacts");
          handleClose();
        },
      },
      {
        id: "nav-accounts",
        category: "Navegación",
        title: "Ir a Empresas",
        subtitle: "Directorio de cuentas B2B y actividad consolidada",
        icon: Building2,
        onSelect: () => {
          onNavigate?.("/accounts");
          handleClose();
        },
      },
      {
        id: "nav-tasks",
        category: "Navegación",
        title: "Ir a Tareas y Seguimientos",
        subtitle: "Compromisos comerciales y limpieza de tareas vencidas",
        icon: CheckSquare,
        onSelect: () => {
          onNavigate?.("/tasks");
          handleClose();
        },
      },
      {
        id: "nav-reports",
        category: "Navegación",
        title: "Ir a Reportes y Forecast Financiero",
        subtitle: "Forecast USD, velocidad comercial, embudo y atribución por canal",
        icon: BarChart3,
        onSelect: () => {
          onNavigate?.("/reports");
          handleClose();
        },
      },
      {
        id: "nav-byok",
        category: "Navegación",
        title: "Claves API de Modelos",
        subtitle: "Administrar credenciales de proveedores externos",
        icon: KeyRound,
        onSelect: () => {
          onNavigate?.("/settings/llm-credentials");
          handleClose();
        },
      },
    ],
    [onNavigate, handleClose]
  );

  useEffect(() => {
    if (!isOpen || !authToken || query.trim().length < 2) {
      return;
    }
    let active = true;
    const trimmed = query.trim();
    const timer = setTimeout(() => {
      void Promise.all([
        fetchContacts(authToken, { q: trimmed }).catch(() => []),
        fetchDeals(authToken, trimmed).catch(() => []),
      ]).then(([foundContacts, foundDeals]) => {
        if (!active) return;
        setLiveContacts(foundContacts.slice(0, 4));
        setLiveDeals(foundDeals.slice(0, 4));
      });
    }, 180);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [isOpen, authToken, query]);

  const filteredCommands = useMemo(() => {
    const trimmed = query.trim();
    if (!trimmed) return commands;
    const lower = trimmed.toLowerCase();
    const staticMatches = commands.filter(
      (cmd) =>
        cmd.title.toLowerCase().includes(lower) ||
        cmd.subtitle?.toLowerCase().includes(lower) ||
        cmd.category.toLowerCase().includes(lower)
    );

    if (trimmed.length < 2) return staticMatches;

    const contactMatches: CommandItem[] = liveContacts.map((c) => ({
      id: `contact-${c.id}`,
      category: "Contactos",
      title: `${c.first_name} ${c.last_name}`,
      subtitle: `${c.email}${c.job_title ? ` · ${c.job_title}` : ""}`,
      icon: Users,
      onSelect: () => {
        onNavigate?.(`/contacts?q=${encodeURIComponent(c.email)}`);
        handleClose();
      },
    }));

    const dealMatches: CommandItem[] = liveDeals.map((d) => ({
      id: `deal-${d.id}`,
      category: "Oportunidades",
      title: d.title,
      subtitle: `$${Number(d.normalized_amount_usd ?? d.amount).toLocaleString("en-US")} USD · ${d.forecast_category}`,
      icon: DollarSign,
      onSelect: () => {
        onNavigate?.("/deals");
        handleClose();
      },
    }));

    return [...dealMatches, ...contactMatches, ...staticMatches];
  }, [commands, query, liveContacts, liveDeals, onNavigate, handleClose]);

  const handleInputKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % (filteredCommands.length || 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex(
        (prev) => (prev - 1 + (filteredCommands.length || 1)) % (filteredCommands.length || 1)
      );
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filteredCommands[selectedIndex]) {
        filteredCommands[selectedIndex].onSelect();
      }
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-20 sm:pt-28 bg-background/80 backdrop-blur-sm p-4"
      role="dialog"
      aria-modal="true"
      aria-label="Paleta de comandos globales del CRM"
      onClick={handleClose}
    >
      <div
        className="w-full max-w-xl bg-card border border-border rounded-lg shadow-elevated overflow-hidden flex flex-col focus:outline-none"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-card">
          <Search className="h-4 w-4 text-muted-foreground shrink-0" aria-hidden="true" />
          <input
            ref={inputRef}
            type="text"
            role="combobox"
            aria-expanded="true"
            aria-autocomplete="list"
            aria-controls="command-palette-results"
            className="w-full bg-transparent text-sm text-foreground placeholder:text-muted-foreground outline-none border-none p-0 focus:ring-0"
            placeholder="Buscar acciones o navegar (ej. Nuevo contacto, Empresas, Tareas, Pipeline)..."
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleInputKeyDown}
          />
          <kbd className="hidden sm:inline-flex items-center gap-1 text-[11px] font-mono text-muted-foreground bg-muted px-2 py-0.5 rounded border border-border">
            ESC
          </kbd>
        </div>

        <div
          id="command-palette-results"
          role="listbox"
          className="max-h-80 overflow-y-auto p-2 flex flex-col gap-1"
        >
          {filteredCommands.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              No se encontraron acciones para &ldquo;{query}&rdquo;
            </div>
          ) : (
            filteredCommands.map((cmd, idx) => {
              const isSelected = idx === selectedIndex;
              const Icon = cmd.icon;

              return (
                <div
                  key={cmd.id}
                  role="option"
                  aria-selected={isSelected}
                  className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-xs cursor-pointer transition-colors ${
                    isSelected
                      ? "bg-primary text-primary-foreground"
                      : "text-foreground hover:bg-muted/50"
                  }`}
                  onClick={() => cmd.onSelect()}
                  onMouseEnter={() => setSelectedIndex(idx)}
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <Icon
                      className={`h-4 w-4 shrink-0 ${
                        isSelected ? "text-primary-foreground" : "text-primary"
                      }`}
                    />
                    <div className="flex flex-col min-w-0">
                      <span className="font-medium truncate">{cmd.title}</span>
                      {cmd.subtitle && (
                        <span
                          className={`text-[11px] truncate ${
                            isSelected ? "text-primary-foreground/80" : "text-muted-foreground"
                          }`}
                        >
                          {cmd.subtitle}
                        </span>
                      )}
                    </div>
                  </div>

                  {cmd.shortcut ? (
                    <kbd
                      className={`font-mono text-[10px] px-1.5 py-0.5 rounded border ${
                        isSelected
                          ? "bg-primary-foreground/20 text-primary-foreground border-primary-foreground/30"
                          : "bg-muted text-muted-foreground border-border"
                      }`}
                    >
                      {cmd.shortcut}
                    </kbd>
                  ) : (
                    <ArrowRight
                      className={`h-3 w-3 shrink-0 ${
                        isSelected ? "text-primary-foreground" : "text-muted-foreground"
                      }`}
                    />
                  )}
                </div>
              );
            })
          )}
        </div>

        <div className="px-4 py-2 border-t border-border bg-muted/30 flex items-center justify-between text-[11px] text-muted-foreground">
          <div className="flex items-center gap-3">
            <span>↑↓ navegar</span>
            <span>↵ ejecutar</span>
            <span>C contacto · D deal · / buscar</span>
          </div>
          <div className="flex items-center gap-1 font-mono">
            <Command className="h-3 w-3" />
            <span>K</span>
          </div>
        </div>
      </div>
    </div>
  );
}
