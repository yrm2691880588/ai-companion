/** 请求公共配置：基地址、用户标识、设备标识。

- 基地址可配置：桌面打包、手机 PWA、反向代理等场景不再依赖“当前域名”；
- 设备标识：首次访问生成 ULID 存本地，用于跨端数据来源判定。
*/

import { ulid } from "ulid";

const USER_KEY = "ai-companion-user-id";
const DEVICE_KEY = "ai-companion-device-id";

/** 允许用 VITE_API_BASE 指定后端地址；默认同源（由后端托管页面）。 */
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/+$/, "") ?? "";

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

export function getUserId(): string {
  return localStorage.getItem(USER_KEY) || "dev-user";
}

export function setUserId(value: string): void {
  localStorage.setItem(USER_KEY, value.trim() || "dev-user");
}

/** 设备标识：生成一次后长期复用；localStorage 不可用时退回内存值。 */
let memoryDeviceId = "";

export function getDeviceId(): string {
  try {
    const saved = localStorage.getItem(DEVICE_KEY);
    if (saved) return saved;
    const created = ulid();
    localStorage.setItem(DEVICE_KEY, created);
    return created;
  } catch {
    if (!memoryDeviceId) memoryDeviceId = ulid();
    return memoryDeviceId;
  }
}

export function authHeaders(): Record<string, string> {
  return {
    "X-User-Id": getUserId(),
    "X-Device-Id": getDeviceId(),
  };
}
