import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import type { z } from "zod";
import { nullableNumber, personaFormSchema, personaFormValues } from "../lib/forms";
import { personaFields } from "../lib/form-fields.generated";
import type { Persona } from "../lib/types";
import FieldError from "./FieldError";

interface Props {
  value: Persona;
  formId: string;
  onSubmit: (persona: Persona, intent?: string) => void | Promise<void>;
  onEdit?: () => void;
  disabled?: boolean;
}

export default function PersonaForm({ value, formId, onSubmit, onEdit, disabled }: Props) {
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<
    z.input<typeof personaFormSchema>, unknown, z.output<typeof personaFormSchema>
  >({ resolver: zodResolver(personaFormSchema), values: personaFormValues(value), mode: "onBlur" });
  const locked = disabled || isSubmitting;
  const fields = [
    ["personality", "p-personality", "性格特质（逗号分隔，2–8 个）", false],
    ["speaking_style", "p-style", "说话风格", true],
    ["background", "p-background", "背景设定", true],
    ["tags", "p-tags", "核心标签（逗号分隔）", false],
    ["relationship", "p-relation", "关系定位", false],
    ["example_openers", "p-openers", "示例开场白（每行一句，最多 3 句）", true],
  ] as const;
  return (
    <form id={formId} noValidate onChange={onEdit} onSubmit={handleSubmit(async (data, event) => {
      const submitter = (event?.nativeEvent as SubmitEvent | undefined)?.submitter;
      await onSubmit(data, submitter?.getAttribute("data-intent") ?? undefined);
    })}>
      <div className="field-grid">
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
      {fields.map(([name, id, label, multiline]) => (
        <div key={name}>
          <label htmlFor={id}>{label}</label>
          {multiline
            ? <textarea id={id} disabled={locked} {...register(name)} aria-invalid={!!errors[name]} aria-describedby={`${id}-error`} />
            : <input id={id} disabled={locked} {...register(name)} aria-invalid={!!errors[name]} aria-describedby={`${id}-error`} />}
          <FieldError id={`${id}-error`} error={errors[name]} />
        </div>
      ))}
    </form>
  );
}
