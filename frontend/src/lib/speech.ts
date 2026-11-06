/** 流式语音播报：边接收回复文字，边按句合成、边播放。

为什么这样做：等整段回复写完再合成，用户要空等 2–4 秒才听到声音。
按句切分后，第一句一出现就能开始合成与播放，首声明显提前。

顺序保证：合成请求必须串行（按句顺序），播放交给队列，避免音频互相打断。
*/

import { api } from "../api";
import { takeChunk } from "./sentence";
import { createSpeechPlayer } from "./voice";
import type { SpeechPlayer } from "./voice";

export interface StreamingSpeaker {
  /** 收到一段回复文字。 */
  push: (delta: string) => void;
  /** 回复结束：把剩余文字合成掉。 */
  finish: () => void;
  /** 立即停止（用户关语音、切会话、点停止）。 */
  stop: () => void;
}

export interface SpeakerOptions {
  voiceId: string;
  sessionId?: number;
  /** 第一段音频开始播放时回调一次，用于把界面切到「她在说话」。 */
  onFirstAudio?: () => void;
  /** 队列全部播完时回调。 */
  onIdle?: () => void;
  /** 某一句合成失败时回调；不中断后续句子。 */
  onError?: (message: string) => void;
}

export function createStreamingSpeaker(options: SpeakerOptions): StreamingSpeaker {
  const player: SpeechPlayer = createSpeechPlayer();
  let buffer = "";
  let stopped = false;
  let started = false;
  // 合成串行链：保证第 2 句的音频排在第 1 句之后
  let chain: Promise<void> = Promise.resolve();

  player.onIdle(() => {
    if (!stopped) options.onIdle?.();
  });

  // 播放失败不能静默吞掉，否则用户只会觉得「没声音」
  player.onError((message) => {
    if (!stopped) options.onError?.(message);
  });

  function speak(chunk: string) {
    chain = chain
      .then(async () => {
        if (stopped || !chunk.trim()) return;
        const speech = await api.synthesize(chunk, options.voiceId, {
          sessionId: options.sessionId,
        });
        if (stopped) return;
        if (!started) {
          started = true;
          options.onFirstAudio?.();
        }
        player.enqueue(speech.audio_url);
      })
      .catch((event: unknown) => {
        if (stopped) return;
        options.onError?.((event as Error).message || "语音合成失败");
      });
  }

  function drain() {
    for (;;) {
      const [chunk, rest] = takeChunk(buffer);
      if (!chunk) return;
      buffer = rest;
      speak(chunk);
    }
  }

  return {
    push: (delta) => {
      if (stopped) return;
      buffer += delta;
      drain();
    },
    finish: () => {
      if (stopped) return;
      const tail = buffer.trim();
      buffer = "";
      if (tail) speak(tail);
      // 没有产生任何音频时也要收尾，否则界面会一直显示「她在说话」
      void chain.then(() => {
        if (stopped) return;
        if (!started) options.onIdle?.();
      });
    },
    stop: () => {
      stopped = true;
      buffer = "";
      player.stop();
    },
  };
}
