import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { API_BASE_URL } from "../lib/api-client";
import { DealKanbanBoard } from "../components/features/deals/deal-kanban-board";
import { Deal, PipelineStage } from "../types/crm";

const STAGES: PipelineStage[] = [
  {
    id: "st-1",
    pipeline_id: "pipe-1",
    name: "Prospección",
    position: 1,
    default_probability: 0.1,
    is_closed_won: false,
    is_closed_lost: false,
  },
  {
    id: "st-2",
    pipeline_id: "pipe-1",
    name: "Negociación",
    position: 2,
    default_probability: 0.8,
    is_closed_won: false,
    is_closed_lost: false,
  },
  {
    id: "st-3",
    pipeline_id: "pipe-1",
    name: "Cierre Perdido",
    position: 3,
    default_probability: 0,
    is_closed_won: false,
    is_closed_lost: true,
  },
];

const SAMPLE_DEAL: Deal = {
  id: "deal-1",
  tenant_id: "tenant-1",
  pipeline_id: "pipe-1",
  stage_id: "st-1",
  owner_id: "user-1",
  title: "Migración Cloud 5000",
  amount: 120000,
  currency: "USD",
  forecast_category: "pipeline",
  win_probability: 0.1,
  is_won: false,
  is_lost: false,
  created_at: "2026-11-20T00:00:00Z",
  updated_at: "2026-11-20T00:00:00Z",
};

describe("DealKanbanBoard", () => {
  it("synchronizes deals when initialDeals arrives asynchronously after mount", () => {
    const { rerender } = render(<DealKanbanBoard stages={STAGES} initialDeals={[]} />);
    expect(screen.queryByText("Migración Cloud 5000")).not.toBeInTheDocument();

    rerender(<DealKanbanBoard stages={STAGES} initialDeals={[SAMPLE_DEAL]} />);
    expect(screen.getByText("Migración Cloud 5000")).toBeInTheDocument();
  });

  it("rolls back optimistic transition and displays alert when API fails", async () => {
    const user = userEvent.setup();
    server.use(
      http.post(`${API_BASE_URL}/deals/deal-1/move-stage`, () =>
        HttpResponse.json({ detail: "Stage mismatch" }, { status: 400 })
      )
    );

    render(<DealKanbanBoard stages={STAGES} initialDeals={[SAMPLE_DEAL]} authToken="tok" />);
    const advanceBtn = screen.getByRole("button", {
      name: /Avanzar oportunidad Migración Cloud 5000 a Negociación/i,
    });
    await user.click(advanceBtn);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Stage mismatch");
    // Rolled back to original stage select value
    const select = screen.getByLabelText(/Mover Migración Cloud 5000 a etapa/i) as HTMLSelectElement;
    expect(select.value).toBe("st-1");
  });

  it("prompts for mandatory loss_reason before transitioning to Closed Lost", async () => {
    const user = userEvent.setup();
    let capturedBody: Record<string, unknown> | null = null;

    server.use(
      http.post(`${API_BASE_URL}/deals/deal-1/move-stage`, async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          ...SAMPLE_DEAL,
          stage_id: "st-3",
          win_probability: 0,
          is_lost: true,
          forecast_category: "omitted",
          loss_reason: capturedBody.loss_reason,
        });
      })
    );

    render(<DealKanbanBoard stages={STAGES} initialDeals={[SAMPLE_DEAL]} authToken="tok" />);

    const select = screen.getByLabelText(/Mover Migración Cloud 5000 a etapa/i);
    await user.selectOptions(select, "st-3");

    expect(screen.getByRole("dialog", { name: /Registrar motivo de pérdida/i })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Confirmar Cierre Perdido/i }));
    expect(await screen.findByText(/motivo de pérdida es obligatorio/i)).toBeInTheDocument();

    await user.type(
      screen.getByRole("textbox", { name: /Motivo de pérdida/i }),
      "Presupuesto diferido"
    );
    await user.click(screen.getByRole("button", { name: /Confirmar Cierre Perdido/i }));

    await waitFor(() => {
      expect(capturedBody).toEqual({
        new_stage_id: "st-3",
        loss_reason: "Presupuesto diferido",
        loss_category: "price",
      });
    });
  });
});
