import { describe, it, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import {
  API_BASE_URL,
  ApiError,
  approveAIProposal,
  bootstrapPipeline,
  createContact,
  createDeal,
  deleteContact,
  fetchAIProposals,
  fetchContacts,
  fetchCurrentUser,
  fetchDealInteractions,
  fetchDeals,
  fetchPipelineStages,
  getAccessToken,
  loginUser,
  logoutUser,
  moveDealStage,
  registerWorkspace,
  rejectAIProposal,
  runSemanticSearch,
  setAccessToken,
  summarizeInteraction,
} from "../lib/api-client";

describe("api-client", () => {
  beforeEach(() => {
    setAccessToken(null);
  });

  it("normalizes Decimal strings from FastAPI into numbers for deals and contacts", async () => {
    setAccessToken("valid-token");

    server.use(
      http.get(`${API_BASE_URL}/deals`, () =>
        HttpResponse.json([
          {
            id: "d-1",
            tenant_id: "t-1",
            pipeline_id: "p-1",
            stage_id: "s-1",
            owner_id: "u-1",
            title: "Enterprise Deal",
            amount: "145000.00",
            currency: "USD",
            forecast_category: "commit",
            win_probability: "0.80",
            is_won: false,
            is_lost: false,
            created_at: "2026-11-20T00:00:00Z",
            updated_at: "2026-11-20T00:00:00Z",
          },
        ])
      ),
      http.get(`${API_BASE_URL}/contacts`, () =>
        HttpResponse.json([
          {
            id: "c-1",
            tenant_id: "t-1",
            owner_id: "u-1",
            first_name: "Ana",
            last_name: "Gomez",
            email: "ana@acme.io",
            lead_score: "87.50",
            lifecycle_stage: "sales_qualified",
            created_at: "2026-11-20T00:00:00Z",
            updated_at: "2026-11-20T00:00:00Z",
          },
        ])
      )
    );

    const deals = await fetchDeals();
    const contacts = await fetchContacts();

    expect(deals[0].amount).toBe(145000);
    expect(deals[0].win_probability).toBe(0.8);
    expect(contacts[0].lead_score).toBe(87.5);
  });

  it("performs a single silent refresh retry on 401 and forwards updated Bearer token", async () => {
    setAccessToken("expired-token");
    let callCount = 0;

    server.use(
      http.get(`${API_BASE_URL}/contacts`, ({ request }) => {
        callCount += 1;
        if (request.headers.get("authorization") === "Bearer fresh-token") {
          return HttpResponse.json([]);
        }
        return HttpResponse.json({ detail: "Token expired" }, { status: 401 });
      }),
      http.post(`${API_BASE_URL}/auth/refresh`, () =>
        HttpResponse.json({
          access_token: "fresh-token",
          token_type: "bearer",
          expires_in: 900,
          refresh_token: "rt-2",
          user: {
            id: "u-1",
            tenant_id: "t-1",
            email: "admin@acme.io",
            full_name: "Admin",
            role: "admin",
          },
        })
      )
    );

    const contacts = await fetchContacts();
    expect(contacts).toEqual([]);
    expect(callCount).toBe(2);
  });

  it("throws ApiError with HTTP status and detail on error responses", async () => {
    setAccessToken("valid-token");
    server.use(
      http.get(`${API_BASE_URL}/deals`, () =>
        HttpResponse.json({ detail: "Access denied" }, { status: 403 })
      )
    );

    await expect(fetchDeals()).rejects.toMatchObject({
      name: "ApiError",
      status: 403,
      message: "Access denied",
    } satisfies Partial<ApiError>);
  });

  it("handles auth lifecycle and typed CRM/AI API mutations", async () => {
    server.use(
      http.post(`${API_BASE_URL}/auth/login`, () =>
        HttpResponse.json({
          access_token: "login-jwt",
          token_type: "bearer",
          expires_in: 900,
          user: { id: "u-1", tenant_id: "t-1", email: "a@b.com", full_name: "Ana", role: "admin" },
        })
      ),
      http.post(`${API_BASE_URL}/auth/register`, () =>
        HttpResponse.json({
          access_token: "reg-jwt",
          token_type: "bearer",
          expires_in: 900,
          user: { id: "u-2", tenant_id: "t-2", email: "c@d.com", full_name: "Carl", role: "admin" },
        })
      ),
      http.post(`${API_BASE_URL}/auth/logout`, () => HttpResponse.json({ ok: true })),
      http.get(`${API_BASE_URL}/auth/me`, () =>
        HttpResponse.json({
          id: "u-1",
          tenant_id: "t-1",
          email: "a@b.com",
          full_name: "Ana",
          role: "admin",
        })
      ),
      http.post(`${API_BASE_URL}/deals`, () =>
        HttpResponse.json({
          id: "d-2",
          tenant_id: "t-1",
          pipeline_id: "p-1",
          stage_id: "s-1",
          owner_id: "u-1",
          title: "New Deal",
          amount: "50000.00",
          currency: "USD",
          forecast_category: "pipeline",
          win_probability: "0.40",
          is_won: false,
          is_lost: false,
          created_at: "2026-11-20T00:00:00Z",
          updated_at: "2026-11-20T00:00:00Z",
        })
      ),
      http.get(`${API_BASE_URL}/deals/stages`, () =>
        HttpResponse.json([
          {
            id: "s-1",
            pipeline_id: "p-1",
            name: "Discovery",
            position: 1,
            default_probability: "0.25",
            is_closed_won: false,
            is_closed_lost: false,
          },
        ])
      ),
      http.post(`${API_BASE_URL}/deals/pipelines/bootstrap`, () =>
        HttpResponse.json([
          {
            id: "s-1",
            pipeline_id: "p-1",
            name: "Discovery",
            position: 1,
            default_probability: "0.25",
            is_closed_won: false,
            is_closed_lost: false,
          },
        ])
      ),
      http.post(`${API_BASE_URL}/deals/d-2/move-stage`, () =>
        HttpResponse.json({
          id: "d-2",
          tenant_id: "t-1",
          pipeline_id: "p-1",
          stage_id: "s-2",
          owner_id: "u-1",
          title: "New Deal",
          amount: "50000.00",
          currency: "USD",
          forecast_category: "best_case",
          win_probability: "0.60",
          is_won: false,
          is_lost: false,
          created_at: "2026-11-20T00:00:00Z",
          updated_at: "2026-11-20T00:00:00Z",
        })
      ),
      http.get(`${API_BASE_URL}/deals/d-2/interactions`, () => HttpResponse.json([])),
      http.post(`${API_BASE_URL}/contacts`, () =>
        HttpResponse.json({
          id: "c-2",
          tenant_id: "t-1",
          owner_id: "u-1",
          first_name: "Luis",
          last_name: "Paz",
          email: "luis@acme.io",
          lead_score: "70.00",
          lifecycle_stage: "lead",
          created_at: "2026-11-20T00:00:00Z",
          updated_at: "2026-11-20T00:00:00Z",
        })
      ),
      http.delete(`${API_BASE_URL}/contacts/c-2`, () => new HttpResponse(null, { status: 204 })),
      http.post(`${API_BASE_URL}/ai/copilot/summarize-interaction`, () =>
        HttpResponse.json({
          executive_summary: "Strong signal",
          key_commitments_identified: ["Send MSA"],
          detected_sentiment: "positive",
          suggested_next_step: "Send contract",
          action_proposals: [],
          proposal_id: "prop-1",
          proposal_ids: ["prop-1"],
          ai_audit_id: "audit-1",
          model_used: "gemini/gemini-3.8-flash",
          key_source: "tenant_byok",
          is_stub: false,
        })
      ),
      http.get(`${API_BASE_URL}/ai/proposals`, () =>
        HttpResponse.json([
          {
            id: "prop-1",
            tenant_id: "t-1",
            agent_name: "deal_copilot",
            action_type: "create_task",
            target_entity_type: "deal",
            target_entity_id: "d-2",
            proposed_payload: { title: "Follow up" },
            reasoning_summary: "Buyer requested terms",
            status: "pending_review",
            created_at: "2026-11-20T00:00:00Z",
          },
        ])
      ),
      http.post(`${API_BASE_URL}/ai/proposals/prop-1/approve`, () =>
        HttpResponse.json({
          id: "prop-1",
          tenant_id: "t-1",
          agent_name: "deal_copilot",
          action_type: "create_task",
          target_entity_type: "deal",
          target_entity_id: "d-2",
          proposed_payload: { title: "Follow up" },
          reasoning_summary: "Buyer requested terms",
          status: "approved",
          created_at: "2026-11-20T00:00:00Z",
        })
      ),
      http.post(`${API_BASE_URL}/ai/proposals/prop-1/reject`, () =>
        HttpResponse.json({
          id: "prop-1",
          tenant_id: "t-1",
          agent_name: "deal_copilot",
          action_type: "create_task",
          target_entity_type: "deal",
          target_entity_id: "d-2",
          proposed_payload: { title: "Follow up" },
          reasoning_summary: "Buyer requested terms",
          status: "rejected",
          created_at: "2026-11-20T00:00:00Z",
        })
      ),
      http.post(`${API_BASE_URL}/ai/copilot/semantic-search`, () =>
        HttpResponse.json({
          results: [
            {
              entity_type: "contact",
              entity_id: "c-2",
              text_content: "VP Engineering",
              similarity: 0.91,
            },
          ],
          source: "pgvector",
        })
      )
    );

    const loginRes = await loginUser({ email: "a@b.com", password: "Password123!" });
    expect(loginRes.access_token).toBe("login-jwt");
    expect(getAccessToken()).toBe("login-jwt");

    const regRes = await registerWorkspace({
      tenant_name: "Beta",
      tenant_slug: "beta",
      admin_email: "c@d.com",
      admin_full_name: "Carl",
      password: "Password123!",
    });
    expect(regRes.access_token).toBe("reg-jwt");

    const me = await fetchCurrentUser();
    expect(me.email).toBe("a@b.com");

    const deal = await createDeal({ title: "New Deal", amount: 50000, stage_id: "s-1" });
    expect(deal.amount).toBe(50000);
    expect((await fetchPipelineStages())[0].default_probability).toBe(0.25);
    expect((await bootstrapPipeline()).length).toBe(1);
    expect((await moveDealStage("d-2", { new_stage_id: "s-2" })).win_probability).toBe(0.6);
    expect(await fetchDealInteractions("d-2")).toEqual([]);

    const contact = await createContact({
      first_name: "Luis",
      last_name: "Paz",
      email: "luis@acme.io",
    });
    expect(contact.lead_score).toBe(70);
    await deleteContact("c-2");

    const ai = await summarizeInteraction({
      contact_id: "c-2",
      deal_id: "d-2",
      raw_notes_or_transcript: "Needs contract",
      interaction_type: "call",
    });
    expect(ai.proposal_id).toBe("prop-1");
    expect((await fetchAIProposals()).length).toBe(1);
    expect((await approveAIProposal("prop-1")).status).toBe("approved");
    expect((await rejectAIProposal("prop-1", "Not needed")).status).toBe("rejected");
    expect((await runSemanticSearch("VP Engineering")).results[0].similarity).toBe(0.91);

    await logoutUser();
    expect(getAccessToken()).toBeNull();
  });
});
