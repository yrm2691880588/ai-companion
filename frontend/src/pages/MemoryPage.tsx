import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import type { Companion, Memory } from "../types";

export default function MemoryPage() {
  const { id } = useParams();
  const companionId = Number(id);
  const [companion, setCompanion] = useState<Companion | null>(null);
  const [items, setItems] = useState<Memory[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState(true);

  async function reload() {
    try {
      const [loaded, memories] = await Promise.all([
        api.companion(companionId),
        api.memories(companionId),
      ]);
      setCompanion(loaded);
      setEnabled(loaded.memory_enabled);
      setItems(memories);
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [companionId]);

  async function toggle() {
    try {
      const next = !enabled;
      await api.memoryEnabled(companionId, next);
      setEnabled(next);
    } catch (event) {
      setError((event as Error).message);
    }
  }

  async function remove(memory: Memory) {
    if (!window.confirm(`删除这条记忆？\n\n[${memory.type_label}] ${memory.content}`)) return;
    try {
      await api.deleteMemory(memory.id);
      setItems((prev) => prev.filter((item) => item.id !== memory.id));
    } catch (event) {
      setError((event as Error).message);
    }
  }

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>记忆</h1>
          <p className="muted">{companion ? `${companion.name} 记住了什么` : "加载中…"}</p>
        </div>
        <div className="toolbar">
          <Link className="btn ghost" to={`/companions/${companionId}/chat`}>
            回到对话
          </Link>
          <button className={enabled ? "ghost" : "primary"} onClick={() => void toggle()}>
            {enabled ? "关闭记忆" : "开启记忆"}
          </button>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}
      {!enabled && (
        <div className="notice">记忆已关闭：不会自动抽取，也不会在对话里调用已有记忆。</div>
      )}

      {loading ? (
        <p className="muted">加载中…</p>
      ) : items.length === 0 ? (
        <div className="card">
          <h3>还没有记忆</h3>
          <p className="muted">聊天时提到自己的喜好、经历、习惯或约定，伴侣会自动记下来。</p>
        </div>
      ) : (
        <div className="grid" style={{ marginTop: 12 }}>
          {items.map((memory) => (
            <div className="card" key={memory.id}>
              <span className="chip">{memory.type_label}</span>
              <p style={{ margin: "8px 0", lineHeight: 1.6 }}>{memory.content}</p>
              {memory.quote && <p className="muted">来源：「{memory.quote}」</p>}
              <p className="muted">置信度 {Math.round(memory.confidence * 100)}%</p>
              <div className="toolbar">
                <button className="danger" onClick={() => void remove(memory)}>
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
