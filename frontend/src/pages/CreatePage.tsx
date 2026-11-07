import { useQuery } from "@tanstack/react-query";
import { queries } from "../lib/queries";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { descriptionSchema } from "../lib/forms";
import FieldError from "../components/FieldError";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import PersonaForm from "../components/PersonaForm";
import TrialChat from "../components/TrialChat";
import PersonaImportButton from "../components/PersonaImport";
import PageHeader from "../components/PageHeader";
import ErrorAlert from "../components/ErrorAlert";
import { track } from "../lib/analytics";
import type { Persona, Template } from "../lib/types";

/**
 * 创建伴侣。
 *
 * 结构上分三步走，用户始终知道自己在第几步：
 * 1. 描述（一句话，或从模板挑）—— 首屏必须有内容，不能只有一个输入框；
 * 2. 调整人设（生成后逐项改）；
 * 3. 确认（试聊一句，或直接创建）。
 *
 * 「导入人设」是换机迁移才用的低频操作，从原来的三个平级 Tab 里
 * 挪到标题栏右侧，不占主要创建方式的位置。
 */

/** 示例描述：点一下直接填进输入框，解决「不知道写什么」。 */
const EXAMPLES = [
  "温柔但偶尔毒舌的心理学学姐，比我大两岁，晚上常熬夜",
  "话不多但很会照顾人的咖啡店老板，喜欢在雨天讲故事",
  "一起打游戏认识的队友，说话直、爱开玩笑，其实很细心",
];

const STEPS = [
  { title: "描述她", desc: "一句话说清性格、身份、和你的关系" },
  { title: "调整人设", desc: "生成后可以逐项改，改到像为止" },
  { title: "试聊确认", desc: "先聊三句，觉得像再创建" },
];

export default function CreatePage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"draft" | "template">("draft");
  const { register, handleSubmit, setValue, control, formState: { errors } } = useForm({
    resolver: zodResolver(descriptionSchema),
    defaultValues: { description: "" },
  });
  // useWatch 代替 watch()：后者每次渲染都返回新函数，lint 会告警且可能引发多余重渲染
  const description = useWatch({ control, name: "description" }) ?? "";
  const [persona, setPersona] = useState<Persona | null>(null);
  const templatesQuery = useQuery(queries.templates());
  const templates = templatesQuery.data ?? [];
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [trialPersona, setTrialPersona] = useState<Persona | null>(null);
  const [error, setError] = useState("");

  async function generate({ description: text }: { description: string }) {
    track("create_start");
    setBusy(true);
    setError("");
    try {
      setPersona(await api.draftPersona(text.trim()));
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

  async function create(next: Persona) {
    setBusy(true);
    setError("");
    try {
      const created = selected
        ? await api.createFromTemplate(selected, next.name)
        : await api.createCompanion(next);
      track("create_success");
      navigate(`/companions/${created.id}/chat`);
    } catch (event) {
      setError((event as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // 已经在调整人设阶段：收起步骤说明，把空间让给表单
  const adjusting = persona !== null;

  return (
    <div>
      <PageHeader
        title="创建伴侣"
        description="一句话描述，或从模板开始；生成后可以逐项修改。"
        actions={<PersonaImportButton onCreated={(created) => navigate(`/companions/${created.id}/chat`)} />}
      />

      {/* 首屏步骤说明：原来这块是空的，用户看到一个大输入框加一片空白 */}
      {!adjusting && (
        <div className="create-steps">
          {STEPS.map((step, index) => (
            <div className="create-step" key={step.title}>
              <span className="create-step-num" aria-hidden="true">
                {index + 1}
              </span>
              <div>
                <strong>{step.title}</strong>
                <span className="muted">{step.desc}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {!adjusting && (
        <div className="tabs" role="tablist" aria-label="创建方式">
          <button
            role="tab"
            aria-selected={mode === "draft"}
            className={mode === "draft" ? "tab active" : "tab"}
            onClick={() => setMode("draft")}
          >
            一句话生成
          </button>
          <button
            role="tab"
            aria-selected={mode === "template"}
            className={mode === "template" ? "tab active" : "tab"}
            onClick={() => setMode("template")}
          >
            从模板开始
          </button>
        </div>
      )}

      <ErrorAlert
        message={error || templatesQuery.error?.message}
        onDismiss={error ? () => setError("") : undefined}
        onRetry={templatesQuery.error ? () => void templatesQuery.refetch() : undefined}
      />

      {mode === "draft" && !adjusting && (
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

          {/* 示例 chips：点一下直接填入，省去「不知道怎么写」的停顿 */}
          <div className="example-chips">
            <span className="muted">不知道写什么？试试：</span>
            {EXAMPLES.map((example) => (
              <button
                key={example}
                type="button"
                className="chip-button"
                onClick={() => setValue("description", example, { shouldValidate: true })}
              >
                {example.length > 18 ? `${example.slice(0, 18)}…` : example}
              </button>
            ))}
          </div>

          <div className="toolbar">
            <button className="primary" disabled={busy || !description.trim()} type="submit">
              {busy ? "生成中…" : persona ? "换一版" : "生成人设"}
            </button>
          </div>
        </form>
      )}

      {mode === "template" && !adjusting && (
        <div>
          <p className="muted">选一个模板，创建后只改名字也能直接聊。</p>
          <div className="grid">
            {templates.map((template) => (
              <button
                key={template.key}
                className={`card template-card${selected === template.key ? " active" : ""}`}
                onClick={() => pickTemplate(template)}
              >
                <span className="template-avatar" aria-hidden="true">
                  {template.name.slice(0, 1)}
                </span>
                <div className="template-body">
                  <h3>{template.name}</h3>
                  <span className="chip">{template.category}</span>
                  <p className="muted">{template.tagline}</p>
                  {/* 示例开场白：让用户在选之前就知道「她会怎么说话」 */}
                  {template.persona?.example_openers?.[0] && (
                    <p className="template-line">「{template.persona.example_openers[0]}」</p>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {adjusting && persona && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
            <h2 style={{ margin: 0 }}>{selected ? "预览模板人设" : "生成的人设（可修改）"}</h2>
            <button className="btn ghost" disabled={busy} onClick={() => setPersona(null)}>
              重新选择
            </button>
          </div>
          <p className="muted">下面是她的设定，逐项改到像为止；改完可以试聊三句再决定。</p>
          <PersonaForm
            formId="create-persona"
            value={persona}
            onEdit={() => setSelected(null)}
            refinable
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
