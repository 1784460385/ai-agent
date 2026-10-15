import axios from 'axios';
import { dispatchAuthExpired } from '../lib/authEvents';

export const TOKEN_KEY = 'token';
export const USER_KEY = 'user';

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function readDetail(data: unknown, fallback: string): string {
  if (!data || typeof data !== 'object') return fallback;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg || JSON.stringify(item)).join('；');
  }
  return fallback;
}

/**
 * 清掉本地登录态。注意:不再负责跳转,把跳转交给订阅了 ``authEvents.expired`` 的组件。
 */
export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export const http = axios.create();

http.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status ?? 0;
    const url = String(error.config?.url || '');

    // 登录本身失败时不需要重复触发 expired 事件(还在登录页)
    if (status === 401 && !url.includes('/api/auth/login')) {
      // 通过 dispatchAuthExpired 让上层订阅者决定怎么跳转,
      // 不要再这里直接 window.location.assign(可能打断正在显示的错误 toast)
      dispatchAuthExpired();
    }
    const message = readDetail(error.response?.data, error.message || '请求失败');
    return Promise.reject(new ApiError(status, message));
  }
);
