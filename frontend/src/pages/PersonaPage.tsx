import { useQuery, useQueryClient } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { useState } from "react";
import { toast } from "sonner";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import PersonaForm from "../components/PersonaForm";
import { track } from "../lib/analytics";
import UserProfileForm from "../components/UserProfileForm";
import VoicePicker from "../components/VoicePicker";
import type { Persona } from "../lib/types";

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
    return <p className="muted">{error || companionQuery.error?.message || "加载中…"}</p>;
  }

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>人设</h1>
          <p className="muted">
            {companion.name} · 当前 v{companion.current_version}
            {companion.derived_from ? " · 衍生伴侣" : ""}
          </p>
        </div>
        <div className="toolbar">
          <Link className="btn ghost" to={`/companions/${companionId}/chat`}>
            回到对话
          </Link>
          <button className={editing ? "ghost" : "primary"} onClick={() => setEditing(!editing)}>
            {editing ? "取消编辑" : "编辑人设"}
          </button>
        </div>
      </div>

      {error && <div className="alert">{error}</div>}

      <div className="notice" style={{ marginTop: 12 }}>
        修改后不会覆盖当前伴侣，而是用这版人设创建一个新伴侣；原来的会话、记忆和头像都保持不变。
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <PersonaForm
          key={`${companionId}-${editing}`}
          formId="derive-persona"
          value={companion.persona}
          onSubmit={derive}
          disabled={!editing || busy}
        />
      </div>

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

      {editing && (
        <div className="toolbar">
          <button className="primary" disabled={busy} type="submit" form="derive-persona">
            {busy ? "创建中…" : "用这版人设创建新伴侣"}
          </button>
          <button
            className="ghost"
            disabled={busy}
            onClick={() => {
              setEditing(false);
            }}
          >
            放弃修改
          </button>
        </div>
      )}
    </div>
  );
}






