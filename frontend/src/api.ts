import type {
  Account,
  AdminSettings,
  AdminSettingsResponse,
  Companion,
  Latest,
  LoginResponse,
  Memory,
  Message,
  Persona,
  Provider,
  Quota,
  Run,
  RunStart,
  Scenario,
  Session,
  SmsCodeResponse,
  Summary,
  Template,
  UsageSummary,
} from "./types";

const USER_KEY = "ai-companion-user-id";

export function getUserId(): string {
  return localStorage.getItem(USER_KEY) || "dev-user";
}

export function setUserId(value: string): void {
  localStorage.setItem(USER_KEY, value.trim() || "dev-user");
}

export class ApiError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-User-Id": getUserId(),
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
  onMeta?: (data: { session_id: number; user_message_id: number }) => void;
  onDelta?: (text: string) => void;
  onDone?: (data: {
    assistant_message_id: number;
    model?: string;
    input_tokens?: number;
    output_tokens?: number;
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
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-User-Id": getUserId(),
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
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary = buffer.indexOf("\n\n");
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      handleBlock(block, handlers);
      boundary = buffer.indexOf("\n\n");
    }
  }
}

function handleBlock(block: string, handlers: StreamHandlers): void {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (dataLines.length === 0) return;
  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
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
  async companions(): Promise<Companion[]> {
    return request<Companion[]>("/v1/companions");
  },
  async companion(id: number): Promise<Companion> {
    return request<Companion>(`/v1/companions/${id}`);
  },
  async createCompanion(persona: Persona, name?: string): Promise<Companion> {
    return request<Companion>("/v1/companions", {
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
  async draftPersona(description: string): Promise<Persona> {
    const result = await request<{ persona: Persona }>("/v1/personas/draft", {
      method: "POST",
      body: JSON.stringify({ description }),
    });
    return result.persona;
  },
  async savePersona(id: number, persona: Persona): Promise<Companion> {
    return request<Companion>(`/v1/companions/${id}/persona`, {
      method: "PUT",
      body: JSON.stringify({ persona }),
    });
  },
  async templates(): Promise<Template[]> {
    return request<Template[]>("/v1/templates");
  },
  async sessions(companionId: number): Promise<Session[]> {
    return request<Session[]>(`/v1/companions/${companionId}/sessions`);
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
  async latest(companionId: number): Promise<Latest> {
    return request<Latest>(`/v1/companions/${companionId}/latest`);
  },
  async messages(sessionId: number): Promise<Message[]> {
    return request<Message[]>(`/v1/sessions/${sessionId}/messages?limit=100`);
  },
  async summary(sessionId: number): Promise<Summary> {
    return request<Summary>(`/v1/sessions/${sessionId}/summary`);
  },
  async memories(companionId: number): Promise<Memory[]> {
    return request<Memory[]>(`/v1/companions/${companionId}/memories`);
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
  async scenarios(): Promise<Scenario[]> {
    return request<Scenario[]>("/v1/roleplay/scenarios");
  },
  async startRoleplay(companionId: number, scenarioKey: string): Promise<RunStart> {
    return request<RunStart>(`/v1/companions/${companionId}/roleplay`, {
      method: "POST",
      body: JSON.stringify({ scenario_key: scenarioKey }),
    });
  },
  async getRun(runId: number): Promise<Run> {
    return request<Run>(`/v1/roleplay/${runId}`);
  },
  async finishRoleplay(runId: number): Promise<Run> {
    return request<Run>(`/v1/roleplay/${runId}/finish`, { method: "POST" });
  },
  async providers(): Promise<Provider[]> {
    return request<Provider[]>("/v1/model-providers");
  },
  async usage(days = 7): Promise<UsageSummary> {
    return request<UsageSummary>(`/v1/me/usage/models?days=${days}`);
  },
  async quota(): Promise<Quota> {
    return request<Quota>("/v1/me/quota");
  },
  async adminSettings(): Promise<AdminSettingsResponse> {
    return request<AdminSettingsResponse>("/v1/admin/settings");
  },
  async adminUpdate(patch: Partial<AdminSettings>): Promise<AdminSettingsResponse> {
    return request<AdminSettingsResponse>("/v1/admin/settings", {
      method: "PUT",
      body: JSON.stringify(patch),
    });
  },
};
