import { useQuery } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { descriptionSchema } from "../lib/forms";
import FieldError from "../components/FieldError";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import PersonaForm from "../components/PersonaForm";
import TrialChat from "../components/TrialChat";
import PersonaImportButton from "../components/PersonaImport";
import { track } from "../lib/analytics";
import type { Persona, Template } from "../lib/types";

export default function CreatePage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"draft" | "template">("draft");
  const { register, handleSubmit, formState: { errors } } = useForm({ resolver: zodResolver(descriptionSchema), defaultValues: { description: "" } });
  const [persona, setPersona] = useState<Persona | null>(null);
  const templatesQuery = useQuery(queries.templates());
  const templates = templatesQuery.data ?? [];
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [trialPersona, setTrialPersona] = useState<Persona | null>(null);
  const [error, setError] = useState("");

  async function generate({ description }: { description: string }) {
    track("create_start");
    setBusy(true);
    setError("");
    try {
      setPersona(await api.draftPersona(description.trim()));
      setSelected(null);
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function pickTemplate(template: Template) {
    setSelected(template.key);
    setPersona(template.persona);
    setMode("template");
    setError("");
  }

  async function create(persona: Persona) {
    setBusy(true);
    setError("");
    try {
      const created = selected
        ? await api.createFromTemplate(selected, persona.name)
        : await api.createCompanion(persona);
      track("create_success");
      navigate(`/companions/${created.id}/chat`);
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h1>创建伴侣</h1>
      <p className="muted">一句话描述，或从模板开始；生成后可以逐项修改。</p>

      <div className="toolbar">
        <PersonaImportButton onCreated={(created) => navigate(`/companions/${created.id}/chat`)} />
        <button
          className={mode === "draft" ? "primary" : "ghost"}
          onClick={() => setMode("draft")}
        >
          一句话生成
        </button>
        <button
          className={mode === "template" ? "primary" : "ghost"}
          onClick={() => setMode("template")}
        >
          从模板开始
        </button>
      </div>

      {(error || templatesQuery.error) && <div className="alert">{error || templatesQuery.error?.message}</div>}

      {mode === "draft" && (
        <form className="card" noValidate onSubmit={handleSubmit(generate)}>
          <label htmlFor="desc">你想要一个什么样的人？</label>
          <textarea
            id="desc"
            {...register("description")}
            placeholder="例如：温柔但偶尔毒舌的心理学学姐，比我大两岁，晚上常熬夜"
            aria-invalid={!!errors.description}
            aria-describedby="desc-error"
          />
          <FieldError id="desc-error" error={errors.description} />
          <div className="toolbar">
            <button className="primary" disabled={busy} type="submit">
              {busy ? "生成中…" : persona ? "换一版" : "生成人设"}
            </button>
          </div>
        </form>
      )}

      {mode === "template" && (
        <div>
          <p className="muted">选一个模板，创建后只改名字也能直接聊。</p>
          <div className="grid">
            {templates.map((template) => (
              <button
                key={template.key}
                className="card"
                style={{
                  textAlign: "left",
                  borderColor: selected === template.key ? "var(--accent)" : undefined,
                }}
                onClick={() => pickTemplate(template)}
              >
                <h3>{template.name}</h3>
                <p className="muted">{template.category}</p>
                <p className="muted">{template.tagline}</p>
              </button>
            ))}
          </div>
        </div>
      )}

      {persona && (
        <div className="card" style={{ marginTop: 16 }}>
          <h2>{selected ? "预览模板人设" : "生成的人设（可修改）"}</h2>
          <PersonaForm
            formId="create-persona"
            value={persona}
            onEdit={() => setSelected(null)}
            onSubmit={async (next, intent) => {
              if (intent === "trial") setTrialPersona(next);
              else await create(next);
            }}
            disabled={busy}
          />
          <div className="toolbar">
            <button className="primary" disabled={busy} type="submit" form="create-persona">
              {busy ? "创建中…" : "创建并开始聊天"}
            </button>
            <button className="ghost" disabled={busy} type="submit" form="create-persona" data-intent="trial">
              先试聊 3 句
            </button>
            <button className="ghost" disabled={busy} onClick={() => setPersona(null)}>
              重新选择
            </button>
          </div>
          {selected && (
            <p className="muted">提示：从模板创建时会沿用模板人设，仅覆盖名字；改任意字段即按自定义人设创建。</p>
          )}
        </div>
      )}

      {trialPersona && (
        <TrialChat persona={trialPersona} onClose={() => setTrialPersona(null)} />
      )}
    </div>
  );
}





