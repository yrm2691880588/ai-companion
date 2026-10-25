import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, streamEvents } from "../api";
import type { Companion, Message, Quota, Session } from "../types";

export default function ChatPage() {
  const { id } = useParams();
  const companionId = Number(id);
  const [companion, setCompanion] = useState<Companion | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const [quota, setQuota] = useState<Quota | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [loaded, list] = await Promise.all([
          api.companion(companionId),
          api.sessions(companionId),
        ]);
        setCompanion(loaded);
        setSessions(list);
        if (list.length > 0) await selectSession(list[0].id);
        setQuota(await api.quota());
      } catch (event) {
        setError((event as Error).message);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  async function selectSession(id: number) {
    setSessionId(id);
    setMessages(await api.messages(id));
  }

  async function newSession() {
    try {
      const created = await api.createSession(companionId);
      setSessions((prev) => [created, ...prev]);
      await selectSession(created.id);
    } catch (event) {
      setError((event as Error).message);
    }
  }

  async function send() {
    const text = draft.trim();
    if (!text || !sessionId || streaming) return;
    setDraft("");
    setError("");
    const tempUserId = -Date.now();
    const tempAssistantId = tempUserId - 1;
    const now = new Date().toISOString();
    setMessages((prev) => [
      ...prev,
      { id: tempUserId, session_id: sessionId, seq: 0, role: "user", content: text, created_at: now },
      { id: tempAssistantId, session_id: sessionId, seq: 0, role: "assistant", content: "", created_at: now },
    ]);
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamEvents(
        `/v1/sessions/${sessionId}/messages`,
        { content: text },
        {
          onDelta: (delta) =>
            setMessages((prev) =>
              prev.map((item) =>
                item.id === tempAssistantId ? { ...item, content: item.content + delta } : item,
              ),
            ),
          onError: (err) => setError(err.message),
          onDone: () => {
            void (async () => {
              const list = await api.messages(sessionId);
              setMessages(list);
              setSessions(await api.sessions(companionId));
              setQuota(await api.quota());
            })();
          },
        },
        controller.signal,
      );
    } catch (event) {
      if (!(event instanceof DOMException && event.name === "AbortError")) {
        setError((event as Error).message);
      } else if (sessionId) {
        window.setTimeout(() => {
          void api.messages(sessionId).then(setMessages);
        }, 400);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  async function regenerate(messageId: number) {
    if (!sessionId || streaming) return;
    setError("");
    setStreaming(true);
    setMessages((prev) =>
      prev.map((item) => (item.id === messageId ? { ...item, content: "" } : item)),
    );
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamEvents(
        `/v1/messages/${messageId}/regenerate`,
        {},
        {
          onDelta: (delta) =>
            setMessages((prev) =>
              prev.map((item) =>
                item.id === messageId ? { ...item, content: item.content + delta } : item,
              ),
            ),
          onError: (err) => setError(err.message),
          onDone: () => {
            void (async () => {
              setMessages(await api.messages(sessionId));
              setQuota(await api.quota());
            })();
          },
        },
        controller.signal,
      );
    } catch (event) {
      if (!(event instanceof DOMException && event.name === "AbortError")) {
        setError((event as Error).message);
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  const lastAssistantId = [...messages].reverse().find((item) => item.role === "assistant")?.id;

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>{companion ? companion.name : "对话"}</h1>
          <p className="muted">
            {companion ? `${companion.persona.identity} · 人设 v${companion.current_version}` : "加载中…"}
          </p>
          {quota && (
            <span className="chip">
              今日剩余 {quota.remaining}/{quota.limit} 轮
            </span>
          )}
        </div>
        <div className="toolbar">
          <Link className="btn ghost" to={`/companions/${companionId}/memories`}>
            记忆
          </Link>
          <Link className="btn ghost" to={`/companions/${companionId}/roleplay`}>
            演练
          </Link>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}
      {quota && quota.remaining <= 0 && (
        <div className="notice">今天的额度用完了，明天再来聊吧。</div>
      )}

      <div className="chat-layout" style={{ marginTop: 12 }}>
        <aside>
          <button className="btn" style={{ width: "100%" }} onClick={() => void newSession()}>
            + 新会话
          </button>
          <div className="session-list" style={{ marginTop: 8 }}>
            {sessions.map((item) => (
              <button
                key={item.id}
                className={`session-item ${item.id === sessionId ? "active" : ""}`}
                onClick={() => void selectSession(item.id)}
              >
                {item.title || "未命名会话"}
              </button>
            ))}
          </div>
        </aside>

        <section>
          <div className="messages">
            {messages.map((item) => (
              <div key={item.id} className={`bubble ${item.role}`}>
                {item.content || (streaming ? "…" : "")}
                {item.role === "assistant" && item.id === lastAssistantId && !streaming && (
                  <div style={{ marginTop: 6 }}>
                    <button
                      className="ghost"
                      style={{ fontSize: 12, padding: "2px 8px" }}
                      onClick={() => void regenerate(item.id)}
                    >
                      重新生成
                    </button>
                  </div>
                )}
              </div>
            ))}
            <div ref={bottomRef} />
          </div>
          <div className="composer">
            <input
              value={draft}
              placeholder="说点什么…"
              disabled={!sessionId}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void send();
                }
              }}
            />
            {streaming ? (
              <button className="danger" onClick={stop}>
                停止
              </button>
            ) : (
              <button className="primary" onClick={() => void send()}>
                发送
              </button>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
