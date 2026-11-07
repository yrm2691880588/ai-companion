/**
 * 前端用到的业务约束常量。
 *
 * 为什么集中放这里：AGENTS.local.md 15.5 明确写「前端页面禁止硬编码业务常量」。
 * 这些数字都对应后端的真实约束，散落在组件里会两边漂移——
 * 后端改了上限，前端提示还写着旧数字，比不写更糟。
 *
 * 命名与来源：
 * - MAX_PERSONA_VERSIONS         ← backend/app/domain/companions.py
 * - MAX_REFINE_HINT              ← backend/app/domain/companions.py
 * - MESSAGE_PAGE_SIZE            ← 首次加载条数，与 api.messages 默认一致
 * - OLDER_PAGE_SIZE              ← 加载更早每页条数
 * - MAX_MESSAGE_CHARS            ← backend/app/domain/chat.py
 *
 * 这些是「协议常量」不是「业务规则」：真正的校验仍在后端，
 * 前端用它们只为给出准确的提示文案、避免无意义的请求。
 */

/** 每个伴侣保留的历史人设版本上限。 */
export const MAX_PERSONA_VERSIONS = 20;

/** AI 改写人设时，补充要求的字数上限。 */
export const MAX_REFINE_HINT = 200;

/** 单条消息的字数上限。 */
export const MAX_MESSAGE_CHARS = 2000;

/** 进入会话时首次加载的消息条数。 */
export const MESSAGE_PAGE_SIZE = 100;

/** 点「加载更早」时每次追加的条数。 */
export const OLDER_PAGE_SIZE = 30;
