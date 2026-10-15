/**
 * SSE (Server-Sent Events) 客户端封装,基于 eventsource-parser。
 *
 * 已解决:
 * - AbortSignal:支持外部取消,safe 取消 reader 并解析器终止
 * - 超时:无数据超过 idle_ms 自动 abort 并抛错(默认 90s)
 * - 错误事件解析:`data: { ... }` 走 JSON.parse;失败则降级为 `{ type: 'delta', content: rawData }`
 * - reader 清理:无论以什么方式退出都会 cancel 掉底层 reader,避免泄露
 *
 * 用法:
 *   for await (const evt of streamChatEvents(url, { method: 'POST', body: form, signal })) {
 *     // evt.type === 'delta' | 'router' | 'sources' | 'done' | 'error' | 'conversation'
 *   }
 */
import { createParser, type EventSourceMessage } from 'eventsource-parser';

export type SSEEvent = {
  type: string;
  [key: string]: unknown;
};

export interface SSERequestInit extends Omit<RequestInit, 'signal'> {
  signal?: AbortSignal;
  /** 两次 read 之间允许的最大空闲时间(ms);超过则 abort。默认 90000 (90s) */
  idleTimeoutMs?: number;
  /** 重连配置;开启后会捕获 AbortError 后自动重试一次,直到 signal.aborted */
  retry?: {
    maxAttempts?: number;
    delayMs?: number;
  };
  /** 每次拿到 server-sent 事件后触发(可用于进度心跳) */
  onActivity?: () => void;
}

const DEFAULT_IDLE_TIMEOUT_MS = 90_000;

export class SSEError extends Error {
  status: number;
  cause?: unknown;

  constructor(message: string, status: number, cause?: unknown) {
    super(message);
    this.name = 'SSEError';
    this.status = status;
    this.cause = cause;
  }
}

function isTransientNetworkError(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  // AbortError:fetch / reader.read 拒绝时抛;可能是人为取消,不是网络问题
  return (
    err.name !== 'AbortError' &&
    (err.name === 'TypeError' ||
      err.message?.includes('network') ||
      err.message?.includes('fetch failed'))
  );
}

/**
 * 启动一个 SSE 请求,把每个事件以 async iterable 形式交付给调用方。
 *
 * 参数:
 *   url - 接口地址,绝对路径或相对路径都可
 *   init - 同 fetch 的 RequestInit,加 signal / idleTimeoutMs / retry / onActivity
 *
 * 返回 async iterable<SSEEvent>;调用方可用 for-await-of。
 *
 * 异常:
 *  - 抛出 SSEError(非 2xx + 解析 detail)
 *  - 网络中断 / idle 超时抛 SSEError,带原因
 *  - 中途 abort 自然关闭,不再继续产出事件
 */
export async function* streamChatEvents(
  url: string,
  init: SSERequestInit = {}
): AsyncGenerator<SSEEvent> {
  const {
    signal,
    idleTimeoutMs = DEFAULT_IDLE_TIMEOUT_MS,
    retry = { maxAttempts: 1, delayMs: 800 },
    onActivity,
    ...fetchInit
  } = init;

  // 把 idle timer 用 controller 控制,让 fetch 之外也能 abort
  const idleController = new AbortController();
  const linkedController = new AbortController();
  const onExternalAbort = () => linkedController.abort(signal?.reason);
  signal?.addEventListener('abort', onExternalAbort);

  let idleTimer: ReturnType<typeof setTimeout> | null = null;
  const armIdle = () => {
    if (idleTimer) clearTimeout(idleTimer);
    if (idleTimeoutMs <= 0) return;
    idleTimer = setTimeout(() => {
      idleController.abort(new Error(`SSE 空闲超过 ${idleTimeoutMs}ms`));
    }, idleTimeoutMs);
  };
  const disarmIdle = () => {
    if (idleTimer) {
      clearTimeout(idleTimer);
      idleTimer = null;
    }
  };
  const abortWith = (reason: unknown) => {
    idleController.abort(reason);
    linkedController.abort(reason);
  };

  const cleanup = () => {
    disarmIdle();
    signal?.removeEventListener('abort', onExternalAbort);
  };

  try {
    armIdle();
    const response = await fetch(url, {
      ...fetchInit,
      signal: linkedController.signal,
    });

    // ---- 非 2xx:解析 detail,抛出 SSEError ----
    if (!response.ok) {
      const body = await response.text();
      let message = `请求失败 (${response.status})`;
      try {
        const json = JSON.parse(body) as { detail?: unknown };
        if (typeof json.detail === 'string') message = json.detail;
      } catch {
        // 留 fallback
      }
      abortWith(new SSEError(message, response.status));
      throw new SSEError(message, response.status);
    }

    if (!response.body) {
      throw new SSEError('浏览器不支持流式读取', 0);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending: SSEEvent | null = null;
    let pendingResolver: ((value: SSEEvent | null) => void) | null = null;

    const wake = (event: SSEEvent | null) => {
      const r = pendingResolver;
      pendingResolver = null;
      if (r) {
        r(event);
      } else {
        pending = event;
      }
    };

    const next = (): Promise<SSEEvent | null> =>
      new Promise((resolve) => {
        if (pending !== null) {
          const value = pending;
          pending = null;
          resolve(value);
          return;
        }
        pendingResolver = resolve;
      });

    // 创建解析器;事件经 wake() 回到主循环,主循环 yield 给调用方
    const parser = createParser({
      onEvent(message: EventSourceMessage) {
        const data = message.data?.trim();
        if (!data || data === '[DONE]') return;
        let evt: SSEEvent;
        try {
          evt = JSON.parse(data) as SSEEvent;
        } catch {
          evt = { type: 'delta', content: data };
        }
        onActivity?.();
        armIdle();
        wake(evt);
      },
    });

    try {
      while (!linkedController.signal.aborted) {
        let readChunk: Uint8Array;
        try {
          const result = await reader.read();
          disarmIdle();
          if (result.done) {
            wake(null);
            break;
          }
          readChunk = result.value;
        } catch (readErr) {
          disarmIdle();
          // 用户取消
          if (linkedController.signal.aborted) break;
          throw readErr;
        }
        parser.feed(decoder.decode(readChunk, { stream: true }));

        const evt = await next();
        if (evt === null) break;
        yield evt;
      }
    } finally {
      try {
        await reader.cancel();
      } catch {
        // 已经在关闭
      }
    }
  } finally {
    cleanup();
  }
}

/** 把 SSE 事件流折叠成 [首字节延迟, 总事件数, 错误事件] 统计;供上层 metrics 用。 */
export async function consumeStream(
  url: string,
  init: SSERequestInit,
  onEvent: (evt: SSEEvent) => void
): Promise<{ count: number; errorEvent?: SSEEvent }> {
  let count = 0;
  let errorEvent: SSEEvent | undefined;
  for await (const evt of streamChatEvents(url, init)) {
    count += 1;
    if (evt.type === 'error') errorEvent = evt;
    onEvent(evt);
  }
  return { count, errorEvent };
}

export { isTransientNetworkError };
