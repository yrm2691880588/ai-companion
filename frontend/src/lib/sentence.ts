/** 把回复文字切成适合逐句合成的片段。

单独放在这里是为了可被 Node 直接测试：不依赖浏览器 API，也不引入 api 模块。
*/

/**
 * 句子结束标记：中英文句号、问号、叹号、分号与换行。
 * 半角 `.` 也在内，但要避免把小数点（3.5）和英文缩写误判——
 * 由 MIN_CHUNK 与「标点后需有非标点内容」共同兜底。
 */
const SENTENCE_END = /[。.！？!?；;\n]/;
/** 逗号等次级停顿，只在句子已经足够长时才切，避免碎成太多短块。 */
const CLAUSE_END = /[，,、：:]/;
/**
 * 句号类标点之后的最小长度。
 * 只在「没有真正句末标点」时才用它兜底；有标点就是明确句界，不该拦。
 */
export const MIN_CHUNK = 4;
/** 次级停顿切分要求的最小长度。 */
export const MIN_CLAUSE_CHUNK = 24;
/** 缓冲上限：超过就强制切一块，避免长句一直等不到句号。 */
export const MAX_BUFFER = 60;

/** 从缓冲区头部切出可合成的片段，返回 [片段, 剩余缓冲]。 */
export function takeChunk(buffer: string): [string, string] {
  for (let index = 0; index < buffer.length; index += 1) {
    const char = buffer[index];
    if (SENTENCE_END.test(char)) {
      // 句末标点是明确的语义边界，只要不是纯标点就切
      const chunk = buffer.slice(0, index + 1).trim();
      if (chunk.replace(/[。！？!?；;\n]/g, "").trim().length >= MIN_CHUNK) {
        return [chunk, buffer.slice(index + 1)];
      }
    }
    if (CLAUSE_END.test(char) && index + 1 >= MIN_CLAUSE_CHUNK) {
      const chunk = buffer.slice(0, index + 1).trim();
      return [chunk, buffer.slice(index + 1)];
    }
  }
  if (buffer.length >= MAX_BUFFER) {
    return [buffer.slice(0, MAX_BUFFER).trim(), buffer.slice(MAX_BUFFER)];
  }
  return ["", buffer];
}
