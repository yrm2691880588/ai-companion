import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import type { Companion } from "../types";

export function downloadPersona(companion: Companion): void {
  const payload = {
    format: "ai-companion-persona",
    version: 1,
    exported_at: new Date().toISOString(),
    persona: companion.persona,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
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

export default function PersonaImportButton() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 2000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  async function onFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as { persona?: unknown; format?: string };
      const persona = parsed.persona;
      if (!persona || typeof persona !== "object") {
        throw new Error("文件里没有找到人设（persona）");
      }
      const created = await api.importPersona(persona as never);
      setNotice("导入成功");
      navigate(`/companions/${created.id}/chat`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button className="btn ghost" disabled={busy} onClick={() => inputRef.current?.click()}>
        {busy ? "导入中…" : "导入人设"}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="application/json,.json"
        style={{ display: "none" }}
        onChange={(event) => void onFile(event)}
      />
      {error && <span className="muted"> {error}</span>}
      {notice && <span className="muted"> {notice}</span>}
    </>
  );
}
