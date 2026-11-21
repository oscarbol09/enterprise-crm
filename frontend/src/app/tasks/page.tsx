"use client";

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  Circle,
  Plus,
  RefreshCw,
} from "lucide-react";
import { TaskItem } from "../../types/crm";
import { ApiError, createTask, fetchTasks, pruneZombieTasks, updateTask } from "../../lib/api-client";
import { useAuth } from "../../lib/auth-context";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";

export default function TasksPage() {
  const { accessToken, user } = useAuth();
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isPruning, setIsPruning] = useState(false);
  const [prunedNotice, setPrunedNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<"all" | "pending" | "completed">("all");

  // Quick Task Creator
  const [newTitle, setNewTitle] = useState("");
  const [newPriority, setNewPriority] = useState<"low" | "medium" | "high" | "urgent">("medium");
  const [isCreating, setIsCreating] = useState(false);

  const loadTasks = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchTasks(accessToken ?? undefined);
      setTasks(data);
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Error al cargar tareas.");
    } finally {
      setIsLoading(false);
    }
  }, [accessToken]);

  useEffect(() => {
    let active = true;
    async function initTasks() {
      try {
        const data = await fetchTasks(accessToken ?? undefined);
        if (active) setTasks(data);
      } catch (err: unknown) {
        if (active) {
          setError(err instanceof ApiError ? err.message : "Error al cargar tareas.");
        }
      } finally {
        if (active) setIsLoading(false);
      }
    }
    void initTasks();
    return () => {
      active = false;
    };
  }, [accessToken]);

  const handleQuickCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setIsCreating(true);
    setError(null);
    try {
      const dueIso = new Date(Date.now() + 86400000).toISOString();
      const created = await createTask(
        {
          title: newTitle.trim(),
          priority: newPriority,
          due_date: dueIso,
        },
        accessToken ?? undefined
      );
      setTasks((prev) => [created, ...prev]);
      setNewTitle("");
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo crear la tarea.");
    } finally {
      setIsCreating(false);
    }
  };

  const handleToggleTask = async (task: TaskItem) => {
    const nextStatus = task.status === "completed" ? "pending" : "completed";
    try {
      const updated = await updateTask(
        task.id,
        { status: nextStatus },
        accessToken ?? undefined
      );
      setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudo actualizar el estado de la tarea.");
    }
  };

  const handlePruneZombies = async () => {
    setIsPruning(true);
    setError(null);
    setPrunedNotice(null);
    try {
      const res = await pruneZombieTasks(14, accessToken ?? undefined);
      setPrunedNotice(`Se cancelaron ${res.pruned_count} tareas zombi (>14 días o deals cerrados).`);
      await loadTasks();
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "No se pudieron limpiar las tareas zombi.");
    } finally {
      setIsPruning(false);
    }
  };

  const filtered = tasks.filter((t) => {
    if (statusFilter === "pending") return t.status === "pending" || t.status === "in_progress";
    if (statusFilter === "completed") return t.status === "completed";
    return true;
  });

  return (
    <div className="flex flex-col h-full p-6 gap-5 max-w-5xl w-full mx-auto">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 pb-4 border-b border-border">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-foreground">Tareas y Seguimientos</h1>
            <Badge variant="secondary" className="font-mono text-xs tabular-nums">
              {tasks.filter((t) => t.status === "pending" || t.status === "in_progress").length} pendientes
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground mt-0.5">
            Compromisos pendientes del equipo, creados manualmente o aprobados desde minutas.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="inline-flex p-0.5 bg-muted border border-border rounded-lg text-xs">
            {(["all", "pending", "completed"] as const).map((st) => (
              <button
                key={st}
                type="button"
                onClick={() => setStatusFilter(st)}
                className={`px-2.5 py-1 rounded-md font-medium capitalize ${
                  statusFilter === st
                    ? "bg-card text-foreground shadow-subtle"
                    : "text-muted-foreground"
                }`}
              >
                {st === "all" ? "Todas" : st === "pending" ? "Pendientes" : "Completadas"}
              </button>
            ))}
          </div>
          {user?.role !== "readonly" && (
            <Button
              variant="outline"
              size="sm"
              onClick={handlePruneZombies}
              isLoading={isPruning}
              className="gap-1.5"
            >
              <span>Limpiar Tareas Zombi</span>
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={loadTasks} isLoading={isLoading} className="gap-1.5">
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Actualizar</span>
          </Button>
        </div>
      </div>

      {prunedNotice && (
        <div
          role="status"
          className="p-3 text-xs text-foreground bg-muted border border-border rounded-md flex items-center justify-between"
        >
          <span>{prunedNotice}</span>
          <button
            type="button"
            onClick={() => setPrunedNotice(null)}
            className="text-muted-foreground hover:text-foreground"
          >
            Cerrar
          </button>
        </div>
      )}

      {error && (
        <div role="alert" className="p-3 text-xs text-destructive bg-destructive/10 border border-destructive/20 rounded-md flex items-center gap-2">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {user?.role !== "readonly" && (
        <form
          onSubmit={handleQuickCreate}
          className="flex flex-wrap items-center gap-2 p-3 bg-card border border-border rounded-lg shadow-subtle"
        >
          <input
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="Añadir tarea rápida en 1 paso (ej. Enviar contrato marco a Laura)..."
            className="flex-1 min-w-[240px] h-9 px-3 bg-background border border-border rounded-md text-xs"
          />
          <select
            aria-label="Prioridad de tarea"
            value={newPriority}
            onChange={(e) =>
              setNewPriority(e.target.value as "low" | "medium" | "high" | "urgent")
            }
            className="h-9 px-2.5 bg-background border border-border rounded-md text-xs"
          >
            <option value="low">Prioridad Baja</option>
            <option value="medium">Prioridad Media</option>
            <option value="high">Prioridad Alta</option>
            <option value="urgent">Urgente</option>
          </select>
          <Button type="submit" variant="primary" size="sm" isLoading={isCreating} disabled={!newTitle.trim()} className="gap-1.5">
            <Plus className="h-3.5 w-3.5" />
            <span>Crear Tarea</span>
          </Button>
        </form>
      )}

      <div className="flex-1 bg-card border border-border rounded-lg shadow-card overflow-hidden">
        {isLoading ? (
          <div className="p-12 text-center text-xs text-muted-foreground">Cargando tareas...</div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center text-xs text-muted-foreground">
            No hay tareas en este filtro.
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {filtered.map((task) => {
              const isDone = task.status === "completed";
              return (
                <li
                  key={task.id}
                  className="p-3.5 hover:bg-muted/20 transition-colors flex items-center justify-between gap-3 text-xs"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <button
                      type="button"
                      onClick={() => void handleToggleTask(task)}
                      aria-label={isDone ? `Reabrir ${task.title}` : `Completar ${task.title}`}
                      className="text-muted-foreground hover:text-primary shrink-0"
                    >
                      {isDone ? (
                        <CheckCircle2 className="h-4 w-4 text-success" />
                      ) : (
                        <Circle className="h-4 w-4" />
                      )}
                    </button>
                    <div className="flex flex-col min-w-0">
                      <span
                        className={`font-medium truncate ${
                          isDone ? "line-through text-muted-foreground" : "text-foreground"
                        }`}
                      >
                        {task.title}
                      </span>
                      {task.description && (
                        <span className="text-[11px] text-muted-foreground truncate">
                          {task.description}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 tabular-nums">
                    <Badge
                      variant={
                        task.priority === "urgent" || task.priority === "high"
                          ? "warning"
                          : "secondary"
                      }
                      className="text-[10px] uppercase"
                    >
                      {task.priority}
                    </Badge>
                    <span className="text-[11px] text-muted-foreground font-mono flex items-center gap-1">
                      <Calendar className="h-3 w-3" />
                      {new Date(task.due_date).toLocaleDateString()}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
