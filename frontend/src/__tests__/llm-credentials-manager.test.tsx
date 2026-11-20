import React from "react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { API_BASE_URL } from "../lib/api-client";
import { LLMCredentialsManager } from "../components/features/settings/llm-credentials-manager";

describe("LLMCredentialsManager", () => {
  it("loads credentials from API_BASE_URL, registers masked key, and revokes inline", async () => {
    const user = userEvent.setup();
    let creds = [
      {
        id: "cred-1",
        tenant_id: "tenant-1",
        provider: "gemini",
        key_last_four: "1234",
        is_active: true,
        created_at: "2026-11-20T00:00:00Z",
        updated_at: "2026-11-20T00:00:00Z",
      },
    ];

    server.use(
      http.get(`${API_BASE_URL}/settings/llm-credentials`, () => HttpResponse.json(creds)),
      http.post(`${API_BASE_URL}/settings/llm-credentials`, async ({ request }) => {
        const body = (await request.json()) as { provider: string; raw_api_key: string };
        const created = {
          id: "cred-2",
          tenant_id: "tenant-1",
          provider: body.provider,
          key_last_four: body.raw_api_key.slice(-4),
          is_active: true,
          created_at: "2026-11-20T00:00:00Z",
          updated_at: "2026-11-20T00:00:00Z",
        };
        creds = [created, ...creds];
        return HttpResponse.json(created, { status: 201 });
      }),
      http.delete(`${API_BASE_URL}/settings/llm-credentials/cred-2`, () => {
        creds = creds.map((c) => (c.id === "cred-2" ? { ...c, is_active: false } : c));
        return new HttpResponse(null, { status: 204 });
      })
    );

    render(<LLMCredentialsManager authToken="admin-token" userRole="admin" />);

    expect(await screen.findByText(/1234/)).toBeInTheDocument();

    // Toggle visibility and register new OpenAI key
    const keyInput = screen.getByLabelText(/API Key Privada/i) as HTMLInputElement;
    expect(keyInput.type).toBe("password");
    await user.click(screen.getByRole("button", { name: /Mostrar clave mientras escribe/i }));
    expect(keyInput.type).toBe("text");

    await user.selectOptions(screen.getByLabelText(/Proveedor de IA/i), "openai");
    await user.type(keyInput, "sk-proj-secretkey9988");
    await user.click(screen.getByRole("button", { name: /Guardar Credencial/i }));

    expect(await screen.findByText(/9988/)).toBeInTheDocument();

    // Revoke inline confirmation
    const revokeBtns = screen.getAllByRole("button", { name: /Revocar/i });
    await user.click(revokeBtns[0]);
    await user.click(screen.getByRole("button", { name: /Confirmar/i }));

    expect(await screen.findByText(/Credencial de OPENAI revocada/i)).toBeInTheDocument();
  });

  it("blocks BYOK form when userRole is not admin", () => {
    render(<LLMCredentialsManager authToken="rep-token" userRole="sales_rep" />);
    expect(screen.getByRole("alert")).toHaveTextContent(/sales_rep/);
    expect(screen.queryByRole("button", { name: /Guardar Credencial/i })).not.toBeInTheDocument();
  });
});
