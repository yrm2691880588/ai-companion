/**
 * 时间与日期的统一格式化。
 *
 * 为什么要有这个文件：相对时间原来写死在 CompanionsPage 里，聊天页又自己写了一套
 * toDateString() 比较。同一件事三个实现，文案和边界各不相同（例如「刚刚」的门槛）。
 * 所有页面都从这里取，改一次全站生效。
 *
 * 不引入日期库：需要的只有「相对时间」「当天 HH:mm」「今天/昨天/日期分隔」三类，
 * 用浏览器原生的 Intl 就能覆盖，加一个 20KB 的依赖不值得。
 */

/** 一整天：今天/昨天这类按「自然日」比较，不能用 24 小时算。 */
function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/** 相对时间：刚刚 / N 分钟前 / N 小时前 / N 天前 / 具体日期。 */
export function relativeTime(iso?: string | null): string {
  if (!iso) return "";
  const time = new Date(iso).getTime();
  if (Number.isNaN(time)) return "";
  const diff = Date.now() - time;
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  // 跨天后改用自然日差，避免「23 小时前」其实已经是昨天
  const days = Math.round((startOfDay(new Date()) - startOfDay(new Date(time))) / 86_400_000);
  if (days <= 1) return "昨天";
  if (days < 7) return `${days} 天前`;
  const date = new Date(time);
  return `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
}

/** 消息时间：HH:mm（24 小时制，补零）。 */
export function clockTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${hours}:${minutes}`;
}

/** 日期分隔条：今天 / 昨天 / 2026 年 10 月 25 日。 */
export function dayLabel(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const today = new Date();
  const diffDays = Math.round((startOfDay(today) - startOfDay(date)) / 86_400_000);
  if (diffDays === 0) return "今天";
  if (diffDays === 1) return "昨天";
  if (date.getFullYear() === today.getFullYear()) {
    return `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
  }
  return `${date.getFullYear()} 年 ${date.getMonth() + 1} 月 ${date.getDate()} 日`;
}
