import { test } from "node:test";
import assert from "node:assert";
import { takeChunk } from "../src/lib/sentence.ts";

test("按句号切出完整句子", () => {
  const [chunk, rest] = takeChunk("今天天气不错，我想出去走走。后面还有");
  assert.strictEqual(chunk, "今天天气不错，我想出去走走。");
  assert.strictEqual(rest, "后面还有");
});

test("句子太短时不切，继续等", () => {
  const [chunk, rest] = takeChunk("好的。");
  assert.strictEqual(chunk, "");
  assert.strictEqual(rest, "好的。");
});
test("逗号够长时切分（需达到 24 字门槛）", () => {
  const text = "我今天真的特别累而且工作了一整天中间都没有停下来好好休息过一会儿，想早点睡了";
  const [chunk] = takeChunk(text);
  assert.ok(chunk.endsWith("，"), `应以逗号结尾，实际：${JSON.stringify(chunk)}`);
  assert.ok(chunk.length >= 24, `应达到门槛，实际长度 ${chunk.length}`);
});

test("逗号位置太靠前时不切", () => {
  const [chunk] = takeChunk("好，我想出去走走看看风景");
  assert.strictEqual(chunk, "");
});

test("超过缓冲上限强制切块", () => {
  const [chunk, rest] = takeChunk("啊".repeat(70));
  assert.strictEqual(chunk.length, 60);
  assert.strictEqual(rest.length, 10);
});

test("没有结束标记时原样返回空片段", () => {
  const [chunk, rest] = takeChunk("还没说完");
  assert.strictEqual(chunk, "");
  assert.strictEqual(rest, "还没说完");
});

test("英文句号也能切", () => {
  const [chunk] = takeChunk("This is a long enough sentence. Next one");
  assert.strictEqual(chunk, "This is a long enough sentence.");
});

test("换行也作为句子结束", () => {
  const [chunk] = takeChunk("第一行内容足够长了\n第二行");
  assert.strictEqual(chunk, "第一行内容足够长了");
});

test("问号和感叹号也能切", () => {
  const [chunk] = takeChunk("你今天到底去哪儿了？我找了半天");
  assert.strictEqual(chunk, "你今天到底去哪儿了？");
});
