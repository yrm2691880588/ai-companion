import type { Persona } from "../types";

interface Props {
  value: Persona;
  onChange: (persona: Persona) => void;
  disabled?: boolean;
}

function splitList(text: string): string[] {
  return text
    .split(/[,，、\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function PersonaForm({ value, onChange, disabled }: Props) {
  const update = <K extends keyof Persona>(key: K, next: Persona[K]) => {
    onChange({ ...value, [key]: next });
  };

  return (
    <div>
      <div className="field-grid">
        <div>
          <label htmlFor="p-name">名字</label>
          <input
            id="p-name"
            disabled={disabled}
            value={value.name}
            onChange={(event) => update("name", event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="p-identity">身份</label>
          <input
            id="p-identity"
            disabled={disabled}
            value={value.identity}
            onChange={(event) => update("identity", event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="p-gender">性别</label>
          <select
            id="p-gender"
            disabled={disabled}
            value={value.gender}
            onChange={(event) => update("gender", event.target.value as Persona["gender"])}
          >
            {["女", "男", "其他", "不设定"].map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="p-age">年龄（16–99）</label>
          <input
            id="p-age"
            type="number"
            min={16}
            max={99}
            disabled={disabled}
            value={value.age ?? ""}
            onChange={(event) =>
              update("age", event.target.value === "" ? null : Number(event.target.value))
            }
          />
        </div>
      </div>

      <label htmlFor="p-personality">性格特质（逗号分隔，2–8 个）</label>
      <input
        id="p-personality"
        disabled={disabled}
        value={value.personality.join("，")}
        onChange={(event) => update("personality", splitList(event.target.value))}
      />

      <label htmlFor="p-style">说话风格</label>
      <textarea
        id="p-style"
        disabled={disabled}
        value={value.speaking_style}
        onChange={(event) => update("speaking_style", event.target.value)}
      />

      <label htmlFor="p-background">背景设定</label>
      <textarea
        id="p-background"
        disabled={disabled}
        value={value.background}
        onChange={(event) => update("background", event.target.value)}
      />

      <div className="field-grid">
        <div>
          <label htmlFor="p-tags">核心标签（逗号分隔）</label>
          <input
            id="p-tags"
            disabled={disabled}
            value={value.tags.join("，")}
            onChange={(event) => update("tags", splitList(event.target.value))}
          />
        </div>
        <div>
          <label htmlFor="p-relation">关系定位</label>
          <input
            id="p-relation"
            disabled={disabled}
            value={value.relationship ?? ""}
            onChange={(event) => update("relationship", event.target.value)}
          />
        </div>
      </div>

      <label htmlFor="p-openers">示例开场白（每行一句，最多 3 句）</label>
      <textarea
        id="p-openers"
        disabled={disabled}
        value={(value.example_openers ?? []).join("\n")}
        onChange={(event) =>
          update(
            "example_openers",
            event.target.value
              .split("\n")
              .map((item) => item.trim())
              .filter(Boolean)
              .slice(0, 3),
          )
        }
      />
    </div>
  );
}
