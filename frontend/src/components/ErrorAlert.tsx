import { AlertTriangle, RotateCw, X } from "lucide-react";

interface Props {
  /** 错误信息。为空时不渲染。 */
  message?: string | null;
  /** 传了就显示「重试」按钮。 */
  onRetry?: () => void;
  /** 传了就显示关闭按钮。 */
  onDismiss?: () => void;
  /** banner 用于页面级阻断错误；inline 用于卡片/表单内。 */
  variant?: "banner" | "inline";
}

/**
 * 统一的错误提示。
 *
 * 为什么要有：原来 19 个文件各自写 `<div className="alert">`，
 * 有的带图标有的不带，有的能关有的不能，有的有重试有的只能干瞪眼。
 * 用户在不同页面遇到错误，看到的样式和能做的操作都不一样。
 *
 * 现在统一成：图标 + 文案 + 可选「重试」+ 可选「关闭」。
 */
export default function ErrorAlert({ message, onRetry, onDismiss, variant = "banner" }: Props) {
  if (!message) return null;
  return (
    <div className={`error-alert ${variant}`} role="alert">
      <AlertTriangle size={16} aria-hidden="true" className="error-alert-icon" />
      <span className="error-alert-text">{message}</span>
      {onRetry && (
        <button type="button" className="error-alert-btn" onClick={onRetry}>
          <RotateCw size={13} aria-hidden="true" />
          重试
        </button>
      )}
      {onDismiss && (
        <button
          type="button"
          className="error-alert-close"
          aria-label="关闭提示"
          onClick={onDismiss}
        >
          <X size={14} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
