import { test } from "node:test";
import assert from "node:assert";
import { formatDuration, MAX_RECORD_MS } from "../src/lib/voice.ts";

test("0 毫秒显示 0:00", () => {
  assert.strictEqual(formatDuration(0), "0:00");
});

test("不足 1 秒向下取整", () => {
  assert.strictEqual(formatDuration(999), "0:00");
});

test("5 秒显示 0:05（补零）", () => {
  assert.strictEqual(formatDuration(5000), "0:05");
});

test("59 秒显示 0:59", () => {
  assert.strictEqual(formatDuration(59_000), "0:59");
});

test("60 秒进位到 1:00", () => {
  assert.strictEqual(formatDuration(60_000), "1:00");
});

test("90 秒显示 1:30", () => {
  assert.strictEqual(formatDuration(90_000), "1:30");
});

test("10 分钟显示 10:00", () => {
  assert.strictEqual(formatDuration(600_000), "10:00");
});

test("录音上限是 60 秒", () => {
  assert.strictEqual(MAX_RECORD_MS, 60_000);
});

