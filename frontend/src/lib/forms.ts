import { z } from "zod";
import { zhCN } from "zod/locales";
import { draftFields, personaFields, profileFields, providerFields, voiceFields } from "./form-fields.generated.ts";
import type { Persona } from "./types";

z.config(zhCN());

const splitList = (text: string) => text.split(/[,，、\n]/).map(item => item.trim()).filter(Boolean);
const splitLines = (text: string) => text.split("\n").map(item => item.trim()).filter(Boolean);

// 字段限制来自生成物；文本列表只在提交时转换，输入逗号与换行不会被吞掉。
export const personaSchema = z.object({
  ...personaFields,
  schema_version: personaFields.schema_version.optional(),
  gender: personaFields.gender.default("不设定"),
  age: personaFields.age.default(null),
  relationship: personaFields.relationship.default(""),
  example_openers: personaFields.example_openers.default([]),
});
export const personaFormSchema = personaSchema.extend({
  personality: z.string().transform(splitList).pipe(personaFields.personality),
  tags: z.string().transform(splitList).pipe(personaFields.tags),
  example_openers: z.string().transform(splitLines).pipe(personaFields.example_openers),
});
export function personaFormValues(value: Persona): z.input<typeof personaFormSchema> {
  return { ...value, age: value.age ?? null, relationship: value.relationship ?? "",
    personality: value.personality.join("，"), tags: value.tags.join("，"),
    example_openers: (value.example_openers ?? []).join("\n") };
}
export const profileSchema = z.object(profileFields);
export const providerSchema = z.object({
  apiKey: providerFields.api_key.unwrap(),
  baseUrl: providerFields.base_url.unwrap(),
  enabled: providerFields.enabled.unwrap(),
});
export const voiceSchema = z.object({
  appId: voiceFields.app_id.unwrap(),
  token: voiceFields.token.unwrap(),
  cluster: voiceFields.cluster.unwrap(),
});
export const descriptionSchema = z.object({ description: draftFields.description });
// 模型参数没有独立 Pydantic 模型；这里只检查输入类型，范围由领域层校验。
export const modelDefaultsSchema = z.object({
  model: z.string(), temperature: z.number(), max_tokens: z.number().int(),
  top_p: z.number().optional(), thinking: z.boolean(), json_mode: z.boolean().optional(),
});
export const adminSchema = z.object({ model_defaults: z.record(z.string(), modelDefaultsSchema) });
export const nullableNumber = (value: string) => value === "" ? null : Number(value);
