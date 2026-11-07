interface Props {
  /** 骨架块数量。列表页按预期条数传，聊天页传 3 就够。 */
  lines?: number;
  /** 是否显示头像占位块（列表类页面用）。 */
  avatar?: boolean;
  /** 无障碍读屏文案；不传则按「加载中」处理。 */
  label?: string;
  /** 是否给每块套上卡片边框。列表类页面为 true 时更像「即将出现的内容」。 */
  card?: boolean;
}

/**
 * 统一的加载骨架。
 *
 * 为什么要有：原来各页写 `加载中…` 纯文字，有的连文字都没有直接空白。
 * 纯文字的问题是——用户不知道是在加载还是卡住了，也看不到页面大概长什么样。
 * 骨架屏至少把版式先占住，加载完不会跳一下。
 *
 * 为什么不用第三方库：只有「几条线 + 可选圆头像」两种形状，
 * 引一个骨架库（react-loading-skeleton 约 10KB）不值得。
 */
export default function Loading({
  lines = 3,
  avatar = false,
  label = "加载中",
  card = false,
}: Props) {
  return (
    <div
      className={card ? "loading-block with-card" : "loading-block"}
      role="status"
      aria-live="polite"
      aria-label={label}
    >
      {Array.from({ length: lines }, (_, index) => (
        <div className="loading-row" key={index}>
          {avatar && index === 0 && <div className="skeleton loading-avatar" />}
          <div className="loading-lines">
            <div className="skeleton-line" />
            <div className="skeleton-line short" />
          </div>
        </div>
      ))}
      <span className="sr-only">{label}</span>
    </div>
  );
}
