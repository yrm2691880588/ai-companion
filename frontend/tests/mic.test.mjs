import { test } from "node:test";
import assert from "node:assert";
import {
  FOLLOW_SYSTEM,
  getSelectedMic,
  isMicSupported,
  micConstraints,
  setSelectedMic,
} from "../src/lib/mic.ts";

/** 提供一个最小的 localStorage 替身，让 Node 环境也能跑。 */
function withStorage(run) {
  const store = new Map();
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, String(v)),
    removeItem: (k) => store.delete(k),
  };
  try {
    run(store);
  } finally {
    delete globalThis.localStorage;
  }
}

test("FOLLOW_SYSTEM 是空字符串", () => {
  assert.strictEqual(FOLLOW_SYSTEM, "");
});

test("未设置时返回跟随系统", () => {
  withStorage(() => {
    assert.strictEqual(getSelectedMic(), FOLLOW_SYSTEM);
  });
});

test("设置后能读回", () => {
  withStorage(() => {
    setSelectedMic("abc123");
    assert.strictEqual(getSelectedMic(), "abc123");
  });
});

test("设为空串等价于跟随系统并清除记录", () => {
  withStorage((store) => {
    setSelectedMic("abc123");
    setSelectedMic("");
    assert.strictEqual(store.has("ai-companion-mic-device"), false);
    assert.strictEqual(getSelectedMic(), FOLLOW_SYSTEM);
  });
});

test("localStorage 不可用时不抛异常", () => {
  // 不装替身，Node 环境没有 localStorage
  assert.strictEqual(getSelectedMic(), FOLLOW_SYSTEM);
  assert.doesNotThrow(() => setSelectedMic("x"));
});

test("跟随系统时 constrains 不带 deviceId", () => {
  const c = micConstraints(FOLLOW_SYSTEM);
  assert.strictEqual(c.audio.deviceId, undefined);
  assert.strictEqual(c.audio.channelCount, 1);
  assert.strictEqual(c.audio.autoGainControl, true);
});

test("指定设备时用 exact 约束，避免浏览器悄悄换设备", () => {
  const c = micConstraints("dev-1");
  assert.deepStrictEqual(c.audio.deviceId, { exact: "dev-1" });
});

test("Node 环境判定为不支持麦克风", () => {
  assert.strictEqual(isMicSupported(), false);
});
