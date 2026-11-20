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
  expected_close_date?: string | null;
  forecast_category: "pipeline" | "best_case" | "commit" | "closed" | "omitted";
  win_probability: number;
  is_won: boolean;
  is_lost: boolean;
  loss_reason?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DealCreatePayload {
  title: string;
  stage_id: string;
  amount: number;
  currency?: string;
  contact_id?: string;
  expected_close_date?: string;
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
  notes?: string;
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
