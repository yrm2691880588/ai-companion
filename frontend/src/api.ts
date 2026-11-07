import { createParser } from "eventsource-parser";
import { apiUrl, authHeaders } from "./lib/client";
import type {
  Account,
  AdminSettings,
  AdminSettingsResponse,
  SystemInfo,
  UpdateCheck,
  Companion,
  CompanionUserProfile,
  DiscoveredModel,
  Latest,
  LoginResponse,
  Memory,
  Message,
  Persona,
  PersonaVersion,
  Provider,
  ProviderSetting,
  Quota,
  Run,
  RunStart,
  Scenario,
  Session,
  SmsCodeResponse,
  Summary,
  Template,
  UsageSummary,
  VoiceOption,
  VoiceProvider,
  VoiceSynthesis,
  UserProfile,
} from "./lib/types";

export { getUserId, setUserId, getDeviceId, apiUrl } from "./lib/client";

export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as {
      code?: string;
      message?: string;
    };
    throw new ApiError(body.code ?? String(response.status), body.message ?? response.statusText);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export interface StreamHandlers {
  onMeta?: (data: { session_id?: number; user_message_id?: number; trial_id?: string }) => void;
  onDelta?: (text: string) => void;
  onDone?: (data: {
    assistant_message_id: number;
    model?: string;
    input_tokens?: number;
    output_tokens?: number;
    memories?: string[];
  }) => void;
  onError?: (error: ApiError) => void;
}

/** 解析后端 SSE：event: xxx + data: {...}，块之间空行分隔。 */
export async function streamEvents(
  path: string,
  body: unknown,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(apiUrl(path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
      Accept: "text/event-stream",
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) {
    const payload = (await response.json().catch(() => ({}))) as {
      code?: string;
      message?: string;
    };
    throw new ApiError(payload.code ?? String(response.status), payload.message ?? "请求失败");
  }
  // 分块解析交给 eventsource-parser：它按规范处理跨块截断、多行 data 与注释行
  const parser = createParser({
    onEvent: (message) => dispatchEvent(message.event ?? "message", message.data, handlers),
  });
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    parser.feed(decoder.decode(value, { stream: true }));
  }
}

function dispatchEvent(event: string, data: string, handlers: StreamHandlers): void {
  if (!data) return;
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(data) as Record<string, unknown>;
  } catch {
    return;
  }
  if (event === "meta") handlers.onMeta?.(payload as never);
  else if (event === "delta") handlers.onDelta?.(String(payload.text ?? ""));
  else if (event === "done") handlers.onDone?.(payload as never);
  else if (event === "error") {
    handlers.onError?.(
      new ApiError(String(payload.code ?? "STREAM_ERROR"), String(payload.message ?? "生成失败")),
    );
  }
}

