import {
  AIProposal,
  AuthTokenResponse,
  Contact,
  ContactCreatePayload,
  Deal,
  DealCreatePayload,
  InteractionItem,
  InteractionSummarizePayload,
  InteractionSummarizeResponse,
  LLMCredential,
  LLMCredentialCreatePayload,
  LoginPayload,
  MoveDealStagePayload,
  PipelineStage,
  RegisterWorkspacePayload,
  SemanticSearchResponse,
  UserInfo,
} from "../types/crm";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

let inMemoryAccessToken: string | null = null;
let refreshInFlight: Promise<AuthTokenResponse | null> | null = null;

export function setAccessToken(token: string | null): void {
  inMemoryAccessToken = token;
}

export function getAccessToken(): string | null {
  return inMemoryAccessToken;
}

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

function buildHeaders(explicitToken?: string): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  const resolvedToken = explicitToken ?? inMemoryAccessToken;
  if (resolvedToken) {
    headers["Authorization"] = `Bearer ${resolvedToken}`;
  }
  return headers;
}

function normalizeDeal(raw: Deal): Deal {
  return {
    ...raw,
    amount: Number(raw.amount),
    win_probability: Number(raw.win_probability),
  };
}

function normalizeStage(raw: PipelineStage): PipelineStage {
  return {
    ...raw,
    default_probability: Number(raw.default_probability),
  };
}

function normalizeContact(raw: Contact): Contact {
  return {
    ...raw,
    lead_score: Number(raw.lead_score),
  };
}

async function requestJson<T>(
  path: string,
  options: RequestInit = {},
  explicitToken?: string,
  allowRefresh = true
): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const response = await fetch(url, {
    ...options,
    credentials: "include",
    headers: {
      ...buildHeaders(explicitToken),
      ...(options.headers as Record<string, string> | undefined),
    },
  });

  if (response.status === 401 && allowRefresh && !explicitToken && !path.startsWith("/auth/")) {
    const refreshed = await refreshSessionSafe();
    if (refreshed?.access_token) {
      return requestJson<T>(path, options, refreshed.access_token, false);
    }
  }

  if (!response.ok) {
    const errorJson = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new ApiError(
      response.status,
      errorJson.detail || `Error en solicitud a ${path} (HTTP ${response.status})`,
      errorJson
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function refreshSessionSafe(): Promise<AuthTokenResponse | null> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const resp = await fetch(`${API_BASE_URL}/auth/refresh`, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        if (!resp.ok) {
          setAccessToken(null);
          return null;
        }
        const data = (await resp.json()) as AuthTokenResponse;
        setAccessToken(data.access_token);
        return data;
      } catch {
        setAccessToken(null);
        return null;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

export async function loginUser(payload: LoginPayload): Promise<AuthTokenResponse> {
  const data = await requestJson<AuthTokenResponse>(
    "/auth/login",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    undefined,
    false
  );
  setAccessToken(data.access_token);
  return data;
}

export async function registerWorkspace(
  payload: RegisterWorkspacePayload
): Promise<AuthTokenResponse> {
  const data = await requestJson<AuthTokenResponse>(
    "/auth/register",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    undefined,
    false
  );
  setAccessToken(data.access_token);
  return data;
}

export async function logoutUser(): Promise<void> {
  try {
    await requestJson<void>("/auth/logout", { method: "POST", body: JSON.stringify({}) }, undefined, false);
  } finally {
    setAccessToken(null);
  }
}

export async function fetchCurrentUser(token?: string): Promise<UserInfo> {
  return requestJson<UserInfo>("/auth/me", { method: "GET" }, token);
}

export async function fetchDeals(token?: string): Promise<Deal[]> {
  const raw = await requestJson<Deal[]>("/deals", { method: "GET" }, token);
  return raw.map(normalizeDeal);
}

export async function createDeal(payload: DealCreatePayload, token?: string): Promise<Deal> {
  const raw = await requestJson<Deal>(
    "/deals",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token
  );
  return normalizeDeal(raw);
}

export async function fetchPipelineStages(token?: string): Promise<PipelineStage[]> {
  const raw = await requestJson<PipelineStage[]>("/deals/stages", { method: "GET" }, token);
  return raw.map(normalizeStage);
}

export async function bootstrapPipeline(token?: string): Promise<PipelineStage[]> {
  const raw = await requestJson<PipelineStage[]>(
    "/deals/pipelines/bootstrap",
    { method: "POST" },
    token
  );
  return raw.map(normalizeStage);
}

export async function moveDealStage(
  dealId: string,
  payload: MoveDealStagePayload,
  token?: string
): Promise<Deal> {
  const raw = await requestJson<Deal>(
    `/deals/${dealId}/move-stage`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token
  );
  return normalizeDeal(raw);
}

export async function fetchDealInteractions(
  dealId: string,
  token?: string
): Promise<InteractionItem[]> {
  return requestJson<InteractionItem[]>(`/deals/${dealId}/interactions`, { method: "GET" }, token);
}

export async function fetchContacts(token?: string): Promise<Contact[]> {
  const raw = await requestJson<Contact[]>("/contacts", { method: "GET" }, token);
  return raw.map(normalizeContact);
}

export async function createContact(
  payload: ContactCreatePayload,
  token?: string
): Promise<Contact> {
  const raw = await requestJson<Contact>(
    "/contacts",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token
  );
  return normalizeContact(raw);
}

export async function deleteContact(contactId: string, token?: string): Promise<void> {
  return requestJson<void>(`/contacts/${contactId}`, { method: "DELETE" }, token);
}

export async function fetchLLMCredentials(token?: string): Promise<LLMCredential[]> {
  return requestJson<LLMCredential[]>("/settings/llm-credentials", { method: "GET" }, token);
}

export async function registerLLMCredential(
  payload: LLMCredentialCreatePayload,
  token?: string
): Promise<LLMCredential> {
  return requestJson<LLMCredential>(
    "/settings/llm-credentials",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token
  );
}

export async function revokeLLMCredential(credentialId: string, token?: string): Promise<void> {
  return requestJson<void>(
    `/settings/llm-credentials/${credentialId}`,
    { method: "DELETE" },
    token
  );
}

export async function summarizeInteraction(
  payload: InteractionSummarizePayload,
  token?: string
): Promise<InteractionSummarizeResponse> {
  return requestJson<InteractionSummarizeResponse>(
    "/ai/copilot/summarize-interaction",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token
  );
}

export async function fetchAIProposals(token?: string): Promise<AIProposal[]> {
  return requestJson<AIProposal[]>("/ai/proposals", { method: "GET" }, token);
}

export async function approveAIProposal(proposalId: string, token?: string): Promise<AIProposal> {
  return requestJson<AIProposal>(
    `/ai/proposals/${proposalId}/approve`,
    { method: "POST" },
    token
  );
}

export async function rejectAIProposal(
  proposalId: string,
  rejectionReason: string,
  token?: string
): Promise<AIProposal> {
  return requestJson<AIProposal>(
    `/ai/proposals/${proposalId}/reject`,
    {
      method: "POST",
      body: JSON.stringify({ rejection_reason: rejectionReason }),
    },
    token
  );
}

export async function runSemanticSearch(
  query: string,
  limit = 5,
  token?: string
): Promise<SemanticSearchResponse> {
  return requestJson<SemanticSearchResponse>(
    "/ai/copilot/semantic-search",
    {
      method: "POST",
      body: JSON.stringify({ query, limit }),
    },
    token
  );
}
