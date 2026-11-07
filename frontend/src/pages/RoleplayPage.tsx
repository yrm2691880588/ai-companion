import { useQuery } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Send } from "lucide-react";
import { api, streamEvents } from "../api";
import PageHeader from "../components/PageHeader";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import type { Review, Run } from "../lib/types";

interface Line {
  id: number;
  role: "user" | "assistant";
  content: string;
}

export default function RoleplayPage() {
  const { id } = useParams();
  const companionId = Number(id);
  const companionQuery = useQuery(queries.companion(companionId));
  const scenariosQuery = useQuery(queries.scenarios());
  const companion = companionQuery.data;
  const scenarios = scenariosQuery.data ?? [];
  const [run, setRun] = useState<Run | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  async function start(key: string) {
    setError("");
    setReview(null);
    try {
      const started = await api.startRoleplay(companionId, key);
      setRun(started);
      setLines([{ id: -1, role: "assistant", content: started.opening }]);
    } catch (event) {
      setError((event as Error).message);
    }
  }

  async function send() {
    const text = draft.trim();
    if (!text || !run || streaming) return;
    if (run.turns_played >= run.max_turns) {
      setError("已达到回合上限，请点击「结束并复盘」");
      return;
    }
    setDraft("");
    const userId = -Date.now();
    const assistantId = userId - 1;
    setLines((prev) => [
      ...prev,
      { id: userId, role: "user", content: text },
      { id: assistantId, role: "assistant", content: "" },
    ]);
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamEvents(
        `/v1/roleplay/${run.id}/turns`,
        { content: text },
        {
          onDelta: (delta) =>
            setLines((prev) =>
              prev.map((line) =>
                line.id === assistantId ? { ...line, content: line.content + delta } : line,
              ),
            ),
          onError: (err) => setError(err.message),
          onDone: () => {
            void (async () => {
              const latest = await api.getRun(run.id);
              setRun(latest);
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

  async function finish() {
    if (!run) return;
    setError("");
    try {
      const finished = await api.finishRoleplay(run.id);
      setRun(finished);
      setReview(finished.review ?? null);
    } catch (event) {
      setError((event as Error).message);
    }
  }

  return (
    <div>
      <PageHeader
        title="演练"
        description={
          companion
            ? `${companion.name} 陪你练，结束后会跳出角色给复盘。`
            : "加载中…"
        }
        actions={
          <Link className="btn ghost" to={`/companions/${companionId}/chat`}>
            回到对话
          </Link>
        }
      />

      <ErrorAlert
        message={error || companionQuery.error?.message || scenariosQuery.error?.message}
        onDismiss={error ? () => setError("") : undefined}
        onRetry={scenariosQuery.isError ? () => void scenariosQuery.refetch() : undefined}
      />

      {!run && scenariosQuery.isPending && <Loading lines={3} avatar label="加载场景" card />}

      {!run && !scenariosQuery.isPending && (
        <div className="grid scenario-grid" style={{ marginTop: 16 }}>
          {scenarios.map((scenario) => (
            <div className="card scenario-card" key={scenario.key}>
              <div className="scenario-head">
                <span className="chip">{scenario.category}</span>
                {/* 难度用圆点表示，比「难度 3/5」更直观 */}
                <span className="difficulty" title={`难度 ${scenario.difficulty}/5`}>
                  {Array.from({ length: 5 }, (_, index) => (
                    <span
                      key={index}
                      className={index < scenario.difficulty ? "dot on" : "dot"}
                      aria-hidden="true"
                    />
                  ))}
                  <span className="sr-only">难度 {scenario.difficulty}/5</span>
                </span>
              </div>
              <h3>{scenario.title}</h3>
              <dl className="scenario-meta">
                <dt>她扮演</dt>
                <dd>{scenario.role}</dd>
                <dt>你的目标</dt>
                <dd>{scenario.goal}</dd>
              </dl>
              <button className="btn primary" onClick={() => void start(scenario.key)}>
                开始演练
              </button>
            </div>
          ))}
        </div>
      )}

      {run && (
        <div style={{ marginTop: 16 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <p className="muted">
              {/* 原来直接显示 scenario_key 和 status 原始英文值 */}
              第 {run.turns_played}/{run.max_turns} 轮
              {run.status === "active" ? " · 进行中" : run.status === "finished" ? " · 已结束" : ""}
            </p>
            <div className="toolbar">
              {!review && (
                <button className="btn primary" onClick={() => void finish()}>
                  结束并复盘
                </button>
              )}
              <button
                className="btn ghost"
                onClick={() => {
                  setRun(null);
                  setLines([]);
                  setReview(null);
                }}
              >
                换一个场景
              </button>
            </div>
          </div>

          <div className="messages" style={{ marginTop: 8 }}>
            {lines.map((line) => (
              <div key={line.id} className={`bubble ${line.role}`}>
                {line.content || (streaming ? "…" : "")}
              </div>
            ))}
          </div>

          {!review && (
            <div className="composer">
              <input
                value={draft}
                placeholder="轮到你说了…"
                aria-label="输入你的回应"
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void send();
                  }
                }}
              />
              {streaming ? (
                <button className="btn danger composer-send" onClick={() => abortRef.current?.abort()} aria-label="停止">
                  停止
                </button>
              ) : (
                <button
                  className="btn primary composer-send"
                  onClick={() => void send()}
                  disabled={!draft.trim()}
                  aria-label="发送"
                >
                  <Send size={17} aria-hidden="true" />
                </button>
              )}
            </div>
          )}

          {review && <ReviewPanel review={review} />}
        </div>
      )}
    </div>
  );
}

function ReviewPanel({ review }: { review: Review }) {
  return (
    <div className="card" style={{ marginTop: 14 }}>
      <h2>复盘</h2>
      {review.summary && <p style={{ lineHeight: 1.7 }}>{review.summary}</p>}
      {review.scores && (
        <div className="review-grid">
          {Object.entries(review.scores).map(([key, value]) => (
            <div className="score" key={key}>
              <strong>{value}</strong>
              <span className="muted">{labelOf(key)}</span>
            </div>
          ))}
        </div>
      )}
      {review.highlights && review.highlights.length > 0 && (
        <>
          <h3>做得好的</h3>
          <ul>
            {review.highlights.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}
      {review.improvements && review.improvements.length > 0 && (
        <>
          <h3>可以改进</h3>
          <ul>
            {review.improvements.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}
      {review.sample_lines && review.sample_lines.length > 0 && (
        <>
          <h3>可以这样说</h3>
          <ul>
            {review.sample_lines.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}

function labelOf(key: string): string {
  const labels: Record<string, string> = {
    clarity: "清晰度",
    empathy: "共情",
    structure: "结构",
    confidence: "自信",
  };
  return labels[key] ?? key;
}

