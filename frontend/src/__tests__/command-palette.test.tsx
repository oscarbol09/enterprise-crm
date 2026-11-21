import React, { useState } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { API_BASE_URL } from "../lib/api-client";
import { CommandPalette } from "../components/features/navigation/command-palette";

function ControlledPaletteHarness({
  onNavigate,
  authToken,
}: {
  onNavigate: (path: string) => void;
  authToken?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <CommandPalette
      isOpen={open}
      authToken={authToken}
      onClose={() => setOpen(false)}
      onToggle={() => setOpen((p) => !p)}
      onNavigate={onNavigate}
    />
  );
}

describe("CommandPalette", () => {
  it("opens and closes on Ctrl+K when controlled and navigates on Enter", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();

    render(<ControlledPaletteHarness onNavigate={onNavigate} />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    // Open with Ctrl+K
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.getByRole("dialog", { name: /Paleta de comandos/i })).toBeInTheDocument();

    // Filter to Revisión de Notas and press Enter
    const input = screen.getByRole("combobox");
    await user.type(input, "Revisión");
    await user.keyboard("{Enter}");

    expect(onNavigate).toHaveBeenCalledWith("/ai");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    // Toggle open and close again with Ctrl+K
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    await user.keyboard("{Control>}k{/Control}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("queries live tenant contacts and deals from Cmd+K and navigates on selection", async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();

    server.use(
      http.get(`${API_BASE_URL}/contacts`, () =>
        HttpResponse.json([
          {
            id: "c-live-1",
            tenant_id: "t-1",
            owner_id: "u-1",
            first_name: "Camila",
            last_name: "Ríos",
            email: "camila@andina.co",
            job_title: "CFO",
            lead_score: 92,
            lifecycle_stage: "sales_qualified",
            created_at: "2026-11-20T00:00:00Z",
            updated_at: "2026-11-20T00:00:00Z",
          },
        ])
      ),
      http.get(`${API_BASE_URL}/deals`, () =>
        HttpResponse.json([
          {
            id: "d-live-1",
            tenant_id: "t-1",
            pipeline_id: "p-1",
            stage_id: "st-1",
            owner_id: "u-1",
            title: "Contrato Andina Cloud",
            amount: "75000.00",
            currency: "USD",
            normalized_amount_usd: "75000.00",
            forecast_category: "commit",
            win_probability: "0.80",
            is_won: false,
            is_lost: false,
            created_at: "2026-11-20T00:00:00Z",
            updated_at: "2026-11-20T00:00:00Z",
          },
        ])
      )
    );

    render(<ControlledPaletteHarness onNavigate={onNavigate} authToken="live-token" />);

    await user.keyboard("{Control>}k{/Control}");
    const input = screen.getByRole("combobox");
    await user.type(input, "Andina");

    expect(await screen.findByText("Contrato Andina Cloud")).toBeInTheDocument();
    expect(await screen.findByText("Camila Ríos")).toBeInTheDocument();

    await user.click(screen.getByText("Camila Ríos"));
    expect(onNavigate).toHaveBeenCalledWith("/contacts?q=camila%40andina.co");
  });
});
