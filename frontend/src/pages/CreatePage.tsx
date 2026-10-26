import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import PersonaForm from "../components/PersonaForm";
import TrialChat from "../components/TrialChat";
import type { Persona, Template } from "../types";

export default function CreatePage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"draft" | "template">("draft");
  const [description, setDescription] = useState("");
  const [persona, setPersona] = useState<Persona | null>(null);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [trialOpen, setTrialOpen] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .templates()
      .then(setTemplates)
      .catch((event) => setError((event as Error).message));
  }, []);

  async function generate() {
    if (description.trim().length < 4) {
      setError("请再多说几个字，方便生成人设");
      return;
    }
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

  async function create() {
    if (!persona) return;
    setBusy(true);
    setError("");
    try {
      const created = selected
        ? await api.createFromTemplate(selected, persona.name)
        : await api.createCompanion(persona);
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

      {error && <div className="alert">{error}</div>}

      {mode === "draft" && (
        <div className="card">
          <label htmlFor="desc">你想要一个什么样的人？</label>
          <textarea
            id="desc"
            value={description}
            placeholder="例如：温柔但偶尔毒舌的心理学学姐，比我大两岁，晚上常熬夜"
            onChange={(event) => setDescription(event.target.value)}
          />
          <div className="toolbar">
            <button className="primary" disabled={busy} onClick={() => void generate()}>
              {busy ? "生成中…" : persona ? "换一版" : "生成人设"}
            </button>
          </div>
        </div>
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
            value={persona}
            onChange={(next) => {
              setPersona(next);
              setSelected(null); // 改过任意字段就按自定义人设创建
            }}
            disabled={busy}
          />
          <div className="toolbar">
            <button className="primary" disabled={busy} onClick={() => void create()}>
              {busy ? "创建中…" : "创建并开始聊天"}
            </button>
            <button className="ghost" disabled={busy} onClick={() => setTrialOpen(true)}>
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

      {trialOpen && persona && (
        <TrialChat persona={persona} onClose={() => setTrialOpen(false)} />
      )}
    </div>
  );
}

