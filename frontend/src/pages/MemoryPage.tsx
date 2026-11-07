import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Brain, CloudOff, MoreHorizontal, Trash2 } from "lucide-react";
import { api } from "../api";
import EmptyState from "../components/EmptyState";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import Menu from "../components/Menu";
import Modal from "../components/Modal";
import PageHeader from "../components/PageHeader";
import { relativeTime } from "../lib/format";
import type { Memory } from "../lib/types";

/**
 * 她记得的事。
 *
 * 两处主要改动：
 * 1. 删除从「每张卡占一整行的红色按钮」收进右上角「⋯」菜单——
 *    删除是不可逆操作，不该比内容本身更显眼；
 * 2. 用统一确认弹窗替换 window.confirm，和全站其他删除保持一致。
 */
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
  const [menuId, setMenuId] = useState<number | null>(null);
  const [confirmTarget, setConfirmTarget] = useState<Memory | null>(null);
  const [deleting, setDeleting] = useState(false);

  const toggleMutation = useMutation({
    mutationFn: (next: boolean) => api.memoryEnabled(companionId, next),
    onSuccess: (_data, next) =>
      client.setQueryData(queries.companion(companionId).queryKey, (old) =>
        old ? { ...old, memory_enabled: next } : old,
      ),
  });

  async function toggle() {
    try {
      await toggleMutation.mutateAsync(!enabled);
    } catch (event) {
      setError((event as Error).message);
    }
  }

  async function confirmDelete() {
    if (!confirmTarget) return;
    setDeleting(true);
    try {
      await api.deleteMemory(confirmTarget.id);
      client.setQueryData(queries.memories(companionId).queryKey, (old) =>
        old?.filter((item) => item.id !== confirmTarget.id),
      );
      setConfirmTarget(null);
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="她记得的事"
        description={
          companion
            ? `${companion.name} 记住的关于你的事。聊天时她会自动参考这里的内容；记错了可以删掉。`
            : "加载中…"
        }
        actions={
          <>
            <Link className="btn ghost" to={`/companions/${companionId}/chat`}>
              回到对话
            </Link>
            <button
              disabled={!companion || toggleMutation.isPending}
              className={enabled ? "btn ghost" : "btn primary"}
              onClick={() => void toggle()}
            >
              {enabled ? "关闭记忆" : "开启记忆"}
            </button>
          </>
        }
      />

      <ErrorAlert
        message={error || loadError}
        onDismiss={error ? () => setError("") : undefined}
        onRetry={memoriesQuery.isError ? () => void memoriesQuery.refetch() : undefined}
      />
      {!enabled && (
        <div className="notice">
          记忆已关闭：不会自动抽取新记忆，也不会在对话里调用已有记忆；已经记住的内容仍然保留。
        </div>
      )}

      {loading ? (
        <Loading lines={3} label="加载记忆" card />
      ) : loadError ? (
        <EmptyState
          icon={CloudOff}
          title="没能加载记忆"
          description="可能是服务暂时不可用，也可能是网络断了。"
          action={
            <button className="btn primary" onClick={() => void memoriesQuery.refetch()}>
              重新加载
            </button>
          }
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={Brain}
          title="还没有记忆"
          description="聊天时提到自己的喜好、经历、习惯或约定，她会自动记下来。"
          action={
            <Link className="btn primary" to={`/companions/${companionId}/chat`}>
              去聊几句
            </Link>
          }
        />
      ) : (
        <>
          <p className="muted" style={{ marginTop: 16 }}>
            共 {items.length} 条
          </p>
          <div className="grid memory-grid">
            {items.map((memory) => (
              <div className="card memory-card" key={memory.id}>
                <div className="memory-head">
                  <span className="chip">{memory.type_label}</span>
                  <Menu
                    triggerLabel="更多操作"
                    open={menuId === memory.id}
                    onOpenChange={(open) => setMenuId(open ? memory.id : null)}
                    trigger={
                      <button
                        className="msg-action-btn"
                        aria-label="这条记忆的更多操作"
                        onClick={() => setMenuId(memory.id)}
                      >
                        <MoreHorizontal size={16} aria-hidden="true" />
                      </button>
                    }
                    items={[
                      {
                        key: "delete",
                        label: "删除这条记忆",
                        danger: true,
                        opensModal: true,
                        onSelect: () => setConfirmTarget(memory),
                      },
                    ]}
                  />
                </div>
                <p className="memory-content">{memory.content}</p>
                {memory.quote && (
                  <p className="memory-quote">你曾说过：「{memory.quote}」</p>
                )}
                <p className="memory-meta">
                  {memory.confidence >= 0.8 ? "确定" : "大概"} ·{" "}
                  {relativeTime(memory.created_at)}
                </p>
              </div>
            ))}
          </div>
        </>
      )}

      {confirmTarget && (
        <Modal
          open
          onClose={() => !deleting && setConfirmTarget(null)}
          title="删除这条记忆"
          description="删掉后她就不会再用这条信息，且不可恢复。"
          preventClose={deleting}
          footer={
            <>
              <button className="danger" disabled={deleting} onClick={() => void confirmDelete()}>
                <Trash2 size={15} aria-hidden="true" />
                {deleting ? "删除中…" : "确认删除"}
              </button>
              <button className="ghost" disabled={deleting} onClick={() => setConfirmTarget(null)}>
                取消
              </button>
            </>
          }
        >
          <p className="muted">
            [{confirmTarget.type_label}] {confirmTarget.content}
          </p>
        </Modal>
      )}
    </div>
  );
}
