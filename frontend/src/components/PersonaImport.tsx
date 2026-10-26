import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import PersonaForm from "./PersonaForm";
import type { Companion, Persona } from "../types";

export function downloadPersona(companion: Companion): void {
  const payload = {
    format: "ai-companion-persona",
    version: 1,
    exported_at: new Date().toISOString(),
    persona: companion.persona,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `${companion.name}-人设.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

interface Props {
  onCreated: (companion: Companion) => void;
}

export default function PersonaImportButton({ onCreated }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [draft, setDraft] = useState<Persona | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!draft) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDraft(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [draft]);

  async function onFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError("");
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as { persona?: unknown; format?: string };
      if (parsed.format && parsed.format !== "ai-companion-persona") {
        throw new Error("不是本产品导出的人设文件");
      }
      if (!parsed.persona || typeof parsed.persona !== "object") {
        throw new Error("文件里没有找到人设（persona）");
      }
      // 先预览，不创建
      setDraft(parsed.persona as Persona);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function create() {
    if (!draft) return;
    setBusy(true);
    setError("");
    try {
      const created = await api.importPersona(draft);
      setDraft(null);
      onCreated(created);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className="btn ghost" onClick={() => inputRef.current?.click()}>
        导入人设
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="application/json,.json"
        style={{ display: "none" }}
        onChange={(event) => void onFile(event)}
      />
      {error && <span className="muted"> {error}</span>}

      {draft && (
        <div className="modal-backdrop" onClick={() => !busy && setDraft(null)}>
          <div className="modal import-modal" onClick={(event) => event.stopPropagation()}>
            <h2>预览导入的人设</h2>
            <p className="muted">
              这是文件里的内容。可以直接修改，确认后才会创建新伴侣；关闭不会保存。
            </p>
            {error && <div className="alert">{error}</div>}
            <div className="import-form">
              <PersonaForm value={draft} onChange={setDraft} disabled={busy} />
            </div>
            <div className="toolbar">
              <button className="primary" disabled={busy} onClick={() => void create()}>
                {busy ? "创建中…" : "用这版人设创建伴侣"}
              </button>
              <button className="ghost" disabled={busy} onClick={() => setDraft(null)}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

