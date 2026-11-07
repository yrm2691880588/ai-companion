import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

interface Props {
  icon: LucideIcon;
  title: string;
  description?: string;
  /** 空态下推荐用户做的那个动作，通常是去创建 / 重试。 */
  action?: ReactNode;
}

/**
 * 空状态。
 *
 * 为什么要有：各页原来都是 `<div className="card"><h3>还没有…</h3><p class="muted">…</p>` ，
 * 有的有按钮有的没有，图标和间距也不统一。空态是用户最先看到的画面，
 * 它长得像「没做完」还是「这里本来就该是空的」，直接影响感受。
 */
export default function EmptyState({ icon: Icon, title, description, action }: Props) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon" aria-hidden="true">
        <Icon size={26} strokeWidth={1.6} />
      </div>
      <h3>{title}</h3>
      {description && <p className="muted">{description}</p>}
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  );
}
