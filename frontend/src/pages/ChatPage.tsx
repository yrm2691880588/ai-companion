import { useQuery, useQueryClient } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { Fragment, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  ArrowDown,
  Copy,
  Menu as MenuIcon,
  Mic,
  MoreHorizontal,
  Pencil,
  Plus,
  RotateCw,
  Send,
  Trash2,
  X,
} from "lucide-react";
import { api, streamEvents } from "../api";
import { track } from "../lib/analytics";
import Menu from "../components/Menu";
import ErrorAlert from "../components/ErrorAlert";
import Modal from "../components/Modal";
import VoiceBar from "../components/VoiceBar";
import { createStreamingSpeaker } from "../lib/speech";
import type { StreamingSpeaker } from "../lib/speech";
import { clockTime, dayLabel as formatDayLabel, relativeTime } from "../lib/format";
import { MESSAGE_PAGE_SIZE, OLDER_PAGE_SIZE } from "../lib/constants";
import type { Message, Session } from "../lib/types";

const STICK_THRESHOLD = 80;
const EMPTY_MESSAGES: Message[] = [];

function dayKey(iso: string): string {
  return new Date(iso).toDateString();
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
  // 当前正在播报的流式语音，用于关语音/切会话时立刻停下
  const speakerRef = useRef<StreamingSpeaker | null>(null);
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
  // 手机端会话列表抽屉；桌面端这个状态不生效（按钮隐藏）
  const [drawerOpen, setDrawerOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const stickRef = useRef(true);
  // 「加载更早」：hasMore 表示前面还有；loadingOlder 防重复触发
  const [hasMore, setHasMore] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  /**
   * 失败后重试用的原文与幂等 ID。
   *
   * 为什么两个都要存：重试必须复用同一个 client_request_id，
   * 否则后端会当成新消息再生成一遍，弱网下就会出现重复气泡和重复扣费。
   */
  const [failedSend, setFailedSend] = useState<
    { text: string; requestId: string } | null
  >(null);
  /** 失败那条助手气泡的临时 id，重试时用它定位并清空。 */
  const lastFailedAssistantIdRef = useRef<number | null>(null);
  /** 当前正在流式生成的那条助手消息 id，点「停止」时用它打标记。 */
  const streamingMessageIdRef = useRef<number | null>(null);
  /** 被用户主动停止的消息 id（只存在本地；刷新后以服务端为准）。 */
  const [stoppedIds, setStoppedIds] = useState<Set<number>>(() => new Set());
  /**
   * 正在往上插入历史消息。
   * 用 ref 而不是 state：effect 需要立刻读到最新值，
   * state 更新是异步的，会漏掉同一帧内的那次滚动。
   */
  const prependingRef = useRef(false);
  /** 插入历史前的滚动基准，等 DOM 更新完由 effect 补偿。 */
  const pendingScrollRef = useRef<{ height: number; top: number } | null>(null);

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
      speakerRef.current?.stop();
      speakerRef.current = null;
      stopPlayRef.current?.();
    };
    // 路由按 companionId 挂载，初始化只选一次会话。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client, companionId]);

  useEffect(() => {
    // 正在往上插历史时不自动滚底，否则会把用户甩到最下面
    if (!stickRef.current || prependingRef.current) return;
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, streaming, openerLoading]);

  /**
   * 补偿滚动位置。
   *
   * 为什么单独放一个 effect：插入历史后 DOM 高度变化需要一个确定的时机。
   * 用 rAF 猜帧数在不同机器上不稳定（实测会差 200 多像素）。
   * 改成：插入前把基准存进 ref，等这次渲染的 effect 跑完再补偿——
   * 那时 React 已经提交 DOM、浏览器也完成了布局。
   */
  useEffect(() => {
    const pending = pendingScrollRef.current;
    if (!pending) return;
    pendingScrollRef.current = null;
    const el = scrollerRef.current;
    if (!el) return;
    const delta = el.scrollHeight - pending.height;
    if (delta > 0) el.scrollTop = pending.top + delta;
    prependingRef.current = false;
    stickRef.current = false;
  }, [messages]);

  /** 立刻停止语音播报并复位状态；关语音、切会话、卸载都走这里。 */
  function stopSpeaking() {
    speakerRef.current?.stop();
    speakerRef.current = null;
    stopPlayRef.current?.();
    stopPlayRef.current = null;
    setSpeaking(false);
  }

  async function selectSession(id: number) {
    abortRef.current?.abort();
    stopSpeaking();
    setSessionId(id);
    setError("");
    setShowJump(false);
    stickRef.current = true;
    setRecapOpen(false);
    setEcho(null);
    setEchoOpen(false);
    setHasMore(false);
    setFailedSend(null);
    // 换会话时清掉上一条会话的「已停止」标记，否则会标到新会话的消息上
    setStoppedIds(new Set());
    try {
      const list = await client.fetchQuery(queries.messages(id));
      // 首屏取 100 条；取满了说明前面可能还有更早的
      setHasMore(list.length >= MESSAGE_PAGE_SIZE);
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

  /**
   * 加载更早的消息。
   *
   * 两个细节必须处理：
   * 1. 插入后要保持视野位置——记下插入前的高度，插入后把滚动条往下推同样距离，
   *    否则内容往上一插，用户正在看的地方会突然跳走；
   * 2. 追加到数组前面时要按 seq 去重，流式回复期间可能已经混进临时消息。
   */
  async function loadOlder() {
    if (!sessionId || loadingOlder || !hasMore) return;
    const list = client.getQueryData<Message[]>(queries.messages(sessionId).queryKey) ?? [];
    const oldest = list.find((item) => item.id > 0);
    if (!oldest) return;

    /**
     * 基准就在点击这一刻读，且**同步**读完再往下走。
     *
     * 为什么不能放在请求回来之后读：
     * 请求期间用户可能还在往上滚（这是加载更早的典型动作），
     * 那时读到的 prevTop 已经不是「点击时用户在看哪里」了。
     */
    const scroller = scrollerRef.current;
    const prevHeight = scroller?.scrollHeight ?? 0;
    const prevTop = scroller?.scrollTop ?? 0;

    setLoadingOlder(true);
    prependingRef.current = true;
    // 记下基准；真正的补偿交给下面监听 messages 的 effect
    pendingScrollRef.current = { height: prevHeight, top: prevTop };
    try {
      const older = await api.olderMessages(sessionId, oldest.seq, OLDER_PAGE_SIZE);
      setHasMore(older.length >= OLDER_PAGE_SIZE);
      if (older.length > 0) {
        client.setQueryData(queries.messages(sessionId).queryKey, (current: Message[] = []) => {
          const seen = new Set(current.map((item) => item.id));
          const fresh = older.filter((item) => !seen.has(item.id));
          return [...fresh, ...current];
        });
        // 补偿在 effect 里做，这里不用 rAF 了
      } else {
        pendingScrollRef.current = null;
        prependingRef.current = false;
      }
    } catch (event) {
      pendingScrollRef.current = null;
      prependingRef.current = false;
      setError((event as Error).message);
    } finally {
      setLoadingOlder(false);
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

  /**
   * 发送消息。
   *
   * 失败时的处理（这次新增）：
   * - 记录原文 + 本次的 client_request_id，气泡下方出现「重试」；
   * - 重试**复用同一个 ID**，后端幂等，不会重复生成、重复扣费；
   * - 失败的那条助手气泡不删，改成明确的失败提示，而不是永远停在「…」。
   */
  async function send(explicitText?: string, retry?: { text: string; requestId: string }) {
    const text = (retry?.text ?? explicitText ?? draft).trim();
    if (!text || !sessionId || streaming) return;
    // 重试时不要重复插入用户气泡，沿用上一次那条
    const isRetry = Boolean(retry);
    if (!isRetry) {
      setDraft("");
      if (composerRef.current) composerRef.current.style.height = "auto";
    }
    setError("");
    setFailedSend(null);
    const requestId = retry?.requestId ?? crypto.randomUUID?.() ?? `${Date.now()}`;
    const tempUserId = -Date.now();
    const tempAssistantId = tempUserId - 1;
    const now = new Date().toISOString();
    if (!isRetry) {
      setMessages((prev) => [
        ...prev,
        { id: tempUserId, session_id: sessionId, seq: 0, role: "user", content: text, created_at: now },
        { id: tempAssistantId, session_id: sessionId, seq: 0, role: "assistant", content: "", created_at: now },
      ]);
    } else {
      // 重试：把上一条失败气泡清空重来
      setMessages((prev) =>
        prev.map((item) =>
          item.id === lastFailedAssistantIdRef.current ? { ...item, content: "" } : item,
        ),
      );
    }
    setStreaming(true);
    streamingMessageIdRef.current = tempAssistantId;
    if (messages.length === 0) track("first_message");
    const controller = new AbortController();
    abortRef.current = controller;
    // 流式语音：边收文字边按句合成边播放，首声比整段合成提前数秒
    const speaker =
      voiceOn && companion?.voice_id
        ? createStreamingSpeaker({
            voiceId: companion.voice_id,
            sessionId,
            onFirstAudio: () => setSpeaking(true),
            onIdle: () => {
              setSpeaking(false);
              speakerRef.current = null;
            },
            onError: () => {
              toast.warning("这句语音没出来，继续看文字吧", { id: "voice-fallback" });
            },
          })
        : null;
    speakerRef.current = speaker;
    try {
      await streamEvents(
        `/v1/sessions/${sessionId}/messages`,
        { content: text, client_request_id: requestId },
        {
          onDelta: (delta) => {
            if (!trackedReplyRef.current) {
              trackedReplyRef.current = true;
              track("first_reply");
            }
            // 边收边合成：第一句一到就开始出声
            speaker?.push(delta);
            setMessages((prev) =>
              prev.map((item) =>
                item.id === tempAssistantId || item.id === lastFailedAssistantIdRef.current
                  ? { ...item, content: item.content + delta }
                  : item,
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
            })();
            // 语音已在 onDelta 里逐句播报，这里只需把剩余尾巴送出去
            speaker?.finish();
          },
        },
        controller.signal,
      );
    } catch (event) {
      if (event instanceof DOMException && event.name === "AbortError") {
        /**
         * 用户主动停止。
         *
         * 关键：**不要把服务端结果盖到本地**。
         * 停止时助手回复还没落库，服务端只有用户消息；
         * 一覆盖，用户刚才看到的半截回复就消失了——这比没有「已停止」标记糟糕得多。
         *
         * 所以这里只做一件事：把临时消息的 id 换成正数占位，
         * 让它在这次会话里保持可见，并打上「已停止」标记。
         * 刷新页面后才以服务端为准（那时确实只有用户消息）。
         */
        setMessages((prev) =>
          prev.map((item) =>
            item.role === "assistant" && item.id < 0 && item.content.trim()
              ? { ...item, id: Math.abs(item.id) }
              : item,
          ),
        );
        // 标记跟着 id 一起转正，否则 Set 里存的还是负数，对不上
        const stoppedTemp = streamingMessageIdRef.current;
        if (stoppedTemp !== null && stoppedTemp < 0) {
          setStoppedIds((prev) => {
            if (!prev.has(stoppedTemp)) return prev;
            const next = new Set(prev);
            next.delete(stoppedTemp);
            next.add(Math.abs(stoppedTemp));
            return next;
          });
        }
      } else {
        const message = (event as Error).message || "发送失败";
        setError(message);
        track("error", { error_code: "STREAM_FAILED" });
        // 记住这次失败的原文与幂等 ID，供「重试」复用
        setFailedSend({ text, requestId });
        lastFailedAssistantIdRef.current = tempAssistantId;
                        setMessages((prev) =>
                          prev.map((item) =>
                            item.id === tempAssistantId
                              ? { ...item, content: item.content || "（没有收到回复）" }
                              : item,
                          ),
                        );
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
      streamingMessageIdRef.current = null;
    }
  }

  /**
   * 停止生成：中断请求，并给当前这条回复打上「已停止」标记。
   *
   * 为什么需要标记：原来只是 abort()，消息还保留着半截内容，
   * 但用户看不出它是被自己停掉的、还是模型说到一半断了——
   * 这两种情况感受完全不同，前者无需担心，后者像是出了问题。
   *
   * 实现上记「停止时的消息条数」而不是消息 id：
   * 停止后前端会重拉消息，临时 id 会被服务端真实 id 替换，按 id 记会失效；
   * 而「那一刻已有多少条消息」在重拉后依然能定位到同一条回复。
   * 这样也不用在 effect 里改 state（会多一次渲染）。
   */
  function stop() {
    const target = streamingMessageIdRef.current;
    if (target === null) return;
    /**
     * 只标记「已经生成出内容」的那条。
     *
     * 停止后我们把临时消息的 id 转成正数并留在界面上（见 send 的 AbortError 分支），
     * 所以这里直接按当前 id 记，不需要等重拉、也不受 id 变化影响。
     */
    setStoppedIds((prev) => new Set(prev).add(target));
    abortRef.current?.abort();
  }

  async function regenerate(messageId: number) {
    if (!sessionId || streaming) return;
    track("message_action");
    setError("");
    setStreaming(true);
    streamingMessageIdRef.current = messageId;
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
      streamingMessageIdRef.current = null;
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
      <header className="chat-header">
        <button
          className="icon-btn chat-drawer-btn"
          aria-label="打开会话列表"
          onClick={() => setDrawerOpen(true)}
        >
          <MenuIcon size={18} aria-hidden="true" />
        </button>
        {companion && (
          <div className="avatar chat-avatar">
            {companion.avatar ? (
              <img src={companion.avatar} alt={`${companion.name} 的头像`} />
            ) : (
              companion.persona.name.slice(0, 1)
            )}
          </div>
        )}
        <div className="chat-header-text">
          <h1>{companion ? companion.name : "对话"}</h1>
          <p className="muted">
            {/* 原来显示「人设 v1」，是内部术语；用户需要的是「她是谁」 */}
            {companion
              ? companion.persona.relationship || companion.persona.identity
              : "加载中…"}
          </p>
        </div>
        <div className="chat-header-actions">
          <Link className="btn ghost" to={`/companions/${companionId}/persona`}>
            人设
          </Link>
          <Menu
            triggerLabel="更多操作"
            open={headerMenu}
            onOpenChange={setHeaderMenu}
            trigger={
              <button className="icon-btn" aria-label="更多操作">
                <MoreHorizontal size={18} aria-hidden="true" />
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
      </header>

      <ErrorAlert
        message={
          error ||
          companionQuery.error?.message ||
          voiceQuery.error?.message ||
          summaryQuery.error?.message
        }
        onDismiss={error ? () => setError("") : undefined}
        onRetry={companionQuery.isError ? () => void companionQuery.refetch() : undefined}
      />


      <div className="chat-layout">
        <button
          className="drawer-backdrop"
          aria-label="关闭会话列表"
          data-open={drawerOpen}
          onClick={() => setDrawerOpen(false)}
        />
        <aside data-open={drawerOpen}>
          {/* 抽屉头部：手机上滑出时给一个标题和关闭按钮，
              否则它会顶到最上面、把页面导航盖住一半，看不出这是哪 */}
          <div className="drawer-head">
            <strong>会话</strong>
            <button
              className="icon-btn"
              aria-label="关闭会话列表"
              onClick={() => setDrawerOpen(false)}
            >
              <X size={16} aria-hidden="true" />
            </button>
          </div>
          <button
            className="btn primary"
            style={{ width: "100%" }}
            onClick={() => {
              void newSession();
              setDrawerOpen(false);
            }}
          >
            <Plus size={16} aria-hidden="true" />
            新会话
          </button>
          <div className="session-list" style={{ marginTop: 12 }}>
            {Object.entries(grouped).map(([label, list]) =>
              list.length === 0 ? null : (
                <div key={label} className="session-group">
                  <div className="session-group-label">{label}</div>
                  {list.map((item) => (
                    <div
                      key={item.id}
                      className={`session-item ${item.id === sessionId ? "active" : ""}`}
                      onClick={() => {
                        void selectSession(item.id);
                        setDrawerOpen(false);
                      }}
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
                              className="msg-action-btn"
                              title="重命名"
                              aria-label="重命名会话"
                              onClick={(event) => {
                                event.stopPropagation();
                                setRenamingId(item.id);
                                setRenameDraft(item.title || "");
                              }}
                            >
                              <Pencil size={14} aria-hidden="true" />
                            </button>
                            <button
                              className="msg-action-btn danger-text"
                              title="删除会话"
                              aria-label="删除会话"
                              onClick={(event) => {
                                event.stopPropagation();
                                setConfirm({
                                  kind: "session",
                                  id: item.id,
                                  title: item.title || "未命名会话",
                                });
                              }}
                            >
                              <Trash2 size={14} aria-hidden="true" />
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
            {/* 顶部：加载更早。取满 100 条才显示，避免短会话出现无意义的按钮 */}
            {hasMore && (
              <div className="load-older">
                <button
                  className="btn ghost"
                  disabled={loadingOlder}
                  onClick={() => void loadOlder()}
                >
                  {loadingOlder ? "加载中…" : "加载更早的对话"}
                </button>
              </div>
            )}
            {messages.map((item, index) => {
              const prev = messages[index - 1];
              const newDay = !prev || dayKey(prev.created_at) !== dayKey(item.created_at);
              const isUser = item.role === "user";
              return (
                <Fragment key={item.id}>
                  {newDay && (
                    <div className="date-divider">
                      <span>{formatDayLabel(item.created_at)}</span>
                    </div>
                  )}
                  <div className={`msg-row ${item.role}`}>
                    {/* 只在助手侧显示头像。
                        用户侧原来用 visibility:hidden 占着 40px，
                        自己的气泡左边凭空多出一段空白，看着像没对齐。
                        「我」是唯一的，右对齐 + 粉色气泡已经足够区分。 */}
                    {!isUser && (
                      <span className="msg-avatar" aria-hidden="true">
                        {companion?.avatar ? (
                          <img src={companion.avatar} alt="" />
                        ) : (
                          companion?.persona.name.slice(0, 1) ?? "她"
                        )}
                      </span>
                    )}
                    <div className={`bubble ${item.role}`}>
                      <div className="bubble-content">
                        {item.content || (streaming ? "…" : "")}
                        {stoppedIds.has(item.id) && (
                          <span className="bubble-stopped">（已停止）</span>
                        )}
                      </div>
                      {/* 发送失败：气泡下方直接给原因和重试，不用再打一遍字。
                          重试复用同一个 client_request_id，后端幂等不会重复生成。 */}
                      {failedSend && item.id === lastFailedAssistantIdRef.current && !streaming && (
                        <div className="bubble-failed">
                          <span>这条没发出去</span>
                          <button
                            className="msg-retry"
                            onClick={() => void send(undefined, failedSend)}
                          >
                            <RotateCw size={13} aria-hidden="true" />
                            重试
                          </button>
                          <button
                            className="msg-retry ghost"
                            onClick={() => {
                              // 放弃：把原文放回输入框，气泡删掉
                              setDraft(failedSend.text);
                              setFailedSend(null);
                              lastFailedAssistantIdRef.current = null;
                              setMessages((prev) =>
                                prev.filter(
                                  (m) => m.id !== item.id && !(m.role === "user" && m.id < 0),
                                ),
                              );
                            }}
                          >
                            重新写
                          </button>
                        </div>
                      )}
                      <div className="bubble-meta">
                        <span>{clockTime(item.created_at)}</span>
                        <span className="msg-actions">
                          <button
                            className="msg-action-btn"
                            title="复制"
                            aria-label="复制这条消息"
                            onClick={() => void copy(item.content)}
                          >
                            <Copy size={13} aria-hidden="true" />
                          </button>
                          {item.role === "assistant" && item.id === lastAssistantId && !streaming && (
                            <button
                              className="msg-action-btn"
                              title="重新生成"
                              aria-label="重新生成这条回复"
                              onClick={() => void regenerate(item.id)}
                            >
                              <RotateCw size={13} aria-hidden="true" />
                            </button>
                          )}
                          <button
                            className="msg-action-btn danger-text"
                            title="删除"
                            aria-label="删除这条消息"
                            onClick={() =>
                              setConfirm({
                                kind: "message",
                                id: item.id,
                                title: item.content.slice(0, 20),
                              })
                            }
                          >
                            <Trash2 size={13} aria-hidden="true" />
                          </button>
                        </span>
                      </div>
                      {echoEnabled && echo && echo.messageId === item.id && (
                        <div className="echo">
                          <button className="echo-head" onClick={() => setEchoOpen(!echoOpen)}>
                            她想起了… <span className="muted">{echoOpen ? "收起" : "展开"}</span>
                          </button>
                          {echoOpen && (
                            <ul className="echo-list">
                              {echo.items.map((text, i) => (
                                <li key={i}>{text}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </Fragment>
              );
            })}
            {openerLoading && (
              <div className="msg-row assistant">
                <span className="msg-avatar" aria-hidden="true">
                  {companion?.avatar ? (
                    <img src={companion.avatar} alt="" />
                  ) : (
                    companion?.persona.name.slice(0, 1) ?? "她"
                  )}
                </span>
                <div className="bubble assistant typing">她正在想怎么跟你打招呼…</div>
              </div>
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
              <ArrowDown size={14} aria-hidden="true" />
              回到最新
            </button>
          )}

          <div className="composer">
            {/* 语音开关放进输入行，做成图标按钮。
                原来是输入框下面单独一行文字按钮「语音模式：关」，
                在手机上占掉整整一行，看着像随手挂在底部。 */}
            <button
              className={`icon-btn composer-voice${voiceOn ? " active" : ""}`}
              aria-pressed={voiceOn}
              aria-label={voiceOn ? "关闭语音模式" : "开启语音模式"}
              title={voiceOn ? "关闭语音模式" : "开启语音模式：说话后她会语音回复"}
              onClick={() => {
                if (!voiceAvailable) {
                  toast.info("先到「模型与用量 → 语音」配置火山 AppID 与 Token", { id: "voice-setup" });
                  return;
                }
                if (!voiceOn && !companion?.voice_id) {
                  // 没设音色就不会合成，用户会以为「语音坏了」。这里直接引导去选。
                  toast.warning("这个伴侣还没选音色，选一个才能听到她的声音", {
                    id: "voice-pick",
                    action: {
                      label: "去选音色",
                      onClick: () => navigate(`/companions/${companionId}/persona`),
                    },
                  });
                  return;
                }
                setVoiceOn(!voiceOn);
                if (voiceOn) {
                  stopSpeaking();
                }
              }}
            >
              <Mic size={17} aria-hidden="true" />
            </button>
            <textarea
              ref={composerRef}
              rows={1}
              value={draft}
              placeholder="说点什么…"
              title="Enter 发送，Shift+Enter 换行"
              disabled={!sessionId}
              aria-label="输入消息"
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
              <button className="btn danger composer-send" onClick={stop} aria-label="停止生成">
                停止
              </button>
            ) : (
              <button
                className="btn primary composer-send"
                onClick={() => void send()}
                disabled={!draft.trim()}
                aria-label="发送消息"
              >
                <Send size={17} aria-hidden="true" />
              </button>
            )}
          </div>

          {/* 语音开启后，录音条和状态提示才出现，平时不占位置 */}
          {(voiceOn || speaking) && (
            <div className="composer-extras">
              {voiceOn && (
                <VoiceBar available={voiceAvailable} onTranscribed={(text) => void send(text)} />
              )}
              {speaking && (
                <span className="voice-playing">
                  <span className="muted">她在说话…</span>
                  <button className="btn ghost" onClick={stopSpeaking}>
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
          )}
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















