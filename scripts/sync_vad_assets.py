"""把 VAD 运行期资源复制到 public/vad，避免运行时依赖 node_modules。

@ricky0123/vad-web 需要两类静态资源：
- silero_vad*.onnx 模型
- vad.worklet.bundle.min.js 音频线程脚本

它们必须能从浏览器直接访问（同源），所以复制进 public/ 由 Vite 静态托管。
用法：python scripts/sync_vad_assets.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAD_SOURCE = ROOT / "frontend" / "node_modules" / "@ricky0123" / "vad-web" / "dist"
ORT_SOURCE = (
    ROOT
    / "frontend"
    / "node_modules"
    / ".pnpm"
    / "onnxruntime-web@1.31.1"
    / "node_modules"
    / "onnxruntime-web"
    / "dist"
)
TARGET = ROOT / "frontend" / "public" / "vad"

# 模型与 worklet 来自 vad-web；wasm 来自 onnxruntime-web（推理引擎本体）
ASSETS = [
    "silero_vad_v5.onnx",
    "vad.worklet.bundle.min.js",
    "ort-wasm-simd-threaded.mjs",
    "ort-wasm-simd-threaded.wasm",
]


def main() -> int:
    if not VAD_SOURCE.is_dir():
        print(f"未找到 vad-web 依赖：{VAD_SOURCE}\n请先在 frontend 里执行 pnpm install")
        return 1
    TARGET.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name in ASSETS:
        base = ORT_SOURCE if name.startswith("ort-") else VAD_SOURCE
        src = base / name
        if not src.exists():
            print(f"[缺失] {name}")
            return 1
        shutil.copy2(src, TARGET / name)
        size_kb = round((TARGET / name).stat().st_size / 1024, 0)
        print(f"已复制 {name}（{size_kb} KB）")
        copied += 1
    print(f"完成：{copied} 个文件 -> {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

