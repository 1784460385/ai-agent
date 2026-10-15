/**
 * 鉴权事件的轻量级发布/订阅。
 *
 * 取代原来 ``http.ts`` 中拦截到 401 就 ``window.location.assign('/login')`` 的做法。
 *
 * 用法:
 *   import { authEvents } from '@/lib/authEvents';
 *   authEvents.on('expired', () => nav('/login'));
 *
 *   import { dispatchAuthExpired } from '@/lib/authEvents';
 *   dispatchAuthExpired();   // 内部任意模块触发
 */

import { TOKEN_KEY, USER_KEY } from '../api/http';

export type AuthEventName = 'expired' | 'forbidden';

type Listener = () => void;

const listeners: Record<AuthEventName, Set<Listener>> = {
  expired: new Set(),
  forbidden: new Set(),
};

export const authEvents = {
  on(name: AuthEventName, listener: Listener): () => void {
    listeners[name].add(listener);
    return () => listeners[name].delete(listener);
  },
};

export function dispatchAuthExpired(): void {
  // 先清 token,避免残留状态
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    // localStorage 不可用时忽略
  }
  for (const fn of listeners.expired) {
    try {
      fn();
    } catch {
      // 不让单个监听者崩溃整体
    }
  }
}

export function dispatchAuthForbidden(): void {
  for (const fn of listeners.forbidden) {
    try {
      fn();
    } catch {
      // 忽略
    }
  }
}
