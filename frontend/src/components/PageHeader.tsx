import type { ReactNode } from "react";

interface Props {
  title: string;
  /** 标题下方一句人话说明。不传则不占位。 */
  description?: string;
  /** 右侧操作区，通常是 1 个主按钮 + 0~2 个次要按钮。 */
  actions?: ReactNode;
}

/**
 * 页面标题区。
 *
 * 为什么要有：每个页面原来都自己写 `<div className="row">` + `<h1>` + `<p className="muted">`，
 * 间距和右侧按钮的对齐各不相同（首页右对齐、人设页左对齐、设置页没有操作区）。
 * 统一后所有页面的标题区高度、间距、按钮位置一致。
 */
export default function PageHeader({ title, description, actions }: Props) {
  return (
    <header className="page-header">
      <div className="page-header-text">
        <h1>{title}</h1>
        {description && <p className="muted">{description}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}
