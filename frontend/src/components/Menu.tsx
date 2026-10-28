import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { useRef } from "react";
import type { ReactNode } from "react";

export interface MenuItem {
  key: string;
  label: string;
  onSelect: () => void;
  danger?: boolean;
  /**
   * 该项会打开一个弹窗时置为 true。
   * 菜单关闭默认会把焦点还给触发按钮，会抢走弹窗的焦点，导致焦点陷阱失效；
   * 标记后就让弹窗自己接管焦点。
   */
  opensModal?: boolean;
}

interface Props {
  trigger: ReactNode;
  items: MenuItem[];
  side?: "top" | "bottom";
  align?: "start" | "end";
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  triggerLabel?: string;
}

/**
 * 统一菜单：行为交给 Radix DropdownMenu（键盘上下选择、Esc 关闭、
 * 点击外部关闭、焦点归还、屏幕阅读器语义），外观仍用项目的 .menu 样式。
 */
export default function Menu({
  trigger,
  items,
  side = "bottom",
  align = "end",
  open,
  onOpenChange,
  triggerLabel,
}: Props) {
  const skipFocusReturn = useRef(false);

  return (
    <DropdownMenu.Root
      open={open}
      onOpenChange={(next) => {
        if (next) skipFocusReturn.current = false;
        onOpenChange?.(next);
      }}
    >
      <DropdownMenu.Trigger asChild aria-label={triggerLabel}>
        {trigger}
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          className="menu"
          side={side}
          align={align}
          sideOffset={6}
          collisionPadding={8}
          onCloseAutoFocus={(event) => {
            if (skipFocusReturn.current) {
              event.preventDefault();
              skipFocusReturn.current = false;
            }
          }}
        >
          {items.map((item) => (
            <DropdownMenu.Item
              key={item.key}
              className={item.danger ? "menu-item danger-text" : "menu-item"}
              onSelect={() => {
                if (item.opensModal) skipFocusReturn.current = true;
                item.onSelect();
              }}
            >
              {item.label}
            </DropdownMenu.Item>
          ))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
