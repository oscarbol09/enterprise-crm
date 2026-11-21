import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { API_BASE_URL } from "../lib/api-client";
import { Deal, PipelineStage } from "../types/crm";
import { DealKanbanBoard } from "../components/features/deals/deal-kanban-board";
import { DealDataGrid } from "../components/features/deals/deal-data-grid";
import { DealPeekDrawer } from "../components/features/deals/deal-peek-drawer";
import { ContactForm } from "../components/features/contacts/contact-form";
import { CommandPalette } from "../components/features/navigation/command-palette";
import {
  createAccount,
  createAccountAffiliation,
  createTask,
  fetchAccountAffiliations,
  fetchAccountTimeline,
  fetchAccounts,
  fetchContactAffiliations,
  fetchContactTimeline,
  fetchDealPlaybook,
  fetchTasks,
  mergeAccounts,
  mergeContacts,
  pruneZombieTasks,
  restoreContact,
  updateAccount,
  updateContact,
  updateTask,
} from "../lib/api-client";

const STAGES: PipelineStage[] = [
  {
    id: "st-1",
    pipeline_id: "pipe-1",
    name: "Prospección",
    position: 1,
    default_probability: 0.2,
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
];

const DEALS: Deal[] = [
  {
    id: "d-100",
    tenant_id: "t-1",
    pipeline_id: "pipe-1",
    stage_id: "st-1",
    owner_id: "u-1",
    title: "Plataforma Datos Latam",
    amount: 50000,
    currency: "USD",
    expected_close_date: "2020-01-15", // Overdue -> Rotten indicator
    forecast_category: "pipeline",
    win_probability: 0.2,
    is_won: false,
    is_lost: false,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
  },
  {
    id: "d-200",
    tenant_id: "t-1",
    pipeline_id: "pipe-1",
    stage_id: "st-2",
    owner_id: "u-1",
    title: "Expansión Cloud EMEA",
    amount: 100000,
    currency: "USD",
    expected_close_date: "2027-06-30",
    forecast_category: "commit",
    win_probability: 0.8,
    is_won: false,
    is_lost: false,
    created_at: "2026-11-10T00:00:00Z",
    updated_at: "2026-11-10T00:00:00Z",
  },
];

describe("Pipeline, Data Grid & Deal Peek Drawer Workflows", () => {
  it("supports native HTML5 Drag-and-Drop across Kanban columns and highlights overdue deals", async () => {
    let movedToStage: string | null = null;
    server.use(
      http.post(`${API_BASE_URL}/deals/d-100/move-stage`, async ({ request }) => {
        const body = (await request.json()) as { new_stage_id: string };
        movedToStage = body.new_stage_id;
        return HttpResponse.json({
          ...DEALS[0],
          stage_id: "st-2",
          win_probability: 0.8,
          forecast_category: "commit",
        });
      })
    );

    render(<DealKanbanBoard stages={STAGES} initialDeals={DEALS} authToken="tok" />);

    // Overdue / Rotten deal badge is shown for 2020-01-15
    expect(screen.getByText(/Vencido/i)).toBeInTheDocument();

    const card = screen.getByRole("listitem", { name: /Plataforma Datos Latam/i });
    const targetColumn = screen.getByRole("list", { name: /Oportunidades en Negociación/i });

    const dataTransfer = {
      data: {} as Record<string, string>,
      setData(key: string, val: string) {
        this.data[key] = val;
      },
      getData(key: string) {
        return this.data[key];
      },
      effectAllowed: "move",
      dropEffect: "move",
    };

    fireEvent.dragStart(card, { dataTransfer });
    fireEvent.dragOver(targetColumn, { dataTransfer });
    fireEvent.drop(targetColumn, { dataTransfer });

    await waitFor(() => {
      expect(movedToStage).toBe("st-2");
    });
  });

  it("renders High-Density DealDataGrid with footer aggregations and inline amount editing", async () => {
    const user = userEvent.setup();
    const onDealUpdated = vi.fn();

    server.use(
      http.patch(`${API_BASE_URL}/deals/d-100`, async ({ request }) => {
        const body = (await request.json()) as { amount: number };
        return HttpResponse.json({
          ...DEALS[0],
          amount: body.amount,
        });
      })
    );

    render(
      <DealDataGrid
        stages={STAGES}
        deals={DEALS}
        authToken="tok"
        onDealUpdated={onDealUpdated}
      />
    );

    // Gross sum = 50,000 + 100,000 = 150,000
    // Weighted sum = (50,000 * 0.2) + (100,000 * 0.8) = 10,000 + 80,000 = 90,000
    expect(screen.getByText(/\$150,000/)).toBeInTheDocument();
    expect(screen.getByText(/\$90,000/)).toBeInTheDocument();

    // Activate inline editing on d-100 amount cell
    const editAmountBtn = screen.getByRole("button", {
      name: /Editar monto de Plataforma Datos Latam/i,
    });
    await user.click(editAmountBtn);

    const amountInput = screen.getByRole("spinbutton", {
      name: /Monto de Plataforma Datos Latam/i,
    });
    await user.clear(amountInput);
    await user.type(amountInput, "65000{Enter}");

    await waitFor(() => {
      expect(onDealUpdated).toHaveBeenCalledWith(
        expect.objectContaining({ id: "d-100", amount: 65000 })
      );
    });

    // Also test inline stage change in DealDataGrid
    server.use(
      http.post(`${API_BASE_URL}/deals/d-100/move-stage`, () =>
        HttpResponse.json({
          ...DEALS[0],
          stage_id: "st-2",
          win_probability: 0.8,
        })
      )
    );
    const stageSelect = screen.getByLabelText(/Cambiar etapa de Plataforma Datos Latam/i);
    await user.selectOptions(stageSelect, "st-2");

    await waitFor(() => {
      expect(onDealUpdated).toHaveBeenCalledWith(
        expect.objectContaining({ id: "d-100", stage_id: "st-2" })
      );
    });
  });

  it("parses Omnibox slash commands (/call) inside DealPeekDrawer and logs interaction in-place", async () => {
    const user = userEvent.setup();
    let loggedPayload: Record<string, unknown> | null = null;

    server.use(
      http.get(`${API_BASE_URL}/deals/d-100/interactions`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/deals/d-100/participants`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/deals/d-100/stage-history`, () => HttpResponse.json([])),
      http.post(`${API_BASE_URL}/interactions`, async ({ request }) => {
        loggedPayload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            id: "int-99",
            tenant_id: "t-1",
            user_id: "u-1",
            deal_id: "d-100",
            type: loggedPayload.type,
            direction: "outbound",
            subject: loggedPayload.subject,
            content_body: loggedPayload.content_body,
            occurred_at: "2026-11-20T12:00:00Z",
            created_at: "2026-11-20T12:00:00Z",
          },
          { status: 201 }
        );
      })
    );

    render(
      <DealPeekDrawer
        deal={DEALS[0]}
        stages={STAGES}
        contacts={[]}
        authToken="tok"
        onClose={vi.fn()}
      />
    );

    const omnibox = await screen.findByPlaceholderText(/Escribe una nota o usa \/call/i);
    await user.type(omnibox, "/call Cliente confirmó presupuesto de $50k para diciembre");
    await user.click(screen.getByRole("button", { name: /Registrar Actividad/i }));

    await waitFor(() => {
      expect(loggedPayload).toMatchObject({
        deal_id: "d-100",
        type: "call",
        content_body: "Cliente confirmó presupuesto de $50k para diciembre",
      });
    });

    expect(
      await screen.findByText("Cliente confirmó presupuesto de $50k para diciembre")
    ).toBeInTheDocument();
  });

  it("triggers global single-key shortcuts (C and D) in CommandPalette when focus is outside inputs", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();

    render(<CommandPalette onNavigate={onNavigate} />);

    await user.keyboard("c");
    expect(onNavigate).toHaveBeenCalledWith("/contacts?new=1");

    await user.keyboard("d");
    expect(onNavigate).toHaveBeenCalledWith("/deals?new=1");

    // Open uncontrolled palette with Ctrl+K, navigate with ArrowDown/ArrowUp, select Empresas
    await user.keyboard("{Control>}k{/Control}");
    await user.keyboard("{ArrowDown}{ArrowUp}");
    const input = screen.getByRole("combobox");
    await user.type(input, "Empresas");
    await user.keyboard("{Enter}");
    expect(onNavigate).toHaveBeenCalledWith("/accounts");
  });

  it("auto-infers first name, last name, and primary company from email domain in ContactForm", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <ContactForm
        onSubmit={onSubmit}
        accounts={[
          {
            id: "acc-nordic",
            tenant_id: "t-1",
            name: "Nordic Cloud Systems",
            website: "https://nordiccloud.io",
            owner_id: "u-1",
            created_at: "2026-11-20T00:00:00Z",
            updated_at: "2026-11-20T00:00:00Z",
          },
        ]}
      />
    );

    const emailInput = screen.getByLabelText(/Correo Electrónico Corporativo/i);
    await user.type(emailInput, "laura.serrano@nordiccloud.io");

    const inferBtn = screen.getByRole("button", {
      name: /Autocompletar nombre y empresa por dominio/i,
    });
    await user.click(inferBtn);

    expect((screen.getByLabelText(/Nombre/i) as HTMLInputElement).value).toBe("Laura");
    expect((screen.getByLabelText(/Apellido/i) as HTMLInputElement).value).toBe("Serrano");
    expect((screen.getByLabelText(/Empresa Primaria/i) as HTMLSelectElement).value).toBe(
      "acc-nordic"
    );
  });

  it("handles DealPeekDrawer Buying Committee, SCD2 Stage History tabs, and In-Place Copilot", async () => {
    const user = userEvent.setup();

    server.use(
      http.get(`${API_BASE_URL}/deals/d-100/interactions`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/deals/d-100/participants`, () =>
        HttpResponse.json([
          {
            id: "p-1",
            tenant_id: "t-1",
            deal_id: "d-100",
            contact_id: "c-1",
            buying_role: "champion",
            is_primary: true,
            created_at: "2026-11-20T00:00:00Z",
          },
        ])
      ),
      http.post(`${API_BASE_URL}/deals/d-100/participants`, () =>
        HttpResponse.json(
          {
            id: "p-2",
            tenant_id: "t-1",
            deal_id: "d-100",
            contact_id: "c-2",
            buying_role: "economic_buyer",
            is_primary: false,
            created_at: "2026-11-20T00:00:00Z",
          },
          { status: 201 }
        )
      ),
      http.get(`${API_BASE_URL}/deals/d-100/stage-history`, () =>
        HttpResponse.json([
          {
            id: "sh-1",
            tenant_id: "t-1",
            deal_id: "d-100",
            from_stage_id: null,
            to_stage_id: "st-1",
            amount_at_transition: "50000.00",
            win_probability_at_transition: "0.20",
            entered_at: "2026-11-01T00:00:00Z",
            exited_at: null,
            duration_seconds: null,
          },
        ])
      ),
      http.post(`${API_BASE_URL}/ai/copilot/summarize-interaction`, () =>
        HttpResponse.json({
          executive_summary: "Presupuesto aprobado por el comité.",
          key_commitments_identified: ["Enviar contrato"],
          detected_sentiment: "positive",
          suggested_next_step: "Agendar firma legal",
          action_proposals: [],
          proposal_ids: [],
          ai_audit_id: "aud-1",
          model_used: "gemini-flash",
          key_source: "tenant_byok",
          is_stub: false,
        })
      ),
      http.get(`${API_BASE_URL}/deals/d-100/playbook`, () =>
        HttpResponse.json({
          deal_id: "d-100",
          stage_name: "Prospección",
          normalized_amount_usd: "50000.00",
          recommended_actions: ["Identificar el dolor operativo cuantificable"],
          follow_up_email_subject: "Resumen de prioridades operativas — Licencia Enterprise",
          follow_up_email_body: "Hola, gracias por la conversación sobre Licencia Enterprise.",
        })
      )
    );

    render(
      <DealPeekDrawer
        deal={DEALS[0]}
        stages={STAGES}
        contacts={[
          {
            id: "c-1",
            tenant_id: "t-1",
            owner_id: "u-1",
            first_name: "Laura",
            last_name: "Serrano",
            email: "laura@nordic.io",
            lead_score: 90,
            lifecycle_stage: "sales_qualified",
            created_at: "2026-11-20T00:00:00Z",
            updated_at: "2026-11-20T00:00:00Z",
          },
          {
            id: "c-2",
            tenant_id: "t-1",
            owner_id: "u-1",
            first_name: "Mateo",
            last_name: "Vargas",
            email: "mateo@nordic.io",
            lead_score: 80,
            lifecycle_stage: "sales_qualified",
            created_at: "2026-11-20T00:00:00Z",
            updated_at: "2026-11-20T00:00:00Z",
          },
        ]}
        authToken="tok"
        onClose={vi.fn()}
        onNavigateDeal={vi.fn()}
      />
    );

    // Run In-Place Note Extraction
    const omnibox = await screen.findByPlaceholderText(/Escribe una nota o usa \/call/i);
    await user.type(omnibox, "Reunión con comité financiero aprobando el presupuesto anual.");
    await user.click(screen.getByRole("button", { name: /Extraer resumen y pasos/i }));
    expect(await screen.findByText("Presupuesto aprobado por el comité.")).toBeInTheDocument();

    // Load Rep Playbook & insert follow-up email draft into Omnibox
    await user.click(screen.getByRole("button", { name: /Playbook & Borrador/i }));
    expect(
      await screen.findByText(/Identificar el dolor operativo cuantificable/i)
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Usar borrador en Omnibox/i }));
    expect(omnibox).toHaveValue("Hola, gracias por la conversación sobre Licencia Enterprise.");

    // Switch to Buying Committee tab and link c-2
    await user.click(screen.getByRole("button", { name: /Comité de Compra/i }));
    expect(await screen.findByText(/Laura Serrano/i)).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText(/Seleccionar contacto para comité/i), "c-2");
    await user.click(screen.getByRole("button", { name: /Vincular/i }));
    expect(await screen.findByText(/Mateo Vargas/i)).toBeInTheDocument();

    // Switch to Stage History tab
    await user.click(screen.getByRole("button", { name: /Historial de Etapas/i }));
    expect(await screen.findByText(/Creación inicial/i)).toBeInTheDocument();
  });

  it("executes typed API client calls for accounts, affiliations, timelines, tasks, and contact merges", async () => {
    server.use(
      http.get(`${API_BASE_URL}/accounts`, () =>
        HttpResponse.json([
          {
            id: "a-1",
            tenant_id: "t-1",
            name: "Acme",
            annual_revenue: "500000.00",
            owner_id: "u-1",
            created_at: "2026-11-20T00:00:00Z",
            updated_at: "2026-11-20T00:00:00Z",
          },
        ])
      ),
      http.post(`${API_BASE_URL}/accounts`, () =>
        HttpResponse.json({
          id: "a-2",
          tenant_id: "t-1",
          name: "NewAcc",
          annual_revenue: null,
          owner_id: "u-1",
          created_at: "2026-11-20T00:00:00Z",
          updated_at: "2026-11-20T00:00:00Z",
        })
      ),
      http.patch(`${API_BASE_URL}/accounts/a-2`, () =>
        HttpResponse.json({
          id: "a-2",
          tenant_id: "t-1",
          name: "UpdatedAcc",
          annual_revenue: "1000.00",
          owner_id: "u-1",
          created_at: "2026-11-20T00:00:00Z",
          updated_at: "2026-11-20T00:00:00Z",
        })
      ),
      http.get(`${API_BASE_URL}/accounts/a-1/timeline`, () =>
        HttpResponse.json({ items: [], next_cursor: null })
      ),
      http.get(`${API_BASE_URL}/accounts/a-1/affiliations`, () => HttpResponse.json([])),
      http.post(`${API_BASE_URL}/accounts/a-1/affiliations`, () =>
        HttpResponse.json({
          id: "aff-1",
          tenant_id: "t-1",
          account_id: "a-1",
          contact_id: "c-1",
          is_primary: true,
          is_active: true,
          created_at: "2026-11-20T00:00:00Z",
          updated_at: "2026-11-20T00:00:00Z",
        })
      ),
      http.patch(`${API_BASE_URL}/contacts/c-1`, () =>
        HttpResponse.json({
          id: "c-1",
          tenant_id: "t-1",
          owner_id: "u-1",
          first_name: "Ana",
          last_name: "Gomez",
          email: "ana@acme.io",
          lead_score: "95.00",
          lifecycle_stage: "customer",
          created_at: "2026-11-20T00:00:00Z",
          updated_at: "2026-11-20T00:00:00Z",
        })
      ),
      http.post(`${API_BASE_URL}/contacts/c-1/merge`, () =>
        HttpResponse.json({
          id: "c-1",
          tenant_id: "t-1",
          owner_id: "u-1",
          first_name: "Ana",
          last_name: "Gomez",
          email: "ana@acme.io",
          lead_score: "95.00",
          lifecycle_stage: "customer",
          created_at: "2026-11-20T00:00:00Z",
          updated_at: "2026-11-20T00:00:00Z",
        })
      ),
      http.get(`${API_BASE_URL}/contacts/c-1/timeline`, () =>
        HttpResponse.json({ items: [], next_cursor: null })
      ),
      http.get(`${API_BASE_URL}/contacts/c-1/affiliations`, () => HttpResponse.json([])),
      http.get(`${API_BASE_URL}/tasks`, () => HttpResponse.json([])),
      http.post(`${API_BASE_URL}/tasks`, () =>
        HttpResponse.json({
          id: "tsk-1",
          tenant_id: "t-1",
          assigned_to: "u-1",
          created_by: "u-1",
          title: "Call back",
          priority: "high",
          status: "pending",
          due_date: "2026-11-22T00:00:00Z",
          created_at: "2026-11-20T00:00:00Z",
          updated_at: "2026-11-20T00:00:00Z",
        })
      ),
      http.patch(`${API_BASE_URL}/tasks/tsk-1`, () =>
        HttpResponse.json({
          id: "tsk-1",
          tenant_id: "t-1",
          assigned_to: "u-1",
          created_by: "u-1",
          title: "Call back",
          priority: "high",
          status: "completed",
          due_date: "2026-11-22T00:00:00Z",
          created_at: "2026-11-20T00:00:00Z",
          updated_at: "2026-11-20T00:00:00Z",
        })
      )
    );

    const accs = await fetchAccounts("tok", "Acme");
    expect(accs[0].annual_revenue).toBe(500000);
    const createdAcc = await createAccount({ name: "NewAcc" }, "tok");
    expect(createdAcc.annual_revenue).toBeNull();
    const updatedAcc = await updateAccount("a-2", { name: "UpdatedAcc" }, "tok");
    expect(updatedAcc.annual_revenue).toBe(1000);
    expect((await fetchAccountTimeline("a-1", "cur-1", "tok")).items).toEqual([]);
    expect(await fetchAccountAffiliations("a-1", "tok")).toEqual([]);
    expect((await createAccountAffiliation("a-1", { contact_id: "c-1" }, "tok")).id).toBe("aff-1");

    expect((await updateContact("c-1", { lifecycle_stage: "customer" }, "tok")).lead_score).toBe(95);
    expect((await mergeContacts("c-1", "c-dup", "tok")).id).toBe("c-1");
    expect((await fetchContactTimeline("c-1", undefined, "tok")).items).toEqual([]);
    expect(await fetchContactAffiliations("c-1", "tok")).toEqual([]);

    expect(await fetchTasks("tok")).toEqual([]);
    const tsk = await createTask({ title: "Call back", due_date: "2026-11-22T00:00:00Z" }, "tok");
    expect(tsk.status).toBe("pending");
    const doneTsk = await updateTask("tsk-1", { status: "completed" }, "tok");
    expect(doneTsk.status).toBe("completed");

    server.use(
      http.post(`${API_BASE_URL}/contacts/c-1/restore`, () =>
        HttpResponse.json({
          id: "c-1",
          tenant_id: "t-1",
          owner_id: "u-1",
          first_name: "Ana",
          last_name: "Gomez",
          email: "ana@acme.io",
          lead_score: "95.00",
          lifecycle_stage: "customer",
          created_at: "2026-11-20T00:00:00Z",
          updated_at: "2026-11-20T00:00:00Z",
        })
      ),
      http.post(`${API_BASE_URL}/accounts/a-1/merge`, () =>
        HttpResponse.json({
          id: "a-1",
          tenant_id: "t-1",
          name: "Acme",
          annual_revenue: "650000.00",
          owner_id: "u-1",
          created_at: "2026-11-20T00:00:00Z",
          updated_at: "2026-11-20T00:00:00Z",
        })
      ),
      http.post(`${API_BASE_URL}/tasks/prune-zombies`, () =>
        HttpResponse.json({
          pruned_count: 2,
          pruned_task_ids: ["tsk-old-1", "tsk-old-2"],
        })
      ),
      http.get(`${API_BASE_URL}/deals/d-100/playbook`, () =>
        HttpResponse.json({
          deal_id: "d-100",
          stage_name: "Negociación",
          normalized_amount_usd: "108000.00",
          recommended_actions: ["Revisar redlines legales"],
          follow_up_email_subject: "Contrato MSA",
          follow_up_email_body: "Adjuntamos términos finales.",
        })
      )
    );

    const restoredContact = await restoreContact("c-1", "tok");
    expect(restoredContact.id).toBe("c-1");
    const mergedAccount = await mergeAccounts("a-1", "a-dup", "tok");
    expect(mergedAccount.annual_revenue).toBe(650000);
    const pruned = await pruneZombieTasks(14, "tok");
    expect(pruned.pruned_count).toBe(2);
    const pb = await fetchDealPlaybook("d-100", "tok");
    expect(pb.normalized_amount_usd).toBe(108000);
  });

  it("normalizes multi-currency deals (USD + EUR) into exact USD pipeline totals in DealDataGrid", () => {
    const multiCurrencyDeals: Deal[] = [
      {
        ...DEALS[0],
        id: "d-usd",
        title: "Trato Norteamérica",
        amount: 50000,
        currency: "USD",
        exchange_rate_to_usd: 1.0,
        normalized_amount_usd: 50000,
        win_probability: 0.5,
      },
      {
        ...DEALS[0],
        id: "d-eur",
        title: "Trato Europa",
        amount: 100000,
        currency: "EUR",
        exchange_rate_to_usd: 1.08,
        normalized_amount_usd: 108000,
        win_probability: 0.5,
      },
    ];

    render(<DealDataGrid stages={STAGES} deals={multiCurrencyDeals} />);

    // 50,000 USD + 108,000 USD (from 100,000 EUR @ 1.08) = $158,000 gross total, not $150,000
    expect(screen.getByText("$158,000")).toBeInTheDocument();
    // Weighted total: 50% of 158,000 = $79,000
    expect(screen.getByText("$79,000")).toBeInTheDocument();
    // Shows normalized USD badge next to EUR amount
    expect(screen.getByText(/≈\$108,000 USD/i)).toBeInTheDocument();
  });

  it("highlights stale open deals (>14 days without activity) directly on Kanban cards", () => {
    const twentyDaysAgo = new Date(Date.now() - 20 * 86400000).toISOString();
    const staleDeals: Deal[] = [
      {
        ...DEALS[0],
        id: "d-stale",
        title: "Trato Estancado B2B",
        expected_close_date: "2029-12-31",
        stage_entered_at: twentyDaysAgo,
        last_interaction_at: twentyDaysAgo,
      },
    ];

    render(<DealKanbanBoard stages={STAGES} initialDeals={staleDeals} />);

    expect(screen.getByText(/Estancado 20d/i)).toBeInTheDocument();
  });

  it("opens an inline 1-field Stage-Gate popover on 422 X-Stage-Gate-Fields and retries move automatically", async () => {
    const user = userEvent.setup();
    const onDealMoved = vi.fn();
    let moveAttempt = 0;

    server.use(
      http.post(`${API_BASE_URL}/deals/d-100/move-stage`, () => {
        moveAttempt += 1;
        if (moveAttempt === 1) {
          return HttpResponse.json(
            { detail: "Custom field 'tax_id_nit' (NIT / Tax ID) is required." },
            {
              status: 422,
              headers: {
                "X-Stage-Gate-Fields": JSON.stringify([
                  { field_key: "tax_id_nit", label: "NIT / Tax ID", field_type: "text", allowed_values: [] },
                ]),
              },
            }
          );
        }
        return HttpResponse.json({
          ...DEALS[0],
          stage_id: "st-2",
          win_probability: 0.8,
          metadata: { tax_id_nit: "900123456-1" },
        });
      }),
      http.patch(`${API_BASE_URL}/deals/d-100`, () =>
        HttpResponse.json({
          ...DEALS[0],
          metadata: { tax_id_nit: "900123456-1" },
        })
      )
    );

    render(<DealKanbanBoard stages={STAGES} initialDeals={DEALS} onDealMoved={onDealMoved} />);

    const stageSelect = screen.getByLabelText(/Mover Plataforma Datos Latam a etapa/i);
    await user.selectOptions(stageSelect, "st-2");

    // Inline Stage-Gate dialog opens focused on NIT / Tax ID
    const gateInput = await screen.findByLabelText(/NIT \/ Tax ID/i);
    await user.type(gateInput, "900123456-1");
    await user.click(screen.getByRole("button", { name: /Guardar y Mover/i }));

    await waitFor(() => {
      expect(onDealMoved).toHaveBeenCalledWith(expect.objectContaining({ stage_id: "st-2" }));
    });
  });

  it("navigates DealDataGrid rows with j/k keys and opens Peek Drawer on Space", async () => {
    const user = userEvent.setup();
    const onDealClick = vi.fn();
    const twoDeals: Deal[] = [
      DEALS[0],
      { ...DEALS[0], id: "d-200", title: "Segundo Trato Corporativo" },
    ];

    render(<DealDataGrid stages={STAGES} deals={twoDeals} onDealClick={onDealClick} />);

    // Press j twice to focus the second row, then Space to open it
    await user.keyboard("jj ");
    expect(onDealClick).toHaveBeenCalledWith(expect.objectContaining({ id: "d-200" }));
  });
});
