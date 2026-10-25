import { Fragment, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, streamEvents } from "../api";
import type { Companion, Message, Quota, Session } from "../types";

const STICK_THRESHOLD = 80;

function dayKey(iso: string): string {
  return new Date(iso).toDateString();
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function dayLabel(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const yesterday = new Date();
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === now.toDateString()) return "今天";
  if (date.toDateString() === yesterday.toDateString()) return "昨天";
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} 天前`;
  return dayLabel(iso);
}

export default function ChatPage() {
  const { id } = useParams();
  const companionId = Number(id);
  const [companion, setCompanion] = useState<Companion | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [openerLoading, setOpenerLoading] = useState(false);
  const [showJump, setShowJump] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [quota, setQuota] = useState<Quota | null>(null);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [confirm, setConfirm] = useState<
    { kind: "session" | "message"; id: number; title: string } | null
  >(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const stickRef = useRef(true);

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
    if (!stickRef.current) return;
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, streaming, openerLoading]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 1500);
    return () => window.clearTimeout(timer);
  }, [notice]);

  async function selectSession(id: number) {
    setSessionId(id);
    setError("");
    setShowJump(false);
    stickRef.current = true;
    const list = await api.messages(id);
    setMessages(list);
    if (list.length === 0) {
      setOpenerLoading(true);
      try {
        const opener = await api.openSession(id);
        setMessages([opener]);
        setSessions(await api.sessions(companionId));
      } catch (event) {
        setError((event as Error).message);
      } finally {
        setOpenerLoading(false);
      }
    }
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
    if (composerRef.current) composerRef.current.style.height = "auto";
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
        { content: text, client_request_id: crypto.randomUUID?.() ?? `${Date.now()}` },
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

  async function copy(content: string) {
    try {
      await navigator.clipboard.writeText(content);
      setNotice("已复制");
    } catch {
      setNotice("复制失败，请手动选择文字");
    }
  }

  function onScroll() {
    const el = scrollerRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    stickRef.current = distance < STICK_THRESHOLD;
    setShowJump(distance >= STICK_THRESHOLD);
  }

  function scrollToLatest() {
    const el = scrollerRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    stickRef.current = true;
    setShowJump(false);
  }

  function autoGrow() {
    const el = composerRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }

  function groupOf(iso: string): string {
    const date = new Date(iso);
    const today = new Date();
    const yesterday = new Date();
    yesterday.setDate(today.getDate() - 1);
    if (date.toDateString() === today.toDateString()) return "今天";
    if (date.toDateString() === yesterday.toDateString()) return "昨天";
    return "更早";
  }

  async function saveRename(id: number) {
    const title = renameDraft.trim();
    if (!title) {
      setRenamingId(null);
      return;
    }
    try {
      const updated = await api.renameSession(id, title);
      setSessions((prev) => prev.map((item) => (item.id === id ? updated : item)));
      setRenamingId(null);
    } catch (event) {
      setError((event as Error).message);
    }
  }

  async function confirmDelete() {
    if (!confirm) return;
    setConfirmBusy(true);
    try {
      if (confirm.kind === "session") {
        await api.deleteSession(confirm.id);
        const list = await api.sessions(companionId);
        setSessions(list);
        setConfirm(null);
        if (list.length > 0) await selectSession(list[0].id);
        else await newSession();
      } else {
        await api.deleteMessage(confirm.id);
        setConfirm(null);
        if (sessionId) setMessages(await api.messages(sessionId));
      }
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setConfirmBusy(false);
    }
  }

  const grouped: Record<string, Session[]> = { 今天: [], 昨天: [], 更早: [] };
  for (const item of sessions) {
    grouped[groupOf(item.last_message_at || item.created_at)].push(item);
  }

  const lastAssistantId = [...messages].reverse().find((item) => item.role === "assistant")?.id;

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div className="row" style={{ gap: 12, alignItems: "center" }}>
          {companion && (
            <div className="avatar chat-avatar">
              {companion.avatar ? (
                <img src={companion.avatar} alt={`${companion.name} 的头像`} />
              ) : (
                companion.persona.name.slice(0, 1)
              )}
            </div>
          )}
          <div>
            <h1>{companion ? companion.name : "对话"}</h1>
            <p className="muted">
              {companion
                ? `${companion.persona.relationship || companion.persona.identity} · 人设 v${companion.current_version}`
                : "加载中…"}
            </p>
            {quota &&
              (quota.enforced ? (
                <span className="chip">
                  今日剩余 {quota.remaining}/{quota.limit} 轮
                </span>
              ) : (
                <span className="chip">额度管控已暂停 · 稳定性测试中</span>
              ))}
          </div>
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
      {notice && <div className="toast">{notice}</div>}
      {quota?.enforced && quota.remaining <= 0 && (
        <div className="notice">今天的额度用完了，明天再来聊吧。</div>
      )}

      <div className="chat-layout" style={{ marginTop: 12 }}>
        <aside>
          <button className="btn" style={{ width: "100%" }} onClick={() => void newSession()}>
            + 新会话
          </button>
          <div className="session-list" style={{ marginTop: 8 }}>
            {Object.entries(grouped).map(([label, list]) =>
              list.length === 0 ? null : (
                <div key={label} className="session-group">
                  <div className="session-group-label">{label}</div>
                  {list.map((item) => (
                    <div
                      key={item.id}
                      className={`session-item ${item.id === sessionId ? "active" : ""}`}
                      onClick={() => void selectSession(item.id)}
                    >
                      {renamingId === item.id ? (
                        <input
                          autoFocus
                          value={renameDraft}
                          onClick={(event) => event.stopPropagation()}
                          onChange={(event) => setRenameDraft(event.target.value)}
                          onBlur={() => void saveRename(item.id)}
                          onKeyDown={(event) => {
                            if (event.key === "Enter") void saveRename(item.id);
                            if (event.key === "Escape") setRenamingId(null);
                          }}
                        />
                      ) : (
                        <>
                          <span className="session-title">{item.title || "未命名会话"}</span>
                          <span className="session-time">
                            {relativeTime(item.last_message_at || item.created_at)}
                          </span>
                          <span className="session-actions">
                            <button
                              className="link"
                              title="重命名"
                              onClick={(event) => {
                                event.stopPropagation();
                                setRenamingId(item.id);
                                setRenameDraft(item.title || "");
                              }}
                            >
                              改
                            </button>
                            <button
                              className="link danger-text"
                              title="删除会话"
                              onClick={(event) => {
                                event.stopPropagation();
                                setConfirm({
                                  kind: "session",
                                  id: item.id,
                                  title: item.title || "未命名会话",
                                });
                              }}
                            >
                              删
                            </button>
                          </span>
                        </>
                      )}
                    </div>
                  ))}
                </div>
              ),
            )}
          </div>
        </aside>

        <section className="chat-panel">
          <div className="messages" ref={scrollerRef} onScroll={onScroll}>
            {messages.map((item, index) => {
              const prev = messages[index - 1];
              const newDay = !prev || dayKey(prev.created_at) !== dayKey(item.created_at);
              return (
                <Fragment key={item.id}>
                  {newDay && (
                    <div className="date-divider">
                      <span>{dayLabel(item.created_at)}</span>
                    </div>
                  )}
                  <div className={`bubble ${item.role}`}>
                    <div className="bubble-content">
                      {item.content || (streaming ? "…" : "")}
                    </div>
                    <div className="bubble-meta">
                      <span>{formatTime(item.created_at)}</span>
                      <button className="link" onClick={() => void copy(item.content)}>
                        复制
                      </button>
                      <button
                        className="link danger-text"
                        onClick={() =>
                          setConfirm({
                            kind: "message",
                            id: item.id,
                            title: item.content.slice(0, 20),
                          })
                        }
                      >
                        删除
                      </button>
                      {item.role === "assistant" && item.id === lastAssistantId && !streaming && (
                        <button className="link" onClick={() => void regenerate(item.id)}>
                          重新生成
                        </button>
                      )}
                    </div>
                  </div>
                </Fragment>
              );
            })}
            {openerLoading && (
              <div className="bubble assistant typing">她正在想怎么跟你打招呼…</div>
            )}
            {!openerLoading && messages.length === 0 && sessionId && (
              <div className="empty-chat">
                <p>新会话已经建好了。</p>
                <p className="muted">她应该马上就会开口，稍等一下。</p>
              </div>
            )}
          </div>

          {showJump && (
            <button className="jump-latest" onClick={scrollToLatest}>
              回到最新 ↓
            </button>
          )}

          <div className="composer">
            <textarea
              ref={composerRef}
              rows={1}
              value={draft}
              placeholder="说点什么…（Enter 发送，Shift+Enter 换行）"
              disabled={!sessionId}
              onChange={(event) => {
                setDraft(event.target.value);
                autoGrow();
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
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

      {confirm && (
        <div className="modal-backdrop" onClick={() => !confirmBusy && setConfirm(null)}>
          <div className="modal" onClick={(event) => event.stopPropagation()}>
            <h2>{confirm.kind === "session" ? "删除会话" : "删除消息"}</h2>
            <p className="muted">
              {confirm.kind === "session"
                ? `会删除「${confirm.title}」里的全部消息，不可恢复。`
                : `确定删除这条消息吗？删除后不会出现在历史里。`}
            </p>
            <div className="toolbar">
              <button className="danger" disabled={confirmBusy} onClick={() => void confirmDelete()}>
                {confirmBusy ? "删除中…" : "确认删除"}
              </button>
              <button className="ghost" disabled={confirmBusy} onClick={() => setConfirm(null)}>
                取消
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
