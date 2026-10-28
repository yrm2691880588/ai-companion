// DO NOT EDIT — 由 scripts/generate_form_contracts.py 生成。
// 只映射输入字段约束，不替代后端领域校验或内容安全规则。
import { z } from "zod";

export const personaFields = {
  schema_version: z.number().int(),
  name: z.string().min(1).max(20),
  identity: z.string().min(2).max(60),
  gender: z.enum(["女", "男", "其他", "不设定"]),
  age: z.number().int().min(18).max(99).nullable(),
  personality: z.array(z.string()).min(2).max(8),
  speaking_style: z.string().min(4).max(200),
  background: z.string().min(10).max(800),
  tags: z.array(z.string()).min(1).max(8),
  relationship: z.string().max(60),
  example_openers: z.array(z.string()).max(3),
};

export const profileFields = {
  nickname: z.string().max(20),
  identity: z.string().max(60),
  age: z.number().int().min(18).max(99).nullable(),
  gender: z.string().max(8),
  city: z.string().max(40),
  background: z.string().max(400),
};

export const providerFields = {
  api_key: z.string().max(400).nullable(),
  base_url: z.string().max(500).nullable(),
  enabled: z.boolean().nullable(),
};

export const voiceFields = {
  app_id: z.string().max(128).nullable(),
  token: z.string().max(512).nullable(),
  cluster: z.string().max(64).nullable(),
  base_url: z.string().max(500).nullable(),
  enabled: z.boolean().nullable(),
};

export const draftFields = {
  description: z.string().min(4).max(200),
};
