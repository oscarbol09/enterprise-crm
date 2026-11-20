"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Command,
  DollarSign,
  KeyRound,
  Search,
  Sparkles,
  TrendingUp,
  UserPlus,
  Users,
} from "lucide-react";

interface CommandItem {
  id: string;
  category: "Acciones Rápidas" | "Navegación" | "Inteligencia Artificial";
  title: string;
  subtitle?: string;
  icon: React.ComponentType<{ className?: string }>;
  shortcut?: string;
  onSelect: () => void;
}

interface CommandPaletteProps {
  isOpen?: boolean;
  onClose?: () => void;
  onToggle?: () => void;
  onNavigate?: (path: string) => void;
}

export function CommandPalette({
  isOpen: controlledIsOpen,
  onClose: controlledOnClose,
  onToggle: controlledOnToggle,
  onNavigate,
}: CommandPaletteProps) {
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);

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
      } else if (e.key === "Escape" && isOpen) {
        e.preventDefault();
        handleClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isControlled, controlledOnClose, controlledOnToggle, handleClose]);

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
        category: "Inteligencia Artificial",
        title: "Copilot IA & Propuestas HITL",
        subtitle: "Resumir interacciones, aprobar propuestas y búsqueda semántica",
        icon: Sparkles,
        onSelect: () => {
          onNavigate?.("/ai");
          handleClose();
        },
      },
      {
        id: "nav-contacts",
        category: "Navegación",
        title: "Ir a Directorio de Contactos",
        subtitle: "Lista consolidada de clientes y leads",
        icon: Users,
        onSelect: () => {
          onNavigate?.("/contacts");
          handleClose();
        },
      },
      {
        id: "nav-pipeline",
        category: "Navegación",
        title: "Ir a Tablero de Ventas (Pipeline)",
        subtitle: "Vista Kanban de etapas y forecasting",
        icon: TrendingUp,
        onSelect: () => {
          onNavigate?.("/deals");
          handleClose();
        },
      },
      {
        id: "nav-byok",
        category: "Navegación",
        title: "Configuración BYOK (Credenciales LLM)",
        subtitle: "Gestión cifrada AES-256-GCM de API keys del tenant",
        icon: KeyRound,
        onSelect: () => {
          onNavigate?.("/settings/llm-credentials");
          handleClose();
        },
      },
    ],
    [onNavigate, handleClose]
  );

  const filteredCommands = useMemo(() => {
    if (!query.trim()) return commands;
    const lower = query.toLowerCase();
    return commands.filter(
      (cmd) =>
        cmd.title.toLowerCase().includes(lower) ||
        cmd.subtitle?.toLowerCase().includes(lower) ||
        cmd.category.toLowerCase().includes(lower)
    );
  }, [commands, query]);

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
        className="w-full max-w-xl bg-card border border-border rounded-xl shadow-elevated overflow-hidden flex flex-col focus:outline-none"
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
            placeholder="Buscar acciones o navegar (ej. Nuevo contacto, Copilot IA, Pipeline)..."
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
            <span>↑↓ para navegar</span>
            <span>↵ para seleccionar</span>
          </div>
          <div className="flex items-center gap-1 font-mono">
            <Command className="h-3 w-3" />
            <span>K para abrir / cerrar</span>
          </div>
        </div>
      </div>
    </div>
  );
}
