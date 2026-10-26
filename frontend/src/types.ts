export type Gender = "女" | "男" | "其他" | "不设定";

export interface Persona {
  schema_version?: number;
  name: string;
  identity: string;
  gender: Gender;
  age?: number | null;
  personality: string[];
  speaking_style: string;
  background: string;
  tags: string[];
  relationship?: string;
  example_openers?: string[];
}

export interface Companion {
  id: number;
  name: string;
  current_version: number;
  persona: Persona;
  memory_enabled: boolean;
  avatar?: string | null;
  derived_from?: number | null;
  created_at: string;
  updated_at: string;
}

export interface Template {
  key: string;
  category: string;
  name: string;
  tagline: string;
  persona: Persona;
}

export interface Session {
  id: number;
  companion_id: number;
  title: string;
  state: string;
  created_at: string;
  last_message_at?: string | null;
}

export interface Message {
  id: number;
  session_id: number;
  seq: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface Memory {
  id: number;
  type: string;
  type_label: string;
  content: string;
  confidence: number;
  source_session_id?: number | null;
  quote?: string | null;
  created_at: string;
  last_used_at?: string | null;
}

export interface Summary {
  session_id: number;
  summary?: string | null;
  covered_seq: number;
  updated_at?: string | null;
}

export interface Latest {
  session_id?: number | null;
  message_id?: number | null;
  role?: "user" | "assistant" | null;
  content?: string | null;
  created_at?: string | null;
}

export interface Scenario {
  key: string;
  title: string;
  category: string;
  role: string;
  goal: string;
  difficulty: number;
  max_turns: number;
  opening: string;
  tips: string;
}

export interface Review {
  summary?: string;
  scores?: Record<string, number>;
  highlights?: string[];
  improvements?: string[];
  sample_lines?: string[];
}

export interface Run {
  id: number;
  companion_id: number;
  scenario_key: string;
  session_id: number;
  status: string;
  max_turns: number;
  turns_played: number;
  review?: Review | null;
  created_at: string;
  finished_at?: string | null;
}

export interface RunStart extends Run {
  scenario: Scenario;
  opening: string;
}

export interface ModelInfo {
  key: string;
  provider_key: string;
  model_name: string;
  display_name: string;
  context_window: number;
  max_output: number;
  supports: string[];
  embedding_dim?: number | null;
  notes?: string;
}

export interface Provider {
  key: string;
  name: string;
  kind: string;
  base_url: string;
  scope: string;
  has_key: boolean;
  masked_key: string;
  allows_private: boolean;
  models: ModelInfo[];
}

export interface UsageTotals {
  calls: number;
  ok_calls: number;
  input_tokens: number;
  output_tokens: number;
  cache_hit_tokens: number;
  cache_miss_tokens: number;
  hit_ratio: number;
  cost_cny: number;
}

export interface ModelUsage {
  model_key: string;
  totals: UsageTotals;
  avg_first_token_ms?: number | null;
}

export interface UsageSummary {
  days: number;
  totals: UsageTotals;
  by_model: ModelUsage[];
  daily: { day: string; calls: number; cost_cny: number }[];
}

export interface Quota {
  day: string;
  used: number;
  limit: number;
  remaining: number;
  enforced: boolean;
}

export interface Account {
  user_id: string;
  account_id?: number | null;
  phone_masked?: string | null;
  role?: string;
  created_at?: string | null;
}

export interface ModelDefaults {
  model: string;
  temperature: number;
  max_tokens: number;
  top_p?: number;
  thinking: boolean;
  json_mode?: boolean;
}

export interface AdminSettings {
  quota: { enforced: boolean; daily_limit: number };
  model_defaults: Record<string, ModelDefaults>;
}

export interface AdminSettingsResponse {
  settings: AdminSettings;
  models: { key: string; display_name: string; provider: string }[];
}

export interface SmsCodeResponse {
  ok: boolean;
  expires_in: number;
  debug_code?: string | null;
}

export interface LoginResponse {
  account_id: number;
  phone_masked: string;
  expires_at: string;
}


export interface UserProfile {
  nickname: string;
  identity: string;
  age?: number | null;
  gender: string;
  city: string;
  background: string;
}

export interface CompanionUserProfile {
  companion_id: number;
  nickname?: string | null;
  identity?: string | null;
  age?: number | null;
  gender?: string | null;
  city?: string | null;
  background?: string | null;
  effective: UserProfile;
}

export interface ProviderSetting {
  provider_key: string;
  has_key: boolean;
  masked_key: string;
  base_url?: string | null;
  enabled: boolean;
}

export interface DiscoveredModel {
  id: string;
  owned_by: string;
}
