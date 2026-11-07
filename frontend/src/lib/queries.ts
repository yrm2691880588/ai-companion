import { QueryClient, queryOptions } from "@tanstack/react-query";
import { api, getUserId } from "../api";

/** 服务端数据的前端缓存入口；不持久化个人资料，也不自动重试写操作。 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 0,
      gcTime: 5 * 60_000,
      retry: false,
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
    },
    mutations: { retry: false, gcTime: 5 * 60_000 },
  },
});

const key = (...parts: (string | number)[]) => [getUserId(), ...parts] as const;

export const queries = {
  companions: () => queryOptions({ queryKey: key("companions"), queryFn: ({ signal }) => api.companions(signal) }),
  companion: (id: number) => queryOptions({ queryKey: key("companion", id), queryFn: ({ signal }) => api.companion(id, signal) }),
  latest: (id: number) => queryOptions({ queryKey: key("latest", id), queryFn: ({ signal }) => api.latest(id, signal) }),
  sessions: (id: number) => queryOptions({ queryKey: key("sessions", id), queryFn: ({ signal }) => api.sessions(id, signal) }),
  messages: (id: number) => queryOptions({ queryKey: key("messages", id), queryFn: ({ signal }) => api.messages(id, signal) }),
  summary: (id: number) => queryOptions({ queryKey: key("summary", id), queryFn: ({ signal }) => api.summary(id, signal) }),
  memories: (id: number) => queryOptions({ queryKey: key("memories", id), queryFn: ({ signal }) => api.memories(id, signal) }),
  personaVersions: (id: number) => queryOptions({ queryKey: key("persona-versions", id), queryFn: ({ signal }) => api.personaVersions(id, signal) }),
  templates: () => queryOptions({ queryKey: key("templates"), queryFn: ({ signal }) => api.templates(signal) }),
  scenarios: () => queryOptions({ queryKey: key("scenarios"), queryFn: ({ signal }) => api.scenarios(signal) }),
  run: (id: number) => queryOptions({ queryKey: key("run", id), queryFn: ({ signal }) => api.getRun(id, signal) }),
  providers: () => queryOptions({ queryKey: key("providers"), queryFn: ({ signal }) => api.providers(signal) }),
  usage: () => queryOptions({ queryKey: key("usage", 7), queryFn: ({ signal }) => api.usage(7, signal) }),
  providerSettings: () => queryOptions({ queryKey: key("provider-settings"), queryFn: ({ signal }) => api.providerSettings(signal) }),
  voiceProviders: () => queryOptions({ queryKey: key("voice-providers"), queryFn: ({ signal }) => api.voiceProviders(signal) }),
  voices: (provider: string) => queryOptions({ queryKey: key("voices", provider), queryFn: ({ signal }) => api.voiceOptions(provider, false, signal) }),
  profile: () => queryOptions({ queryKey: key("profile"), queryFn: ({ signal }) => api.getProfile(signal) }),
  companionProfile: (id: number) => queryOptions({ queryKey: key("companion-profile", id), queryFn: ({ signal }) => api.getCompanionProfile(id, signal) }),
  admin: () => queryOptions({ queryKey: key("admin"), queryFn: ({ signal }) => api.adminSettings(signal) }),
  systemInfo: () => queryOptions({ queryKey: key("system-info"), queryFn: ({ signal }) => api.systemInfo(signal) }),
};
