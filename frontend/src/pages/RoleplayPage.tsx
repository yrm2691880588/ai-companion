import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, streamEvents } from "../api";
import type { Companion, Review, Run, Scenario } from "../lib/types";

interface Line {
  id: number;
  role: "user" | "assistant";
  content: string;
}

export default function RoleplayPage() {
  const { id } = useParams();
  const companionId = Number(id);
  const [companion, setCompanion] = useState<Companion | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState("");
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [loaded, list] = await Promise.all([
          api.companion(companionId),
          api.scenarios(),
        ]);
        setCompanion(loaded);
        setScenarios(list);
      } catch (event) {
        setError((event as Error).message);
      }
    })();
  }, [companionId]);

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
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>演练</h1>
          <p className="muted">
            {companion ? `${companion.name} 陪你练` : "加载中…"} · 结束后会跳出角色给复盘
          </p>
        </div>
        <Link className="btn ghost" to={`/companions/${companionId}/chat`}>
          回到对话
        </Link>
      </div>

      {error && <div className="alert">{error}</div>}

      {!run && (
        <div className="grid" style={{ marginTop: 12 }}>
          {scenarios.map((scenario) => (
            <div className="card" key={scenario.key}>
              <span className="chip">
                {scenario.category} · 难度 {scenario.difficulty}/5
              </span>
              <h3 style={{ marginTop: 8 }}>{scenario.title}</h3>
              <p className="muted">AI 扮演：{scenario.role}</p>
              <p className="muted">你的目标：{scenario.goal}</p>
              <div className="toolbar">
                <button className="primary" onClick={() => void start(scenario.key)}>
                  开始演练
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {run && (
        <div style={{ marginTop: 12 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <p className="muted">
              场景 {run.scenario_key} · 已进行 {run.turns_played}/{run.max_turns} 轮 · 状态{" "}
              {run.status}
            </p>
            <div className="toolbar">
              {!review && (
                <button className="primary" onClick={() => void finish()}>
                  结束并复盘
                </button>
              )}
              <button
                className="ghost"
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
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void send();
                  }
                }}
              />
              {streaming ? (
                <button className="danger" onClick={() => abortRef.current?.abort()}>
                  停止
                </button>
              ) : (
                <button className="primary" onClick={() => void send()}>
                  发送
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

