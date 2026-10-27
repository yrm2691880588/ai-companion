import { useRef, useState } from "react";
import { api } from "../api";
import Modal from "./Modal";
import type { Persona } from "../types";

interface Props {
  persona: Persona;
  onClose: () => void;
}

interface Turn {
  role: "user" | "assistant";
  content: string;
}

export default function TrialChat({ persona, onClose }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [trialId, setTrialId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [limitReached, setLimitReached] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const userTurns = turns.filter((turn) => turn.role === "user").length;

  async function send() {
    const text = draft.trim();
    if (!text || busy || limitReached) return;
    setDraft("");
    setError("");
    setTurns((prev) => [...prev, { role: "user", content: text }, { role: "assistant", content: "" }]);
    setBusy(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = await api.trialChat(persona, text, trialId ?? undefined);
      if (!response.ok || !response.body) {
        throw new Error("试聊请求失败");
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
          let event = "message";
          const dataLines: string[] = [];
          for (const line of block.split("\n")) {
            if (line.startsWith("event:")) event = line.slice(6).trim();
            else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
          }
          if (dataLines.length === 0) continue;
          const payload = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
          if (event === "meta" && typeof payload.trial_id === "string") {
            setTrialId(payload.trial_id);
          } else if (event === "delta") {
            const delta = String(payload.text ?? "");
            setTurns((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last && last.role === "assistant") last.content += delta;
              return next;
            });
          } else if (event === "error") {
            const code = String(payload.code ?? "");
            setError(String(payload.message ?? "试聊失败"));
            if (code === "TRIAL_LIMIT") setLimitReached(true);
          }
          boundary = buffer.indexOf("\n\n");
        }
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="先和她聊两句"
      className="trial-modal"
      footer={
        <button className="ghost" onClick={onClose}>
          关闭
        </button>
      }
    >
      <p className="muted">
        这里只是试聊，不会保存到正式会话，也不会产生记忆。已聊 {userTurns}/3 轮
      </p>

      {error && <div className="alert">{error}</div>}

      <div className="trial-messages">
        {turns.length === 0 && <p className="muted">说一句试试，看她像不像你想要的人。</p>}
        {turns.map((turn, index) => (
          <div key={index} className={`bubble ${turn.role}`}>
            {turn.content || (busy && index === turns.length - 1 ? "…" : "")}
          </div>
        ))}
      </div>

      <div className="composer">
        <textarea
          rows={1}
          value={draft}
          disabled={busy || limitReached}
          placeholder={limitReached ? "试聊已满 3 轮，去创建她继续聊" : "说点什么…"}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <button className="primary" disabled={busy || limitReached} onClick={() => void send()}>
          {busy ? "…" : "发送"}
        </button>
      </div>
    </Modal>
  );
}

