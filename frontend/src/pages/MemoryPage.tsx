import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import type { Memory } from "../lib/types";

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diff / 86_400_000);
  if (days < 1) return "今天";
  if (days < 30) return `${days} 天前`;
  const date = new Date(iso);
  return `${date.getFullYear()} 年 ${date.getMonth() + 1} 月`;
}

export default function MemoryPage() {
  const { id } = useParams();
  const companionId = Number(id);
  const client = useQueryClient();
  const companionQuery = useQuery(queries.companion(companionId));
  const memoriesQuery = useQuery(queries.memories(companionId));
  const companion = companionQuery.data;
  const items = memoriesQuery.data ?? [];
  const enabled = companion?.memory_enabled ?? true;
  const loading = companionQuery.isPending || memoriesQuery.isPending;
  const [error, setError] = useState("");
  const loadError = companionQuery.error?.message || memoriesQuery.error?.message;
  const toggleMutation = useMutation({
    mutationFn: (next: boolean) => api.memoryEnabled(companionId, next),
    onSuccess: (_data, next) => client.setQueryData(queries.companion(companionId).queryKey, old => old ? { ...old, memory_enabled: next } : old),
  });

  async function toggle() {
    try {
      const next = !enabled;
      await toggleMutation.mutateAsync(next);
    } catch (event) {
      setError((event as Error).message);
    }
  }

  async function remove(memory: Memory) {
    if (!window.confirm(`删除这条记忆？\n\n[${memory.type_label}] ${memory.content}`)) return;
    try {
      await api.deleteMemory(memory.id);
      client.setQueryData(queries.memories(companionId).queryKey, old => old?.filter(item => item.id !== memory.id));
    } catch (event) {
      setError((event as Error).message);
    }
  }

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>她记得的事</h1>
          <p className="muted">
            {companion ? `${companion.name} 记住的关于你的事` : "加载中…"}
          </p>
          <p className="muted">
            聊天时她会自动参考这里的内容；记错了可以删掉，删掉后就不再使用。
          </p>
        </div>
        <div className="toolbar">
          <Link className="btn ghost" to={`/companions/${companionId}/chat`}>
            回到对话
          </Link>
          <button disabled={!companion || toggleMutation.isPending} className={enabled ? "ghost" : "primary"} onClick={() => void toggle()}>
            {enabled ? "关闭记忆" : "开启记忆"}
          </button>
        </div>
      </div>

      {(error || loadError) && <div className="alert">{error || loadError}</div>}
      {!enabled && (
        <div className="notice">
          记忆已关闭：不会自动抽取新记忆，也不会在对话里调用已有记忆；已经记住的内容仍然保留。
        </div>
      )}

      {loading ? (
        <p className="muted">加载中…</p>
      ) : loadError ? null : items.length === 0 ? (
        <div className="card">
          <h3>还没有记忆</h3>
          <p className="muted">聊天时提到自己的喜好、经历、习惯或约定，伴侣会自动记下来。</p>
        </div>
      ) : (
        <div className="grid" style={{ marginTop: 12 }}>
          {items.map((memory) => (
            <div className="card" key={memory.id}>
              <span className="chip">{memory.type_label}</span>
              <p style={{ margin: "8px 0", lineHeight: 1.6 }}>她记得：{memory.content}</p>
              {memory.quote && <p className="muted">你曾说过：「{memory.quote}」</p>}
              <p className="muted">
                {memory.confidence >= 0.8 ? "确定" : "大概"} · {relativeTime(memory.created_at)}
              </p>
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


