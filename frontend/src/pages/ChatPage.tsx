import { useQuery, useQueryClient } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { Fragment, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, streamEvents } from "../api";
import { track } from "../lib/analytics";
import Menu from "../components/Menu";
import Modal from "../components/Modal";
import VoiceBar from "../components/VoiceBar";
import { playAudio } from "../lib/voice";
import type { Message, Session } from "../lib/types";

const STICK_THRESHOLD = 80;
const EMPTY_MESSAGES: Message[] = [];

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
  return <Chat key={id} companionId={Number(id)} />;
}

function Chat({ companionId }: { companionId: number }) {
  const client = useQueryClient();
  const companionQuery = useQuery(queries.companion(companionId));
  const companion = companionQuery.data;
  const sessionsQuery = useQuery({ ...queries.sessions(companionId), enabled: false });
  const sessions = sessionsQuery.data ?? [];
  const voiceQuery = useQuery(queries.voiceProviders());
  const voiceAvailable = voiceQuery.data?.some(item => item.configured && item.enabled) ?? false;
  const [sessionId, setSessionId] = useState<number | null>(null);
  const messagesQuery = useQuery({ ...queries.messages(sessionId ?? 0), enabled: false });
  const messages = messagesQuery.data ?? EMPTY_MESSAGES;
  const summaryQuery = useQuery({ ...queries.summary(sessionId ?? 0), enabled: sessionId !== null });
  const recap = summaryQuery.data?.summary ?? null;
  function setMessages(next: Message[] | ((old: Message[]) => Message[])) {
    if (sessionId === null) return;
    client.setQueryData(queries.messages(sessionId).queryKey, (old = []) => typeof next === "function" ? next(old) : next);
  }
  function setSessions(next: Session[] | ((old: Session[]) => Session[])) {
    client.setQueryData(queries.sessions(companionId).queryKey, (old = []) => typeof next === "function" ? next(old) : next);
  }
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [openerLoading, setOpenerLoading] = useState(false);
  const [voiceOn, setVoiceOn] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const stopPlayRef = useRef<(() => void) | null>(null);
  const [showJump, setShowJump] = useState(false);
  const [error, setError] = useState("");

  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [confirm, setConfirm] = useState<
    { kind: "session" | "message"; id: number; title: string } | null
  >(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [headerMenu, setHeaderMenu] = useState(false);
  const navigate = useNavigate();
  const [echo, setEcho] = useState<{ messageId: number; items: string[] } | null>(null);
  const [echoOpen, setEchoOpen] = useState(false);
  const trackedReplyRef = useRef(false);
  const echoEnabled = localStorage.getItem("ai-companion-echo") !== "off";
  const [recapOpen, setRecapOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const stickRef = useRef(true);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const list = await client.fetchQuery(queries.sessions(companionId));
        if (!active) return;
        if (list.length > 0) await selectSession(list[0].id);
        else await newSession();
      } catch (event) {
        if (active) setError((event as Error).message);
      }
    })();
    return () => {
      active = false;
      abortRef.current?.abort();
      stopPlayRef.current?.();
    };
    // 路由按 companionId 挂载，初始化只选一次会话。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, companionId]);

  useEffect(() => {
    if (!stickRef.current) return;
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, streaming, openerLoading]);

  async function selectSession(id: number) {
    abortRef.current?.abort();
    stopPlayRef.current?.();
    setSpeaking(false);
    setSessionId(id);
    setError("");
    setShowJump(false);
    stickRef.current = true;
    setRecapOpen(false);
    setEcho(null);
    setEchoOpen(false);
    try {
      const list = await client.fetchQuery(queries.messages(id));
      if (list.length === 0) {
        setOpenerLoading(true);
        const opener = await api.openSession(id);
        client.setQueryData(queries.messages(id).queryKey, [opener]);
        await client.fetchQuery(queries.sessions(companionId));
      }
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setOpenerLoading(false);
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

  async function send(explicitText?: string) {
    const text = (explicitText ?? draft).trim();
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
    if (messages.length === 0) track("first_message");
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamEvents(
        `/v1/sessions/${sessionId}/messages`,
        { content: text, client_request_id: crypto.randomUUID?.() ?? `${Date.now()}` },
        {
          onDelta: (delta) => {
            if (!trackedReplyRef.current) {
              trackedReplyRef.current = true;
              track("first_reply");
            }
            setMessages((prev) =>
              prev.map((item) =>
                item.id === tempAssistantId ? { ...item, content: item.content + delta } : item,
              ),
            );
          },
          onError: (err) => setError(err.message),
          onDone: (data) => {
            void client.invalidateQueries({ queryKey: queries.latest(companionId).queryKey });
            void client.invalidateQueries({ queryKey: queries.usage().queryKey });
            void client.invalidateQueries({ queryKey: queries.summary(sessionId).queryKey });
            if (data.memories && data.memories.length > 0) {
              setEcho({ messageId: 0, items: data.memories });
            }
            void (async () => {
              const list = await client.fetchQuery(queries.messages(sessionId));
              setMessages(list);
              if (data.memories && data.memories.length > 0 && list.length > 0) {
                setEcho({ messageId: list[list.length - 1].id, items: data.memories });
              }
              setSessions(await client.fetchQuery(queries.sessions(companionId)));
              const voiceId = companion?.voice_id;
              if (voiceOn && voiceId) {
                const last = list[list.length - 1];
                if (last && last.role === "assistant" && last.content.trim()) {
                  try {
                    const speech = await api.synthesize(last.content, voiceId, {
                      sessionId,
                    });
                    stopPlayRef.current?.();
                    setSpeaking(true);
                    stopPlayRef.current = playAudio(speech.audio_url, () => {
                      setSpeaking(false);
                      stopPlayRef.current = null;
                    });
                  } catch {
                    toast.warning("这条语音没出来，先看文字吧", { id: "voice-fallback" });
                  }
                }
              }
            })();
          },
        },
        controller.signal,
      );
    } catch (event) {
      if (!(event instanceof DOMException && event.name === "AbortError")) {
        setError((event as Error).message);
        track("error", { error_code: "STREAM_FAILED" });
      } else if (sessionId) {
        window.setTimeout(() => {
          void client.fetchQuery(queries.messages(sessionId)).then(setMessages);
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
    track("message_action");
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
              setMessages(await client.fetchQuery(queries.messages(sessionId)));
      
            })();
          },
        },
        controller.signal,
      );
    } catch (event) {
      if (!(event instanceof DOMException && event.name === "AbortError")) {
        setError((event as Error).message);
        track("error", { error_code: "STREAM_FAILED" });
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  async function copy(content: string) {
    track("message_action");
    try {
      await navigator.clipboard.writeText(content);
      toast.success("已复制", { id: "copy-message" });
    } catch {
      toast.error("复制失败，请手动选择文字", { id: "copy-message" });
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
        const list = await client.fetchQuery(queries.sessions(companionId));
        setSessions(list);
        setConfirm(null);
        if (list.length > 0) await selectSession(list[0].id);
        else await newSession();
      } else {
        await api.deleteMessage(confirm.id);
        setConfirm(null);
        if (sessionId) setMessages(await client.fetchQuery(queries.messages(sessionId)));
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
          </div>
        </div>
        <div className="toolbar">
          <Link className="btn ghost" to={`/companions/${companionId}/persona`}>
            人设
          </Link>
          <Menu
            triggerLabel="更多操作"
            open={headerMenu}
            onOpenChange={setHeaderMenu}
            trigger={
              <button className="btn ghost" aria-label="更多操作">
                ⋯
              </button>
            }
            items={[
              {
                key: "memories",
                label: "她记得的事",
                onSelect: () => navigate(`/companions/${companionId}/memories`),
              },
              {
                key: "roleplay",
                label: "场景演练",
                onSelect: () => navigate(`/companions/${companionId}/roleplay`),
              },
            ]}
          />
        </div>
      </div>

      {(error || companionQuery.error || voiceQuery.error || summaryQuery.error) && <div className="alert">{error || companionQuery.error?.message || voiceQuery.error?.message || summaryQuery.error?.message}</div>}


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
          {recap && (
            <div className="recap">
              <button className="recap-head" onClick={() => setRecapOpen(!recapOpen)}>
                <span>上次聊到</span>
                <span className="muted">{recapOpen ? "收起" : "展开"}</span>
              </button>
              <p className={recapOpen ? "recap-body" : "recap-body clamp"}>{recap}</p>
            </div>
          )}
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
                    {echoEnabled && echo && echo.messageId === item.id && (
                      <div className="echo">
                        <button className="echo-head" onClick={() => setEchoOpen(!echoOpen)}>
                          她想起了… <span className="muted">{echoOpen ? "收起" : "展开"}</span>
                        </button>
                        {echoOpen && (
                          <ul className="echo-list">
                            {echo.items.map((text, index) => (
                              <li key={index}>{text}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}
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

          <div className="row" style={{ gap: 8, marginTop: 8, alignItems: "center" }}>
            <button
              className={voiceOn ? "btn primary" : "btn ghost"}
              onClick={() => {
                if (!voiceAvailable) {
                  toast.info("先到「模型与用量 → 语音」配置火山 AppID 与 Token", { id: "voice-setup" });
                  return;
                }
                setVoiceOn(!voiceOn);
                if (voiceOn) {
                  stopPlayRef.current?.();
                  stopPlayRef.current = null;
                  setSpeaking(false);
                }
              }}
              title={voiceOn ? "关闭语音模式" : "开启语音模式：说话后她会语音回复"}
            >
              {voiceOn ? "语音模式：开" : "语音模式：关"}
            </button>
            {voiceOn && (
              <VoiceBar available={voiceAvailable} onTranscribed={(text) => void send(text)} />
            )}
            {speaking && (
              <span className="voice-playing">
                <span className="muted">她在说话…</span>
                <button
                  className="btn ghost"
                  onClick={() => {
                    stopPlayRef.current?.();
                    stopPlayRef.current = null;
                    setSpeaking(false);
                  }}
                >
                  停止
                </button>
              </span>
            )}
            {voiceOn && (
              <span className="muted" style={{ fontSize: 12 }}>
                语音比文字贵，按供应商实际计费
              </span>
            )}
          </div>
        </section>
      </div>

      {confirm && (
        <Modal
          open
          onClose={() => !confirmBusy && setConfirm(null)}
          title={confirm.kind === "session" ? "删除会话" : "删除消息"}
          description={
            confirm.kind === "session"
              ? `会删除「${confirm.title}」里的全部消息，不可恢复。`
              : "确定删除这条消息吗？删除后不会出现在历史里。"
          }
          preventClose={confirmBusy}
          footer={
            <>
              <button className="danger" disabled={confirmBusy} onClick={() => void confirmDelete()}>
                {confirmBusy ? "删除中…" : "确认删除"}
              </button>
              <button className="ghost" disabled={confirmBusy} onClick={() => setConfirm(null)}>
                取消
              </button>
            </>
          }
        >
          <></>
        </Modal>
      )}
    </div>
  );
}















