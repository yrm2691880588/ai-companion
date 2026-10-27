/** 人设导出：把伴侣人设序列化为 JSON 文件并触发下载。 */

import type { Companion } from "./types";

export const PERSONA_EXPORT_FORMAT = "ai-companion-persona";
export const PERSONA_EXPORT_VERSION = 1;

export function personaExportPayload(companion: Companion): Record<string, unknown> {
  return {
    format: PERSONA_EXPORT_FORMAT,
    version: PERSONA_EXPORT_VERSION,
    exported_at: new Date().toISOString(),
    persona: companion.persona,
  };
}

export function downloadPersona(companion: Companion): void {
  const blob = new Blob([JSON.stringify(personaExportPayload(companion), null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${companion.name}-人设.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