export const api = {
  async smsCode(phone: string): Promise<SmsCodeResponse> {
    return request<SmsCodeResponse>("/v1/auth/sms-code", {
      method: "POST",
      body: JSON.stringify({ phone }),
    });
  },
  async login(phone: string, code: string): Promise<LoginResponse> {
    return request<LoginResponse>("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ phone, code }),
    });
  },
  async logout(): Promise<void> {
    await request<{ ok: boolean }>("/v1/auth/logout", { method: "POST" });
  },
  async me(): Promise<Account> {
    return request<Account>("/v1/me");
  },
  async companions(signal?: AbortSignal): Promise<Companion[]> {
    return request<Companion[]>("/v1/companions", { signal });
  },
  async companion(id: number, signal?: AbortSignal): Promise<Companion> {
    return request<Companion>(`/v1/companions/${id}`, { signal });
  },
  async createCompanion(persona: Persona, name?: string): Promise<Companion> {
    return request<Companion>("/v1/companions", {
      method: "POST",
      body: JSON.stringify({ persona, name }),
    });
  },
  async trialChat(persona: Persona, content: string, trialId?: string): Promise<Response> {
    return fetch(apiUrl("/v1/trial/chat"), {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ persona, content, trial_id: trialId }),
    });
  },
  async importPersona(persona: Persona, name?: string): Promise<Companion> {
    return request<Companion>("/v1/personas/import", {
      method: "POST",
      body: JSON.stringify({ format: "ai-companion-persona", version: 1, persona, name }),
    });
  },
  async deriveCompanion(id: number, persona: Persona, name?: string): Promise<Companion> {
    return request<Companion>(`/v1/companions/${id}/derive`, {
      method: "POST",
      body: JSON.stringify({ persona, name }),
    });
  },
  async createFromTemplate(templateKey: string, name?: string): Promise<Companion> {
    return request<Companion>("/v1/companions/from-template", {
      method: "POST",
      body: JSON.stringify({ template_key: templateKey, name }),
    });
  },
  async deleteCompanion(id: number, confirmName: string): Promise<void> {
    await request<void>(
      `/v1/companions/${id}?confirm_name=${encodeURIComponent(confirmName)}`,
      { method: "DELETE" },
    );
  },
  /** 批量删除的前端提示规则：确认词与上限由后端给出，避免前端复制业务常量。 */
  async batchDeleteRules(signal?: AbortSignal): Promise<{ confirm: string; max_batch: number }> {
    return request<{ confirm: string; max_batch: number }>("/v1/companions/batch-delete/rules", {
      signal,
    });
  },
  /** 批量删除伴侣；确认词由后端规则接口给出，逐个返回成功与失败。 */
  async batchDeleteCompanions(
    ids: number[],
    confirm: string,
  ): Promise<{ deleted: number[]; failed: { id: number; reason: string }[] }> {
    return request<{ deleted: number[]; failed: { id: number; reason: string }[] }>(
      "/v1/companions/batch-delete",
      { method: "POST", body: JSON.stringify({ ids, confirm }) },
    );
  },
  async draftPersona(description: string): Promise<Persona> {
    const result = await request<{ persona: Persona }>("/v1/personas/draft", {
      method: "POST",
      body: JSON.stringify({ description }),
    });
    return result.persona;
  },
  /**
   * 让 AI 改写人设草稿里的某一个维度，返回建议值。
   * 不落库：用户点「采用」后由调用方写回表单。
   */
  async refinePersonaDimension(
    persona: Persona,
    dimension: string,
    hint: string | null,
  ): Promise<{ value: unknown; modelKey: string; costCny: number }> {
    const result = await request<{
      dimension: string;
      value: unknown;
      model_key: string;
      cost_cny: number;
    }>("/v1/personas/refine", {
      method: "POST",
      body: JSON.stringify({ persona, dimension, hint }),
    });
    return { value: result.value, modelKey: result.model_key, costCny: result.cost_cny };
  },
  async savePersona(id: number, persona: Persona): Promise<Companion> {
    return request<Companion>(`/v1/companions/${id}/persona`, {
      method: "PUT",
      body: JSON.stringify({ persona }),
    });
  },
  /** 人设的历史版本，最新的在前。 */
  async personaVersions(id: number, signal?: AbortSignal): Promise<PersonaVersion[]> {
    return request<PersonaVersion[]>(`/v1/companions/${id}/personas`, { signal });
  },
  /** 把某个历史版本还原成新版本（历史不丢）。 */
  async restorePersonaVersion(id: number, version: number): Promise<Companion> {
    return request<Companion>(`/v1/companions/${id}/personas/${version}/restore`, {
      method: "POST",
    });
  },
  async setAvatar(id: number, avatar: string | null): Promise<Companion> {
    return request<Companion>(`/v1/companions/${id}/avatar`, {
      method: "PUT",
      body: JSON.stringify({ avatar }),
    });
  },
  async templates(signal?: AbortSignal): Promise<Template[]> {
    return request<Template[]>("/v1/templates", { signal });
  },
  async sessions(companionId: number, signal?: AbortSignal): Promise<Session[]> {
    return request<Session[]>(`/v1/companions/${companionId}/sessions`, { signal });
  },
  async createSession(companionId: number, title = ""): Promise<Session> {
    return request<Session>(`/v1/companions/${companionId}/sessions`, {
      method: "POST",
      body: JSON.stringify({ title }),
    });
  },
  async openSession(sessionId: number): Promise<Message> {
    return request<Message>(`/v1/sessions/${sessionId}/opener`, { method: "POST" });
  },
  async renameSession(sessionId: number, title: string): Promise<Session> {
    return request<Session>(`/v1/sessions/${sessionId}`, {
      method: "PATCH",
      body: JSON.stringify({ title }),
    });
  },
  async deleteSession(sessionId: number): Promise<void> {
    await request<void>(`/v1/sessions/${sessionId}`, { method: "DELETE" });
  },
  async deleteMessage(messageId: number): Promise<void> {
    await request<void>(`/v1/messages/${messageId}`, { method: "DELETE" });
  },
  async latest(companionId: number, signal?: AbortSignal): Promise<Latest> {
    return request<Latest>(`/v1/companions/${companionId}/latest`, { signal });
  },
  async messages(sessionId: number, signal?: AbortSignal): Promise<Message[]> {
    return request<Message[]>(`/v1/sessions/${sessionId}/messages?limit=100`, { signal });
  },
  /**
   * 取某个 seq 之前的更早消息（升序返回）。
   * 后端按 seq 倒序取 limit 条再翻转，所以拿到的正好是「紧挨着的那一批」。
   */
  async olderMessages(
    sessionId: number,
    beforeSeq: number,
    limit = 30,
    signal?: AbortSignal,
  ): Promise<Message[]> {
    return request<Message[]>(
      `/v1/sessions/${sessionId}/messages?before_seq=${beforeSeq}&limit=${limit}`,
      { signal },
    );
  },
  async summary(sessionId: number, signal?: AbortSignal): Promise<Summary> {
    return request<Summary>(`/v1/sessions/${sessionId}/summary`, { signal });
  },
  async memories(companionId: number, signal?: AbortSignal): Promise<Memory[]> {
    return request<Memory[]>(`/v1/companions/${companionId}/memories`, { signal });
  },
  async deleteMemory(id: number): Promise<void> {
    await request<void>(`/v1/memories/${id}`, { method: "DELETE" });
  },
  async memoryEnabled(companionId: number, enabled: boolean): Promise<void> {
    await request<void>(`/v1/companions/${companionId}/memory-settings`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    });
  },
  async scenarios(signal?: AbortSignal): Promise<Scenario[]> {
    return request<Scenario[]>("/v1/roleplay/scenarios", { signal });
  },
  async startRoleplay(companionId: number, scenarioKey: string): Promise<RunStart> {
    return request<RunStart>(`/v1/companions/${companionId}/roleplay`, {
      method: "POST",
      body: JSON.stringify({ scenario_key: scenarioKey }),
    });
  },
  async getRun(runId: number, signal?: AbortSignal): Promise<Run> {
    return request<Run>(`/v1/roleplay/${runId}`, { signal });
  },
  async finishRoleplay(runId: number): Promise<Run> {
    return request<Run>(`/v1/roleplay/${runId}/finish`, { method: "POST" });
  },
  async providers(signal?: AbortSignal): Promise<Provider[]> {
    return request<Provider[]>("/v1/model-providers", { signal });
  },
  async usage(days = 7, signal?: AbortSignal): Promise<UsageSummary> {
    return request<UsageSummary>(`/v1/me/usage/models?days=${days}`, { signal });
  },
  async providerSettings(signal?: AbortSignal): Promise<ProviderSetting[]> {
    return request<ProviderSetting[]>("/v1/provider-settings", { signal });
  },
  async saveProviderSetting(
    key: string,
    patch: { api_key?: string; base_url?: string | null; enabled?: boolean },
  ): Promise<ProviderSetting> {
    return request<ProviderSetting>(`/v1/provider-settings/${key}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    });
  },
  async discoverModels(providerKey: string): Promise<DiscoveredModel[]> {
    return request<DiscoveredModel[]>(`/v1/provider-settings/${providerKey}/models`);
  },
  async importModels(providerKey: string, modelIds: string[]): Promise<string[]> {
    return request<string[]>(`/v1/provider-settings/${providerKey}/models/import`, {
      method: "POST",
      body: JSON.stringify({ model_ids: modelIds }),
    });
  },
  async probeProvider(providerKey: string): Promise<{ ok: boolean; model_count?: number }> {
    return request<{ ok: boolean; model_count?: number }>(
      `/v1/provider-settings/${providerKey}/probe`,
      { method: "POST" },
    );
  },
  async setCompanionVoice(id: number, voiceId: string | null): Promise<Companion> {
    return request<Companion>(`/v1/companions/${id}/voice`, {
      method: "PUT",
      body: JSON.stringify({ voice_id: voiceId }),
    });
  },
  async voiceProviders(signal?: AbortSignal): Promise<VoiceProvider[]> {
    return request<VoiceProvider[]>("/v1/voice/providers", { signal });
  },
  async saveVoiceProvider(
    key: string,
    patch: {
      app_id?: string;
      token?: string;
      cluster?: string;
      base_url?: string | null;
      enabled?: boolean;
    },
  ): Promise<VoiceProvider> {
    return request<VoiceProvider>(`/v1/voice/providers/${key}`, {
      method: "PUT",
      body: JSON.stringify(patch),
    });
  },
  async probeVoiceProvider(key: string): Promise<{ ok: boolean; voice_count?: number }> {
    return request<{ ok: boolean; voice_count?: number }>(
      `/v1/voice/providers/${key}/probe`,
      { method: "POST" },
    );
  },
  async voiceOptions(key: string, refresh = false, signal?: AbortSignal): Promise<VoiceOption[]> {
    return request<VoiceOption[]>(
      `/v1/voice/providers/${key}/voices${refresh ? "?refresh=true" : ""}`, { signal });
  },
  async transcribe(audio: Blob, providerKey = "volcengine"): Promise<{ text: string; duration_ms: number }> {
    const form = new FormData();
    // 后端按 Content-Type 判断音频格式（不看文件名）。这里按真实类型命名，
    // 保证 FormData 里的 Content-Type 与音频实际格式一致，避免 MIME 错配。
    const extension = audio.type.includes("wav")
      ? "wav"
      : audio.type.includes("ogg")
        ? "ogg"
        : audio.type.includes("mp3")
          ? "mp3"
          : "webm";
    form.append("file", audio, `voice.${extension}`);
    const response = await fetch(apiUrl(`/v1/voice/transcribe?provider_key=${providerKey}`), {
      method: "POST",
      body: form,
      credentials: "same-origin",
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.message || `识别失败（${response.status}）`);
    }
    return (await response.json()) as { text: string; duration_ms: number };
  },
  async synthesize(
    text: string,
    voiceId: string,
    options: { providerKey?: string; params?: Record<string, unknown>; sessionId?: number } = {},
  ): Promise<VoiceSynthesis> {
    return request<VoiceSynthesis>("/v1/voice/synthesize", {
      method: "POST",
      body: JSON.stringify({
        text,
        voice_id: voiceId,
        provider_key: options.providerKey ?? "volcengine",
        params: options.params ?? null,
        session_id: options.sessionId ?? null,
      }),
    });
  },
  async getProfile(signal?: AbortSignal): Promise<UserProfile> {
    return request<UserProfile>("/v1/me/profile", { signal });
  },
  async saveProfile(profile: UserProfile): Promise<UserProfile> {
    return request<UserProfile>("/v1/me/profile", {
      method: "PUT",
      body: JSON.stringify(profile),
    });
  },
  async getCompanionProfile(id: number, signal?: AbortSignal): Promise<CompanionUserProfile> {
    return request<CompanionUserProfile>(`/v1/me/companions/${id}/profile`, { signal });
  },
  async saveCompanionProfile(
    id: number,
    profile: Partial<CompanionUserProfile>,
  ): Promise<CompanionUserProfile> {
    return request<CompanionUserProfile>(`/v1/me/companions/${id}/profile`, {
      method: "PUT",
      body: JSON.stringify(profile),
    });
  },
  async quota(): Promise<Quota> {
    return request<Quota>("/v1/me/quota");
  },
  async systemInfo(signal?: AbortSignal): Promise<SystemInfo> {
    return request<SystemInfo>("/v1/system/info", { signal });
  },
  async updateCheck(signal?: AbortSignal): Promise<UpdateCheck> {
    return request<UpdateCheck>("/v1/system/update-check", { signal });
  },
  async adminSettings(signal?: AbortSignal): Promise<AdminSettingsResponse> {
    return request<AdminSettingsResponse>("/v1/admin/settings", { signal });
  },
  async adminUpdate(patch: Partial<AdminSettings>): Promise<AdminSettingsResponse> {
    return request<AdminSettingsResponse>("/v1/admin/settings", {
      method: "PUT",
      body: JSON.stringify(patch),
    });
  },
};















