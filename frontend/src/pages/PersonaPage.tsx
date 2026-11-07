import { useQuery, useQueryClient } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { useState } from "react";
import { toast } from "sonner";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Copy } from "lucide-react";
import { api } from "../api";
import PersonaForm from "../components/PersonaForm";
import ErrorAlert from "../components/ErrorAlert";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import PersonaVersionList from "../components/PersonaVersionList";
import { track } from "../lib/analytics";
import UserProfileForm from "../components/UserProfileForm";
import VoicePicker from "../components/VoicePicker";
import type { Persona } from "../lib/types";

/**
 * 人设页。
 *
 * 2026-11 起改为「原地保存」：
 * 修改人设直接作用于当前伴侣，生成新版本，会话、记忆、头像全部保留。
 * 原来的做法是「改人设 = 新建一个伴侣」（ADR-0001），实际用起来很别扭——
 * 想把她说话方式调冷一点，结果多出一个人，旧对话还留在旧的她身上。
 *
 * 「基于这版再造一个」保留在右上角，作为独立的高级操作，
 * 想造变体时仍然可用，但不再是唯一的修改方式。
 */
export default function PersonaPage() {
  const { id } = useParams();
  const companionId = Number(id);
  const navigate = useNavigate();
  const client = useQueryClient();
  const companionQuery = useQuery(queries.companion(companionId));
  const companion = companionQuery.data;
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  /** 原地保存人设：生成新版本，其他一切不变。 */
  async function save(draft: Persona) {
    setBusy(true);
    setError("");
    try {
      const updated = await api.savePersona(companionId, draft);
      client.setQueryData(queries.companion(companionId).queryKey, updated);
      await client.invalidateQueries({ queryKey: queries.personaVersions(companionId).queryKey });
      track("persona_save");
      toast.success(`已保存为第 ${updated.current_version} 版，下一条回复生效`, {
        id: "persona-saved",
      });
      setEditing(false);
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setBusy(false);
    }
  }

  /** 基于当前人设再造一个伴侣（保留的旧能力）。 */
  async function derive(draft: Persona) {
    setBusy(true);
    setError("");
    try {
      const created = await api.deriveCompanion(companionId, draft);
      track("persona_save");
      navigate(`/companions/${created.id}/chat`);
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!companion) {
    if (companionQuery.isError) {
      return (
        <ErrorAlert
          message={error || companionQuery.error?.message || "人设加载失败"}
          onRetry={() => void companionQuery.refetch()}
        />
      );
    }
    return <Loading lines={4} />;
  }

  return (
    <div>
      <PageHeader
        title="人设"
        description={`${companion.name} · 当前第 ${companion.current_version} 版${companion.derived_from ? " · 衍生伴侣" : ""}`}
        actions={
          <>
            <Link className="btn ghost" to={`/companions/${companionId}/chat`}>
              回到对话
            </Link>
            <button className={editing ? "btn ghost" : "btn primary"} onClick={() => setEditing(!editing)}>
              {editing ? "取消编辑" : "编辑人设"}
            </button>
          </>
        }
      />

      <ErrorAlert message={error} onDismiss={() => setError("")} />

      {editing && (
        <div className="notice" style={{ marginTop: 12 }}>
          改完保存会直接作用于当前伴侣：她的会话、记忆和头像都保留，只是从下一条回复开始换一种说话方式。
          每一步都留版本，改坏了可以还原。
        </div>
      )}

      <div className="card" style={{ marginTop: 12 }}>
        <PersonaForm
          key={`${companionId}-${companion.current_version}-${editing}`}
          formId="persona-form"
          value={companion.persona}
          refinable
          onSubmit={async (draft, intent) => {
            // 表单通过 data-intent 区分「保存」和「衍生」，与创建页一致
            if (intent === "derive") await derive(draft);
            else await save(draft);
          }}
          disabled={!editing || busy}
        />
        {editing && (
          <div className="toolbar">
            <button className="btn primary" disabled={busy} type="submit" form="persona-form">
              {busy ? "保存中…" : "保存人设"}
            </button>
            <button className="btn ghost" disabled={busy} onClick={() => setEditing(false)}>
              放弃修改
            </button>
            {/* 高级操作：想造变体时用，不再是唯一的修改方式 */}
            <button
              className="btn ghost"
              disabled={busy}
              title="用这份人设另建一个伴侣，原伴侣不受影响"
              type="submit"
              form="persona-form"
              data-intent="derive"
            >
              <Copy size={14} aria-hidden="true" />
              基于此版再造一个
            </button>
          </div>
        )}
      </div>

      <PersonaVersionList
        companionId={companionId}
        currentVersion={companion.current_version}
        onRestored={(updated) => {
          client.setQueryData(queries.companion(companionId).queryKey, updated);
          setEditing(false);
        }}
      />

      <div style={{ marginTop: 12 }}>
        <VoicePicker
          companionId={companionId}
          value={companion?.voice_id ?? null}
          onChange={(voiceId) => {
            void (async () => {
              try {
                const updated = await api.setCompanionVoice(companionId, voiceId);
                client.setQueryData(queries.companion(companionId).queryKey, updated);
                toast.success("音色已保存，下一条语音生效", { id: "voice-selected" });
              } catch (event) {
                setError((event as Error).message);
              }
            })();
          }}
        />
      </div>

      <div style={{ marginTop: 12 }}>
        <UserProfileForm
          companionId={companionId}
          title="和她聊时的我"
          description="只对当前伴侣生效；留空的字段会沿用「我的身份」里的通用信息。"
        />
      </div>
    </div>
  );
}
