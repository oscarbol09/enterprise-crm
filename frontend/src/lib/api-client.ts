import {
  Account,
  AccountCreatePayload,
  AccountUpdatePayload,
  AIProposal,
  AttributionAnalytics,
  AuthTokenResponse,
  CompanyAffiliation,
  CompanyAffiliationCreatePayload,
  Contact,
  ContactCreatePayload,
  ContactUpdatePayload,
  CSVImportPayload,
  CSVImportResponse,
  CursorPaginatedTimeline,
  Deal,
  DealCreatePayload,
  DealParticipant,
  DealParticipantCreatePayload,
  DealPlaybookResponse,
  DealStageHistoryItem,
  DealUpdatePayload,
  ForecastAnalytics,
  FunnelAnalytics,
  ImportBatchRollbackResponse,
  InteractionCreatePayload,
  InteractionItem,
  InteractionSummarizePayload,
  InteractionSummarizeResponse,
  LLMCredential,
  LLMCredentialCreatePayload,
  LoginPayload,
  MoveDealStagePayload,
  PipelineSnapshotResponse,
  PipelineStage,
  RegisterWorkspacePayload,
  SemanticSearchResponse,
  StageGateFieldRequirement,
  TaskCreatePayload,
  TaskItem,
  TaskPruneZombiesResponse,
  TaskUpdatePayload,
  UserInfo,
  WaterfallBridge,
  WinLossAnalytics,
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
  stageGateFields?: StageGateFieldRequirement[];

  constructor(
    status: number,
    message: string,
    data?: unknown,
    stageGateFields?: StageGateFieldRequirement[]
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
    this.stageGateFields = stageGateFields;
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
  const amount = Number(raw.amount);
  const fx =
    raw.exchange_rate_to_usd !== undefined && raw.exchange_rate_to_usd !== null
      ? Number(raw.exchange_rate_to_usd)
      : 1;
  const normalizedUsd =
    raw.normalized_amount_usd !== undefined && raw.normalized_amount_usd !== null
      ? Number(raw.normalized_amount_usd)
      : Number((amount * fx).toFixed(2));
  return {
    ...raw,
    amount,
    exchange_rate_to_usd: fx,
    normalized_amount_usd: normalizedUsd,
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

function normalizeAccount(raw: Account): Account {
  return {
    ...raw,
    annual_revenue:
      raw.annual_revenue !== null && raw.annual_revenue !== undefined
        ? Number(raw.annual_revenue)
        : null,
  };
}

function normalizeStageHistory(raw: DealStageHistoryItem): DealStageHistoryItem {
  return {
    ...raw,
    amount_at_transition: Number(raw.amount_at_transition),
    win_probability_at_transition: Number(raw.win_probability_at_transition),
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
    let stageGateFields: StageGateFieldRequirement[] | undefined;
    const rawGateHeader = response.headers.get("X-Stage-Gate-Fields");
    if (rawGateHeader) {
      try {
        const parsed = JSON.parse(rawGateHeader) as StageGateFieldRequirement[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          stageGateFields = parsed;
        }
      } catch {
        stageGateFields = undefined;
      }
    }
    throw new ApiError(
      response.status,
      errorJson.detail || `Error en solicitud a ${path} (HTTP ${response.status})`,
      errorJson,
      stageGateFields
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

// ============================================================================
// DEALS & PIPELINE API
// ============================================================================
export async function fetchDeals(token?: string, q?: string): Promise<Deal[]> {
  const qs = q && q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
  const raw = await requestJson<Deal[]>(`/deals${qs}`, { method: "GET" }, token);
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

export async function updateDeal(
  dealId: string,
  payload: DealUpdatePayload,
  token?: string
): Promise<Deal> {
  const raw = await requestJson<Deal>(
    `/deals/${dealId}`,
    {
      method: "PATCH",
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

export async function fetchDealParticipants(
  dealId: string,
  token?: string
): Promise<DealParticipant[]> {
  return requestJson<DealParticipant[]>(`/deals/${dealId}/participants`, { method: "GET" }, token);
}

export async function addDealParticipant(
  dealId: string,
  payload: DealParticipantCreatePayload,
  token?: string
): Promise<DealParticipant> {
  return requestJson<DealParticipant>(
    `/deals/${dealId}/participants`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token
  );
}

export async function fetchDealStageHistory(
  dealId: string,
  token?: string
): Promise<DealStageHistoryItem[]> {
  const raw = await requestJson<DealStageHistoryItem[]>(
    `/deals/${dealId}/stage-history`,
    { method: "GET" },
    token
  );
  return raw.map(normalizeStageHistory);
}

export async function fetchDealPlaybook(
  dealId: string,
  token?: string
): Promise<DealPlaybookResponse> {
  const raw = await requestJson<DealPlaybookResponse>(
    `/deals/${dealId}/playbook`,
    { method: "GET" },
    token
  );
  return {
    ...raw,
    normalized_amount_usd: Number(raw.normalized_amount_usd),
  };
}

// ============================================================================
// CONTACTS API
// ============================================================================
export interface FetchContactsFilter {
  q?: string;
  lifecycle_stage?: string;
  cf_key?: string;
  cf_value?: string;
}

export async function fetchContacts(
  token?: string,
  filters?: FetchContactsFilter
): Promise<Contact[]> {
  const params = new URLSearchParams();
  if (filters?.q && filters.q.trim()) params.set("q", filters.q.trim());
  if (filters?.lifecycle_stage && filters.lifecycle_stage !== "all") {
    params.set("lifecycle_stage", filters.lifecycle_stage);
  }
  if (filters?.cf_key) params.set("cf_key", filters.cf_key);
  if (filters?.cf_value) params.set("cf_value", filters.cf_value);
  const qs = params.toString();
  const path = qs ? `/contacts?${qs}` : "/contacts";
  const raw = await requestJson<Contact[]>(path, { method: "GET" }, token);
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

export async function updateContact(
  contactId: string,
  payload: ContactUpdatePayload,
  token?: string
): Promise<Contact> {
  const raw = await requestJson<Contact>(
    `/contacts/${contactId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    token
  );
  return normalizeContact(raw);
}

export async function deleteContact(contactId: string, token?: string): Promise<void> {
  return requestJson<void>(`/contacts/${contactId}`, { method: "DELETE" }, token);
}

export async function restoreContact(contactId: string, token?: string): Promise<Contact> {
  const raw = await requestJson<Contact>(
    `/contacts/${contactId}/restore`,
    { method: "POST", body: JSON.stringify({}) },
    token
  );
  return normalizeContact(raw);
}

export async function mergeContacts(
  targetContactId: string,
  sourceContactId: string,
  token?: string
): Promise<Contact> {
  const raw = await requestJson<Contact>(
    `/contacts/${targetContactId}/merge`,
    {
      method: "POST",
      body: JSON.stringify({ source_contact_id: sourceContactId }),
    },
    token
  );
  return normalizeContact(raw);
}

export async function fetchContactTimeline(
  contactId: string,
  cursor?: string,
  token?: string
): Promise<CursorPaginatedTimeline> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return requestJson<CursorPaginatedTimeline>(
    `/contacts/${contactId}/timeline${qs}`,
    { method: "GET" },
    token
  );
}

export async function fetchContactAffiliations(
  contactId: string,
  token?: string
): Promise<CompanyAffiliation[]> {
  return requestJson<CompanyAffiliation[]>(
    `/contacts/${contactId}/affiliations`,
    { method: "GET" },
    token
  );
}

// ============================================================================
// ACCOUNTS & TASKS & INTERACTIONS API
// ============================================================================
export async function fetchAccounts(token?: string, q?: string): Promise<Account[]> {
  const qs = q && q.trim() ? `?q=${encodeURIComponent(q.trim())}` : "";
  const raw = await requestJson<Account[]>(`/accounts${qs}`, { method: "GET" }, token);
  return raw.map(normalizeAccount);
}

export async function createAccount(
  payload: AccountCreatePayload,
  token?: string
): Promise<Account> {
  const raw = await requestJson<Account>(
    "/accounts",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token
  );
  return normalizeAccount(raw);
}

export async function updateAccount(
  accountId: string,
  payload: AccountUpdatePayload,
  token?: string
): Promise<Account> {
  const raw = await requestJson<Account>(
    `/accounts/${accountId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    token
  );
  return normalizeAccount(raw);
}

export async function mergeAccounts(
  targetAccountId: string,
  sourceAccountId: string,
  token?: string
): Promise<Account> {
  const raw = await requestJson<Account>(
    `/accounts/${targetAccountId}/merge`,
    {
      method: "POST",
      body: JSON.stringify({ source_account_id: sourceAccountId }),
    },
    token
  );
  return normalizeAccount(raw);
}

export async function fetchAccountTimeline(
  accountId: string,
  cursor?: string,
  token?: string
): Promise<CursorPaginatedTimeline> {
  const qs = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return requestJson<CursorPaginatedTimeline>(
    `/accounts/${accountId}/timeline${qs}`,
    { method: "GET" },
    token
  );
}

export async function fetchAccountAffiliations(
  accountId: string,
  token?: string
): Promise<CompanyAffiliation[]> {
  return requestJson<CompanyAffiliation[]>(
    `/accounts/${accountId}/affiliations`,
    { method: "GET" },
    token
  );
}

export async function createAccountAffiliation(
  accountId: string,
  payload: CompanyAffiliationCreatePayload,
  token?: string
): Promise<CompanyAffiliation> {
  return requestJson<CompanyAffiliation>(
    `/accounts/${accountId}/affiliations`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token
  );
}

export async function createInteraction(
  payload: InteractionCreatePayload,
  token?: string
): Promise<InteractionItem> {
  return requestJson<InteractionItem>(
    "/interactions",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token
  );
}

export async function fetchTasks(token?: string): Promise<TaskItem[]> {
  return requestJson<TaskItem[]>("/tasks", { method: "GET" }, token);
}

export async function createTask(payload: TaskCreatePayload, token?: string): Promise<TaskItem> {
  return requestJson<TaskItem>(
    "/tasks",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token
  );
}

export async function updateTask(
  taskId: string,
  payload: TaskUpdatePayload,
  token?: string
): Promise<TaskItem> {
  return requestJson<TaskItem>(
    `/tasks/${taskId}`,
    {
      method: "PATCH",
      body: JSON.stringify(payload),
    },
    token
  );
}

export async function pruneZombieTasks(
  maxOverdueDays = 14,
  token?: string
): Promise<TaskPruneZombiesResponse> {
  return requestJson<TaskPruneZombiesResponse>(
    "/tasks/prune-zombies",
    {
      method: "POST",
      body: JSON.stringify({ max_overdue_days: maxOverdueDays }),
    },
    token
  );
}

// ============================================================================
// BYOK & AI COPILOT API
// ============================================================================
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

// ============================================================================
// REVENUE INTELLIGENCE, ATTRIBUTION & DATA TRANSFER API
// ============================================================================
export async function fetchForecastAnalytics(
  quotaUsd?: number,
  staleDays = 14,
  token?: string
): Promise<ForecastAnalytics> {
  const params = new URLSearchParams();
  if (quotaUsd && quotaUsd > 0) params.set("quota_usd", String(quotaUsd));
  if (staleDays > 0) params.set("stale_days", String(staleDays));
  const qs = params.toString();
  const raw = await requestJson<ForecastAnalytics>(
    qs ? `/analytics/forecast?${qs}` : "/analytics/forecast",
    { method: "GET" },
    token
  );
  return {
    ...raw,
    closed_won_usd: Number(raw.closed_won_usd),
    closed_lost_usd: Number(raw.closed_lost_usd),
    open_pipeline_usd: Number(raw.open_pipeline_usd),
    commit_usd: Number(raw.commit_usd),
    best_case_usd: Number(raw.best_case_usd),
    weighted_open_usd: Number(raw.weighted_open_usd),
    total_projected_usd: Number(raw.total_projected_usd),
    win_rate: Number(raw.win_rate),
    avg_won_deal_usd: Number(raw.avg_won_deal_usd),
    avg_sales_cycle_days: Number(raw.avg_sales_cycle_days),
    sales_velocity_usd_per_day: Number(raw.sales_velocity_usd_per_day),
    quota_usd: raw.quota_usd !== null && raw.quota_usd !== undefined ? Number(raw.quota_usd) : null,
    pipeline_coverage_ratio:
      raw.pipeline_coverage_ratio !== null && raw.pipeline_coverage_ratio !== undefined
        ? Number(raw.pipeline_coverage_ratio)
        : null,
    usd_at_risk: Number(raw.usd_at_risk),
    at_risk_deals: raw.at_risk_deals.map((d) => ({
      ...d,
      normalized_amount_usd: Number(d.normalized_amount_usd),
    })),
    by_period: raw.by_period.map((p) => ({
      ...p,
      closed_won_usd: Number(p.closed_won_usd),
      commit_usd: Number(p.commit_usd),
      best_case_usd: Number(p.best_case_usd),
      pipeline_usd: Number(p.pipeline_usd),
      weighted_open_usd: Number(p.weighted_open_usd),
    })),
  };
}

export async function fetchFunnelAnalytics(token?: string): Promise<FunnelAnalytics> {
  const raw = await requestJson<FunnelAnalytics>("/analytics/funnel", { method: "GET" }, token);
  return {
    ...raw,
    stages: raw.stages.map((s) => ({
      ...s,
      conversion_to_next_pct: Number(s.conversion_to_next_pct),
      avg_dwell_days: Number(s.avg_dwell_days),
    })),
  };
}

export async function fetchAttributionAnalytics(token?: string): Promise<AttributionAnalytics> {
  const raw = await requestJson<AttributionAnalytics>(
    "/analytics/attribution",
    { method: "GET" },
    token
  );
  return {
    ...raw,
    total_closed_won_usd: Number(raw.total_closed_won_usd),
    channels: raw.channels.map((c) => ({
      ...c,
      win_rate: Number(c.win_rate),
      pipeline_generated_usd: Number(c.pipeline_generated_usd),
      closed_won_revenue_usd: Number(c.closed_won_revenue_usd),
      avg_deal_size_usd: Number(c.avg_deal_size_usd),
      revenue_share_pct: Number(c.revenue_share_pct),
    })),
  };
}

export async function importContactsCsv(
  payload: CSVImportPayload,
  token?: string
): Promise<CSVImportResponse> {
  return requestJson<CSVImportResponse>(
    "/data/contacts/import",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token
  );
}

export async function rollbackImportBatch(
  batchId: string,
  token?: string
): Promise<ImportBatchRollbackResponse> {
  return requestJson<ImportBatchRollbackResponse>(
    `/data/imports/${batchId}/rollback`,
    { method: "POST" },
    token
  );
}

export async function capturePipelineSnapshot(
  snapshotDate?: string,
  token?: string
): Promise<PipelineSnapshotResponse> {
  const raw = await requestJson<PipelineSnapshotResponse>(
    "/analytics/snapshots",
    {
      method: "POST",
      body: JSON.stringify(snapshotDate ? { snapshot_date: snapshotDate } : {}),
    },
    token
  );
  return {
    ...raw,
    total_open_usd: Number(raw.total_open_usd),
  };
}

export async function fetchWaterfallBridge(
  fromDate?: string,
  toDate?: string,
  token?: string
): Promise<WaterfallBridge> {
  const params = new URLSearchParams();
  if (fromDate) params.set("from_date", fromDate);
  if (toDate) params.set("to_date", toDate);
  const qs = params.toString();
  const raw = await requestJson<WaterfallBridge>(
    qs ? `/analytics/waterfall?${qs}` : "/analytics/waterfall",
    { method: "GET" },
    token
  );
  return {
    ...raw,
    starting_open_usd: Number(raw.starting_open_usd),
    new_deals_usd: Number(raw.new_deals_usd),
    expansion_usd: Number(raw.expansion_usd),
    contraction_usd: Number(raw.contraction_usd),
    closed_won_usd: Number(raw.closed_won_usd),
    closed_lost_usd: Number(raw.closed_lost_usd),
    ending_open_usd: Number(raw.ending_open_usd),
  };
}

export async function fetchWinLossAnalytics(token?: string): Promise<WinLossAnalytics> {
  const raw = await requestJson<WinLossAnalytics>(
    "/analytics/win-loss",
    { method: "GET" },
    token
  );
  return {
    ...raw,
    total_lost_usd: Number(raw.total_lost_usd),
    by_category: raw.by_category.map((b) => ({ ...b, lost_usd: Number(b.lost_usd) })),
    by_competitor: raw.by_competitor.map((b) => ({ ...b, lost_usd: Number(b.lost_usd) })),
    by_missing_feature: raw.by_missing_feature.map((b) => ({ ...b, lost_usd: Number(b.lost_usd) })),
  };
}

export async function exportEntityCsv(
  entity: "contacts" | "deals" | "accounts",
  token?: string
): Promise<string> {
  const url = `${API_BASE_URL}/data/export/${entity}`;
  const response = await fetch(url, {
    method: "GET",
    credentials: "include",
    headers: buildHeaders(token),
  });
  if (!response.ok) {
    throw new ApiError(
      response.status,
      `Error al exportar ${entity} (HTTP ${response.status})`
    );
  }
  return response.text();
}
