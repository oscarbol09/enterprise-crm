export interface UserInfo {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string;
  role: "admin" | "sales_manager" | "sales_rep" | "readonly" | string;
  tenant_name?: string | null;
  tenant_slug?: string | null;
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token: string;
  user: UserInfo;
}

export interface LoginPayload {
  email: string;
  password: string;
  tenant_slug?: string;
}

export interface RegisterWorkspacePayload {
  tenant_name: string;
  tenant_slug: string;
  admin_full_name: string;
  admin_email: string;
  password: string;
}

export interface Account {
  id: string;
  tenant_id: string;
  parent_account_id?: string | null;
  name: string;
  industry?: string | null;
  website?: string | null;
  annual_revenue?: number | null;
  employee_count?: number | null;
  owner_id: string;
  metadata?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface AccountCreatePayload {
  name: string;
  industry?: string;
  website?: string;
  annual_revenue?: number;
  employee_count?: number;
  parent_account_id?: string;
  metadata?: Record<string, unknown>;
}

export interface AccountUpdatePayload {
  name?: string;
  industry?: string;
  website?: string;
  annual_revenue?: number;
  employee_count?: number;
  metadata?: Record<string, unknown>;
}

export interface CompanyAffiliation {
  id: string;
  tenant_id: string;
  account_id: string;
  contact_id: string;
  role_title?: string | null;
  department?: string | null;
  is_primary: boolean;
  is_active: boolean;
  started_at?: string | null;
  ended_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CompanyAffiliationCreatePayload {
  contact_id: string;
  role_title?: string;
  department?: string;
  is_primary?: boolean;
}

export interface Deal {
  id: string;
  tenant_id: string;
  pipeline_id: string;
  stage_id: string;
  account_id?: string | null;
  contact_id?: string | null;
  owner_id: string;
  title: string;
  amount: number;
  currency: string;
  exchange_rate_to_usd?: number;
  normalized_amount_usd?: number;
  expected_close_date?: string | null;
  forecast_category: "pipeline" | "best_case" | "commit" | "closed" | "omitted";
  win_probability: number;
  is_won: boolean;
  is_lost: boolean;
  loss_reason?: string | null;
  closed_at?: string | null;
  metadata?: Record<string, unknown>;
  stage_entered_at?: string | null;
  last_interaction_at?: string | null;
  close_date_push_count?: number;
  created_at: string;
  updated_at: string;
}

export interface DealPlaybookResponse {
  deal_id: string;
  stage_name: string;
  normalized_amount_usd: number;
  recommended_actions: string[];
  follow_up_email_subject: string;
  follow_up_email_body: string;
}

export interface TaskPruneZombiesResponse {
  pruned_count: number;
  pruned_task_ids: string[];
}

export interface DealCreatePayload {
  title: string;
  stage_id: string;
  amount: number;
  currency?: string;
  exchange_rate_to_usd?: number;
  account_id?: string;
  contact_id?: string;
  expected_close_date?: string;
  metadata?: Record<string, unknown>;
}

export interface DealUpdatePayload {
  title?: string;
  amount?: number;
  currency?: string;
  exchange_rate_to_usd?: number;
  account_id?: string;
  contact_id?: string;
  expected_close_date?: string;
  metadata?: Record<string, unknown>;
}

export interface DealParticipant {
  id: string;
  tenant_id: string;
  deal_id: string;
  contact_id: string;
  buying_role:
    | "champion"
    | "economic_buyer"
    | "technical_evaluator"
    | "legal_blocker"
    | "executive_sponsor"
    | "stakeholder"
    | string;
  is_primary: boolean;
  notes?: string | null;
  created_at: string;
}

export interface DealParticipantCreatePayload {
  contact_id: string;
  buying_role:
    | "champion"
    | "economic_buyer"
    | "technical_evaluator"
    | "legal_blocker"
    | "executive_sponsor"
    | "stakeholder";
  is_primary?: boolean;
  notes?: string;
}

export interface DealStageHistoryItem {
  id: string;
  tenant_id: string;
  deal_id: string;
  from_stage_id?: string | null;
  to_stage_id: string;
  amount_at_transition: number;
  win_probability_at_transition: number;
  expected_close_date_at_transition?: string | null;
  changed_by?: string | null;
  entered_at: string;
  exited_at?: string | null;
  duration_seconds?: number | null;
}

export interface PipelineStage {
  id: string;
  pipeline_id: string;
  name: string;
  position: number;
  default_probability: number;
  is_closed_won: boolean;
  is_closed_lost: boolean;
}

export interface MoveDealStagePayload {
  new_stage_id: string;
  loss_reason?: string;
  loss_category?: "price" | "missing_feature" | "competitor" | "ghosting" | "timing" | "other";
  competitor_name?: string;
  missing_feature_tag?: string;
  notes?: string;
}

export interface StageGateFieldRequirement {
  field_key: string;
  label: string;
  field_type: "text" | "number" | "boolean" | "date" | "select" | "multi_select" | string;
  allowed_values?: string[];
}

export interface InteractionItem {
  id: string;
  tenant_id: string;
  user_id: string;
  contact_id?: string | null;
  account_id?: string | null;
  deal_id?: string | null;
  type: string;
  direction: string;
  subject: string;
  content_body: string;
  occurred_at: string;
  created_at: string;
}

export interface InteractionCreatePayload {
  contact_id?: string;
  account_id?: string;
  deal_id?: string;
  type?: "email" | "call" | "meeting" | "note" | "task_completed" | "stage_change";
  direction?: "inbound" | "outbound" | "internal";
  subject: string;
  content_body: string;
  metadata?: Record<string, unknown>;
}

export interface CursorPaginatedTimeline {
  items: InteractionItem[];
  next_cursor?: string | null;
}

export interface Contact {
  id: string;
  tenant_id: string;
  account_id?: string | null;
  owner_id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string | null;
  job_title?: string | null;
  lead_score: number;
  lifecycle_stage: string;
  metadata?: Record<string, unknown>;
  merged_into_id?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContactCreatePayload {
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  job_title?: string;
  account_id?: string;
  lifecycle_stage?: string;
  metadata?: Record<string, unknown>;
}

export interface ContactUpdatePayload {
  first_name?: string;
  last_name?: string;
  phone?: string;
  job_title?: string;
  account_id?: string;
  lifecycle_stage?: string;
  lead_score?: number;
  metadata?: Record<string, unknown>;
}

export interface TaskItem {
  id: string;
  tenant_id: string;
  assigned_to: string;
  created_by: string;
  contact_id?: string | null;
  deal_id?: string | null;
  title: string;
  description?: string | null;
  priority: "low" | "medium" | "high" | "urgent" | string;
  status: "pending" | "in_progress" | "completed" | "cancelled" | string;
  due_date: string;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface TaskCreatePayload {
  title: string;
  description?: string;
  priority?: "low" | "medium" | "high" | "urgent";
  due_date: string;
  contact_id?: string;
  deal_id?: string;
  assigned_to?: string;
}

export interface TaskUpdatePayload {
  status?: "pending" | "in_progress" | "completed" | "cancelled";
  priority?: "low" | "medium" | "high" | "urgent";
  title?: string;
}

export interface LLMCredential {
  id: string;
  tenant_id: string;
  provider: "gemini" | "claude" | "openai";
  key_last_four: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface LLMCredentialCreatePayload {
  provider: "gemini" | "claude" | "openai";
  raw_api_key: string;
}

export interface ActionProposalItem {
  action_type: string;
  summary: string;
  suggested_due_date?: string | null;
  confidence_score: number;
  requires_human_approval: boolean;
  target_stage_name?: string | null;
}

export interface InteractionSummarizePayload {
  contact_id: string;
  deal_id?: string;
  raw_notes_or_transcript: string;
  interaction_type: "call" | "meeting" | "email" | "note";
}

export interface InteractionSummarizeResponse {
  executive_summary: string;
  key_commitments_identified: string[];
  detected_sentiment: string;
  suggested_next_step: string;
  action_proposals: ActionProposalItem[];
  proposal_id?: string | null;
  proposal_ids: string[];
  ai_audit_id: string;
  model_used: string;
  key_source: string;
  is_stub: boolean;
}

export interface AIProposal {
  id: string;
  tenant_id: string;
  agent_name: string;
  action_type: string;
  target_entity_type: string;
  target_entity_id: string;
  proposed_payload: Record<string, unknown>;
  reasoning_summary: string;
  status: "pending_review" | "approved" | "rejected" | "expired" | string;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  rejection_reason?: string | null;
  created_at: string;
}

export interface SemanticSearchResult {
  entity_type: string;
  entity_id: string;
  text_content: string;
  similarity: number;
}

export interface SemanticSearchResponse {
  results: SemanticSearchResult[];
  source: string;
}

// ============================================================================
// REVENUE INTELLIGENCE, ATTRIBUTION & DATA TRANSFER TYPES
// ============================================================================
export interface ForecastPeriodBreakdown {
  period: string;
  closed_won_usd: number;
  commit_usd: number;
  best_case_usd: number;
  pipeline_usd: number;
  weighted_open_usd: number;
  deal_count: number;
}

export interface AtRiskDealItem {
  deal_id: string;
  title: string;
  normalized_amount_usd: number;
  expected_close_date?: string | null;
  close_date_push_count: number;
  days_in_stage: number;
  risk_reasons: string[];
}

export interface ForecastAnalytics {
  closed_won_usd: number;
  closed_lost_usd: number;
  open_pipeline_usd: number;
  commit_usd: number;
  best_case_usd: number;
  weighted_open_usd: number;
  total_projected_usd: number;
  open_deals_count: number;
  won_deals_count: number;
  lost_deals_count: number;
  win_rate: number;
  avg_won_deal_usd: number;
  avg_sales_cycle_days: number;
  sales_velocity_usd_per_day: number;
  quota_usd?: number | null;
  pipeline_coverage_ratio?: number | null;
  usd_at_risk: number;
  at_risk_deals: AtRiskDealItem[];
  by_period: ForecastPeriodBreakdown[];
}

export interface FunnelStageMetric {
  stage_id: string;
  stage_name: string;
  position: number;
  is_closed_won: boolean;
  is_closed_lost: boolean;
  deals_entered: number;
  current_open_deals: number;
  conversion_to_next_pct: number;
  avg_dwell_days: number;
}

export interface FunnelAnalytics {
  stages: FunnelStageMetric[];
  bottleneck_stage_name?: string | null;
}

export interface ChannelAttributionMetric {
  source_channel: string;
  leads_count: number;
  opportunities_count: number;
  won_deals_count: number;
  win_rate: number;
  pipeline_generated_usd: number;
  closed_won_revenue_usd: number;
  avg_deal_size_usd: number;
  revenue_share_pct: number;
}

export interface AttributionAnalytics {
  total_leads: number;
  total_closed_won_usd: number;
  channels: ChannelAttributionMetric[];
}

export interface CSVImportPayload {
  csv_content: string;
  dry_run: boolean;
  dedupe_strategy: "skip" | "update";
  column_map?: Record<string, string>;
}

export interface CSVImportRowError {
  row: number;
  email?: string | null;
  reason: string;
}

export interface CSVImportResponse {
  dry_run: boolean;
  import_batch_id?: string | null;
  total_rows: number;
  would_create: number;
  would_update: number;
  would_skip: number;
  would_create_deals?: number;
  created_count: number;
  updated_count: number;
  skipped_count: number;
  deals_created_count?: number;
  quarantined_count: number;
  accounts_auto_created: number;
  detected_columns: Record<string, string>;
  errors: CSVImportRowError[];
}

export interface ImportBatchRollbackResponse {
  batch_id: string;
  status: string;
  reverted_accounts: number;
  reverted_contacts: number;
  reverted_deals: number;
}

export interface PipelineSnapshotResponse {
  snapshot_date: string;
  captured_deals: number;
  total_open_usd: number;
}

export interface WaterfallBridge {
  from_date: string;
  to_date: string;
  starting_open_usd: number;
  new_deals_usd: number;
  expansion_usd: number;
  contraction_usd: number;
  closed_won_usd: number;
  closed_lost_usd: number;
  ending_open_usd: number;
  slipped_deals_count: number;
}

export interface WinLossCategoryBucket {
  category: string;
  lost_deals_count: number;
  lost_usd: number;
}

export interface WinLossNamedBucket {
  name: string;
  lost_deals_count: number;
  lost_usd: number;
}

export interface WinLossAnalytics {
  total_lost_deals: number;
  total_lost_usd: number;
  by_category: WinLossCategoryBucket[];
  by_competitor: WinLossNamedBucket[];
  by_missing_feature: WinLossNamedBucket[];
}
