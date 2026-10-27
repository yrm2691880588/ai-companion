"""从 Pydantic 字段生成前端输入约束；业务清洗与合法性仍由后端领域层负责。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.v1.companion_schemas import PersonaDraftIn  # noqa: E402
from app.api.v1.provider_settings import ProviderPatchIn  # noqa: E402
from app.api.v1.user_profile import ProfileIn  # noqa: E402
from app.api.v1.voice import VoiceProviderPatchIn  # noqa: E402
from app.domain.persona import Persona  # noqa: E402

TARGET = ROOT / "frontend/src/lib/form-fields.generated.ts"


def expression(schema: dict) -> str:
    if "anyOf" in schema:
        variants = schema["anyOf"]
        non_null = [item for item in variants if item.get("type") != "null"]
        if len(variants) == 2 and len(non_null) == 1:
            return expression(non_null[0]) + ".nullable()"
        raise ValueError(f"不支持的联合字段：{schema}")
    if "enum" in schema:
        return "z.enum(" + json.dumps(schema["enum"], ensure_ascii=False) + ")"
    kind = schema["type"]
    if kind == "array":
        value = "z.array(" + expression(schema["items"]) + ")"
    elif kind == "integer":
        value = "z.number().int()"
    elif kind in {"string", "number", "boolean"}:
        value = f"z.{kind}()"
    else:
        raise ValueError(f"不支持的字段类型：{kind}")
    for source, method in [
        ("minLength", "min"), ("maxLength", "max"),
        ("minimum", "min"), ("maximum", "max"),
        ("minItems", "min"), ("maxItems", "max"),
    ]:
        if source in schema:
            value += f".{method}({schema[source]})"
    return value


def generate() -> str:
    lines = [
        "// DO NOT EDIT — 由 scripts/generate_form_contracts.py 生成。",
        "// 只映射输入字段约束，不替代后端领域校验或内容安全规则。",
        'import { z } from "zod";', "",
    ]
    for name, model in [
        ("personaFields", Persona), ("profileFields", ProfileIn),
        ("providerFields", ProviderPatchIn), ("voiceFields", VoiceProviderPatchIn),
        ("draftFields", PersonaDraftIn),
    ]:
        lines.append(f"export const {name} = {{")
        for field, schema in model.model_json_schema()["properties"].items():
            lines.append(f"  {field}: {expression(schema)},")
        lines.extend(["};", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = generate()
    if args.check:
        if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != content:
            raise SystemExit("表单约束生成物存在漂移，请重新运行生成脚本")
        print("表单约束生成物无漂移")
    else:
        TARGET.write_text(content, encoding="utf-8", newline="\n")
        print("已生成前端表单字段约束")


if __name__ == "__main__":
    main()
