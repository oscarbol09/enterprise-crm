import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { API_BASE_URL } from "../lib/api-client";
import { RevenueReportsDashboard } from "../components/features/reports/revenue-reports-dashboard";
import { CsvImportModal } from "../components/features/contacts/csv-import-modal";

describe("Revenue Reports Dashboard & CSV Import Modal", () => {
  it("renders USD forecast KPIs, risk radar, attribution table, funnel bottleneck, quota recalculation, and CSV export", async () => {
    const user = userEvent.setup();

    server.use(
      http.get(`${API_BASE_URL}/analytics/forecast`, ({ request }) => {
        const url = new URL(request.url);
        const quota = Number(url.searchParams.get("quota_usd") || "250000");
        const coverage = Number((180000 / quota).toFixed(2));
        return HttpResponse.json({
          closed_won_usd: "110000.00",
          closed_lost_usd: "50000.00",
          open_pipeline_usd: "180000.00",
          commit_usd: "90000.00",
          best_case_usd: "50000.00",
          weighted_open_usd: "85000.00",
          total_projected_usd: "195000.00",
          open_deals_count: 3,
          won_deals_count: 2,
          lost_deals_count: 2,
          win_rate: "0.50",
          avg_won_deal_usd: "55000.00",
          avg_sales_cycle_days: "20.00",
          sales_velocity_usd_per_day: "4125.00",
          quota_usd: String(quota),
          pipeline_coverage_ratio: String(coverage),
          usd_at_risk: "80000.00",
          at_risk_deals: [
            {
              deal_id: "d-risk-1",
              title: "Contrato Global En Riesgo",
              normalized_amount_usd: "80000.00",
              expected_close_date: "2026-10-01",
              close_date_push_count: 3,
              days_in_stage: 22,
              risk_reasons: ["Fecha pospuesta 3 veces", "Fecha de cierre vencida"],
            },
          ],
          by_period: [
            {
              period: "2026-11",
              closed_won_usd: "110000.00",
              commit_usd: "90000.00",
              best_case_usd: "50000.00",
              pipeline_usd: "40000.00",
              weighted_open_usd: "85000.00",
              deal_count: 5,
            },
          ],
        });
      }),
      http.get(`${API_BASE_URL}/analytics/funnel`, () =>
        HttpResponse.json({
          stages: [
            {
              stage_id: "st-1",
              stage_name: "Prospección",
              position: 1,
              is_closed_won: false,
              is_closed_lost: false,
              deals_entered: 10,
              current_open_deals: 3,
              conversion_to_next_pct: "60.00",
              avg_dwell_days: "4.50",
            },
            {
              stage_id: "st-2",
              stage_name: "Negociación",
              position: 2,
              is_closed_won: false,
              is_closed_lost: false,
              deals_entered: 6,
              current_open_deals: 2,
              conversion_to_next_pct: "50.00",
              avg_dwell_days: "16.20",
            },
          ],
          bottleneck_stage_name: "Negociación",
        })
      ),
      http.get(`${API_BASE_URL}/analytics/attribution`, () =>
        HttpResponse.json({
          total_leads: 25,
          total_closed_won_usd: "110000.00",
          channels: [
            {
              source_channel: "referral",
              leads_count: 3,
              opportunities_count: 2,
              won_deals_count: 2,
              win_rate: "1.00",
              pipeline_generated_usd: "110000.00",
              closed_won_revenue_usd: "110000.00",
              avg_deal_size_usd: "55000.00",
              revenue_share_pct: "100.00",
            },
            {
              source_channel: "paid_search",
              leads_count: 22,
              opportunities_count: 2,
              won_deals_count: 0,
              win_rate: "0.00",
              pipeline_generated_usd: "50000.00",
              closed_won_revenue_usd: "0.00",
              avg_deal_size_usd: "0.00",
              revenue_share_pct: "0.00",
            },
          ],
        })
      ),
      http.get(`${API_BASE_URL}/data/export/deals`, () =>
        new HttpResponse("id,title,normalized_amount_usd\n1,'=EVIL,110000.00\n", {
          headers: { "Content-Type": "text/csv; charset=utf-8" },
        })
      ),
      http.get(`${API_BASE_URL}/analytics/waterfall`, () =>
        HttpResponse.json({
          from_date: "2026-10-21",
          to_date: "2026-11-20",
          starting_open_usd: "120000.00",
          new_deals_usd: "25000.00",
          expansion_usd: "20000.00",
          contraction_usd: "0.00",
          closed_won_usd: "40000.00",
          closed_lost_usd: "30000.00",
          ending_open_usd: "95000.00",
          slipped_deals_count: 1,
        })
      ),
      http.get(`${API_BASE_URL}/analytics/win-loss`, () =>
        HttpResponse.json({
          total_lost_deals: 1,
          total_lost_usd: "30000.00",
          by_category: [{ category: "missing_feature", lost_deals_count: 1, lost_usd: "30000.00" }],
          by_competitor: [{ name: "Salesforce", lost_deals_count: 1, lost_usd: "30000.00" }],
          by_missing_feature: [{ name: "SSO/SAML", lost_deals_count: 1, lost_usd: "30000.00" }],
        })
      ),
      http.post(`${API_BASE_URL}/analytics/snapshots`, () =>
        HttpResponse.json(
          { snapshot_date: "2026-11-20", captured_deals: 5, total_open_usd: "180000.00" },
          { status: 201 }
        )
      )
    );

    render(<RevenueReportsDashboard authToken="tok" />);

    expect(await screen.findByText("$195,000")).toBeInTheDocument();
    expect(screen.getByText("$4,125/d")).toBeInTheDocument();
    expect(screen.getByText("Contrato Global En Riesgo")).toBeInTheDocument();
    expect(screen.getByText(/Cuello de botella: Negociación/i)).toBeInTheDocument();
    expect(screen.getByText("referral")).toBeInTheDocument();
    expect(screen.getByText("100.0%")).toBeInTheDocument();
    expect(screen.getByText("Puente de Pipeline (Waterfall)")).toBeInTheDocument();
    expect(screen.getByText("$95,000")).toBeInTheDocument();
    expect(screen.getByText(/vs Salesforce: \$30,000/i)).toBeInTheDocument();
    expect(screen.getByText(/Brecha SSO\/SAML: \$30,000/i)).toBeInTheDocument();

    // Capture daily snapshot
    await user.click(screen.getByRole("button", { name: /Capturar Snapshot/i }));
    expect(await screen.findByText(/Snapshot capturado/i)).toBeInTheDocument();

    // Recalculate quota to 50,000 -> coverage becomes 3.60x ("Sana")
    const quotaInput = screen.getByLabelText(/Meta USD/i);
    await user.clear(quotaInput);
    await user.type(quotaInput, "50000");
    await user.click(screen.getByRole("button", { name: /Calcular/i }));
    expect(await screen.findByText("3.60x")).toBeInTheDocument();
    expect(screen.getByText("Sana")).toBeInTheDocument();

    // Trigger safe CSV export
    await user.click(screen.getByRole("button", { name: /Deals CSV/i }));
    expect(
      await screen.findByText(/Exportación CSV de deals descargada/i)
    ).toBeInTheDocument();
  });

  it("validates CSV import via Dry-Run preview with DLQ errors before confirming live import", async () => {
    const user = userEvent.setup();
    const onImported = vi.fn();

    server.use(
      http.post(`${API_BASE_URL}/data/contacts/import`, async ({ request }) => {
        const body = (await request.json()) as { dry_run: boolean; dedupe_strategy: string };
        return HttpResponse.json({
          dry_run: body.dry_run,
          import_batch_id: body.dry_run ? null : "batch-999",
          total_rows: 3,
          would_create: 1,
          would_update: body.dedupe_strategy === "update" ? 1 : 0,
          would_skip: body.dedupe_strategy === "skip" ? 1 : 0,
          would_create_deals: 1,
          created_count: body.dry_run ? 0 : 1,
          updated_count: body.dry_run ? 0 : body.dedupe_strategy === "update" ? 1 : 0,
          skipped_count: body.dry_run ? 0 : body.dedupe_strategy === "skip" ? 1 : 0,
          deals_created_count: body.dry_run ? 0 : 1,
          quarantined_count: 1,
          accounts_auto_created: body.dry_run ? 0 : 1,
          detected_columns: { first_name: "First Name", email: "Email Address" },
          errors: [{ row: 4, email: "bad", reason: "Invalid or missing email address: 'bad'" }],
        });
      }),
      http.post(`${API_BASE_URL}/data/imports/batch-999/rollback`, () =>
        HttpResponse.json({
          batch_id: "batch-999",
          status: "rolled_back",
          reverted_accounts: 1,
          reverted_contacts: 1,
          reverted_deals: 1,
        })
      )
    );

    render(
      <CsvImportModal
        isOpen={true}
        authToken="tok"
        onClose={vi.fn()}
        onImported={onImported}
      />
    );

    const textarea = screen.getByLabelText(/Contenido CSV de contactos/i);
    await user.type(
      textarea,
      "First Name,Email Address\nAna,ana@empresa.com\nBad,bad"
    );

    const confirmBtn = screen.getByRole("button", { name: /Confirmar Importación/i });
    expect(confirmBtn).toBeDisabled();

    // Step 1: Dry-Run preview
    await user.click(screen.getByRole("button", { name: /Validar \(Dry-Run\)/i }));
    expect(
      await screen.findByText(/Resultado de Simulación/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Línea 4: Invalid or missing email address/i)).toBeInTheDocument();
    expect(onImported).not.toHaveBeenCalled();

    // Step 2: Confirm live import
    expect(confirmBtn).not.toBeDisabled();
    await user.click(confirmBtn);
    expect(await screen.findByText(/Importación Aplicada/i)).toBeInTheDocument();
    expect(onImported).toHaveBeenCalledTimes(1);

    // Step 3: One-click batch rollback
    await user.click(screen.getByRole("button", { name: /Deshacer esta importación/i }));
    expect(await screen.findByText(/Lote revertido/i)).toBeInTheDocument();
    expect(onImported).toHaveBeenCalledTimes(2);
  });
});
