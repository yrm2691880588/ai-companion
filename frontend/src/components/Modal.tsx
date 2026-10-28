import * as Dialog from "@radix-ui/react-dialog";
import type { ReactNode } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** 弹窗底部按钮区 */
  footer?: ReactNode;
  /** 标题下方的说明文字 */
  description?: string;
  /** 为 true 时禁止 Esc / 点击遮罩关闭（例如保存中） */
  preventClose?: boolean;
  className?: string;
}

/**
 * 统一弹窗：行为交给 Radix Dialog（焦点陷阱、Esc 关闭、点击遮罩关闭、
 * 滚动锁定、屏幕阅读器语义），外观仍用项目自己的 CSS 类。
 */
export default function Modal({
  open,
  onClose,
  title,
  children,
  footer,
  description,
  preventClose = false,
  className = "",
}: Props) {
  return (
    <Dialog.Root open={open} onOpenChange={(next) => (next ? undefined : onClose())}>
      <Dialog.Portal>
        <Dialog.Overlay className="modal-backdrop" />
        <Dialog.Content
          className={`modal ${className}`.trim()}
          onPointerDownOutside={(event) => {
            if (preventClose) event.preventDefault();
          }}
          onEscapeKeyDown={(event) => {
            if (preventClose) event.preventDefault();
          }}
        >
          <Dialog.Title asChild>
            <h2>{title}</h2>
          </Dialog.Title>
          <Dialog.Description asChild>
            <p className={description ? "muted" : "sr-only"}>{description ?? title}</p>
          </Dialog.Description>
          {children}
          {footer && <div className="toolbar">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
