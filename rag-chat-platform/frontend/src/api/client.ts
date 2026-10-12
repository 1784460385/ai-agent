import { createParser, type EventSourceMessage } from 'eventsource-parser';

export interface ModelConfig {
  api_key: string;
  base_url: string;
  model_name: string;
}

export interface SourceItem {
  index: number;
  source: string;
  preview: string;
}

export interface IndexResponse {
  status: string;
  chunks_indexed?: number;
  message?: string;
}

export interface DocumentInfo {
  name: string;
  size: number;
}

export type ChatEvent =
  | { type: 'sources'; sources: SourceItem[] }
  | { type: 'delta'; content: string }
  | { type: 'done' }
  | { type: 'error'; message: string };

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail.map((item) => item?.msg || JSON.stringify(item)).join('；');
    }
  } catch {
    /* 非 JSON 错误体 */
  }
  return fallback;
}

export async function uploadDocument(file: File): Promise<{ status: string; filename: string }> {
  const form = new FormData();
  form.append('file', file);
  const response = await fetch('/api/upload', { method: 'POST', body: form });
  if (!response.ok) {
    throw new ApiError(response.status, await readError(response, '上传失败'));
  }
  return response.json();
}

export async function rebuildIndex(): Promise<IndexResponse> {
  const response = await fetch('/api/index', { method: 'POST' });
  if (!response.ok) {
    throw new ApiError(response.status, await readError(response, '索引失败'));
  }
  return response.json();
}

export async function listDocuments(): Promise<DocumentInfo[]> {
  const response = await fetch('/api/documents');
  if (!response.ok) {
    throw new ApiError(response.status, await readError(response, '无法读取知识库'));
  }
  const body = await response.json();
  return body.files ?? [];
}

export async function fetchStats(): Promise<number> {
  const response = await fetch('/api/stats');
  if (!response.ok) {
    throw new ApiError(response.status, '无法读取索引状态');
  }
  const body = await response.json();
  return body.chunks ?? 0;
}

export async function streamChat(
  message: string,
  config: ModelConfig,
  signal: AbortSignal,
  onEvent: (event: ChatEvent) => void
): Promise<void> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, config }),
    signal,
  });

  if (!response.ok) {
    const fallback = response.status === 401 ? 'API Key 无效或未授权' : `请求失败 (${response.status})`;
    throw new ApiError(response.status, await readError(response, fallback));
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('浏览器不支持流式读取');
  }

  const decoder = new TextDecoder();
  const parser = createParser({
    onEvent(event: EventSourceMessage) {
      const data = event.data?.trim();
      if (!data || data === '[DONE]') return;
      try {
        onEvent(JSON.parse(data) as ChatEvent);
      } catch {
        onEvent({ type: 'delta', content: data });
      }
    },
  });

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    parser.feed(decoder.decode(value, { stream: true }));
  }
}
