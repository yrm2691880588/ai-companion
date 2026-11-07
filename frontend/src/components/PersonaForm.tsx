import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";
import { nullableNumber, personaFormSchema, personaFormValues } from "../lib/forms";
import { personaFields } from "../lib/form-fields.generated";
import type { Persona } from "../lib/types";
import FieldError from "./FieldError";
import PersonaRefineButton from "./PersonaRefineButton";

interface Props {
  value: Persona;
  formId: string;
  onSubmit: (persona: Persona, intent?: string) => void | Promise<void>;
  onEdit?: () => void;
  disabled?: boolean;
  /** 为 true 时每个文本字段旁显示「AI 帮我改」。创建流程里开启。 */
  refinable?: boolean;
}

/**
 * 人设表单。
 *
 * 字段分两块：
 * 1. 基础四项（名字/身份/性别/年龄）—— 固定 2×2，不做 AI 改写；
 * 2. 六个描述字段 —— 可多行，创建流程里每个都带「AI 帮我改」。
 */
export default function PersonaForm({
  value,
  formId,
  onSubmit,
  onEdit,
  disabled,
  refinable = false,
}: Props) {
  const { register, handleSubmit, setValue, getValues, formState: { errors, isSubmitting } } = useForm<
    z.input<typeof personaFormSchema>, unknown, z.output<typeof personaFormSchema>
  >({ resolver: zodResolver(personaFormSchema), values: personaFormValues(value), mode: "onBlur" });
  const locked = disabled || isSubmitting;

  const fields = [
    ["personality", "p-personality", "性格特质", "逗号分隔，2–8 个", false],
    ["speaking_style", "p-style", "说话风格", "她怎么说话、常用什么句式", true],
    ["background", "p-background", "背景设定", "她的经历、现在的处境", true],
    ["tags", "p-tags", "核心标签", "逗号分隔，例如：吃货、夜猫子", false],
    ["relationship", "p-relation", "关系定位", "她和你是什么关系", false],
    ["example_openers", "p-openers", "示例开场白", "每行一句，最多 3 句", true],
  ] as const;

  /**
   * 把后端返回的值转成表单里的表示。
   *
   * 为什么要转：表单把列表字段存成「用「，」连起来的字符串」，
   * 示例开场白按换行存；而后端返回的是真正的数组。
   * 不转换的话，采用建议后字段会显示成 `a,b,c` 或 `[object Object]`。
   */
  function toFormValue(name: string, raw: unknown): string {
    if (Array.isArray(raw)) {
      return name === "example_openers" ? raw.join("\n") : raw.join("，");
    }
    if (raw === null || raw === undefined) return "";
    return String(raw);
  }

  /** 当前整份表单值，作为 AI 改写时的上下文。 */
  function currentPersona(): Persona {
    const raw = getValues();
    return {
      ...value,
      personality: String(raw.personality ?? "").split(/[，,]/).map((s) => s.trim()).filter(Boolean),
      tags: String(raw.tags ?? "").split(/[，,]/).map((s) => s.trim()).filter(Boolean),
      relationship: String(raw.relationship ?? ""),
      speaking_style: String(raw.speaking_style ?? ""),
      background: String(raw.background ?? ""),
      example_openers: String(raw.example_openers ?? "").split("\n").map((s) => s.trim()).filter(Boolean),
      name: String(raw.name ?? value.name),
      identity: String(raw.identity ?? value.identity),
      gender: (raw.gender ?? value.gender) as Persona["gender"],
      age: raw.age === null || raw.age === undefined || raw.age === ("" as unknown) ? null : Number(raw.age),
    };
  }

  return (
    <form id={formId} noValidate onChange={onEdit} onSubmit={handleSubmit(async (data, event) => {
      const submitter = (event?.nativeEvent as SubmitEvent | undefined)?.submitter;
      await onSubmit(data as unknown as Persona, submitter?.getAttribute("data-intent") ?? undefined);
    })}>
      <div className="field-grid profile-grid">
        {([["name", "p-name", "名字"], ["identity", "p-identity", "身份"]] as const).map(([name, id, label]) => (
          <div key={name}>
            <label htmlFor={id}>{label}</label>
            <input id={id} disabled={locked} {...register(name)} aria-invalid={!!errors[name]} aria-describedby={`${id}-error`} />
            <FieldError id={`${id}-error`} error={errors[name]} />
          </div>
        ))}
        <div>
          <label htmlFor="p-gender">性别</label>
          <select id="p-gender" disabled={locked} {...register("gender")}>
            {personaFields.gender.options.map(item => <option key={item} value={item}>{item}</option>)}
          </select>
        </div>
        <div>
          <label htmlFor="p-age">年龄（18–99）</label>
          <input id="p-age" type="number" disabled={locked} {...register("age", { setValueAs: nullableNumber })} aria-invalid={!!errors.age} aria-describedby="p-age-error" />
          <FieldError id="p-age-error" error={errors.age} />
        </div>
      </div>

      {fields.map(([name, id, label, hint, multiline]) => (
        <div key={name} className="persona-field">
          <div className="persona-field-head">
            <label htmlFor={id}>
              {label}
              <em className="field-hint">{hint}</em>
            </label>
            {/* 只在可编辑时显示「AI 帮我改」。
                查看态下字段是禁用的，生成了建议也写不进去，
                按钮出现只会让用户白跑一趟。 */}
            {refinable && !locked && (
              <PersonaRefineButton
                persona={currentPersona()}
                dimension={name}
                label={label}
                onApply={(next) =>
                  setValue(name, toFormValue(name, next) as never, {
                    shouldValidate: true,
                    shouldDirty: true,
                  })
                }
              />
            )}
          </div>
          {multiline
            ? <textarea id={id} disabled={locked} {...register(name)} aria-invalid={!!errors[name]} aria-describedby={`${id}-error`} />
            : <input id={id} disabled={locked} {...register(name)} aria-invalid={!!errors[name]} aria-describedby={`${id}-error`} />}
          <FieldError id={`${id}-error`} error={errors[name]} />
        </div>
      ))}
    </form>
  );
}
