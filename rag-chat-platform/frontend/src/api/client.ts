import { createParser, type EventSourceMessage } from 'eventsource-parser';
import { ApiError, http, TOKEN_KEY, clearSession } from './http';

export { ApiError };

export interface ModelConfig {
  api_key: string;
  base_url: string;
  model_name: string;
}

export interface SourceItem {
  index: number;
  source: string;
  department?: string;
  department_name?: string;
  preview: string;
  excerpt?: string;
}

export interface RouterInfo {
  via: 'rule' | 'llm';
  departments: { key: string; name: string }[];
}

export interface IndexResponse {
  status: string;
  chunks_indexed?: number;
  message?: string;
}

export interface DocumentInfo {
  name: string;
  size: number;
  department?: string;
  parse_status?: string | null;
  parse_error?: string | null;
}

export interface FormatInfo {
  ext: string;
  label: string;
  max_mb: number;
}

export interface AppConfig {
  formats: FormatInfo[];
  coming_soon: string[];
  accept: string;
}

export interface DepartmentInfo {
  key: string;
  name: string;
  description: string;
  chunk_count: number;
  files: DocumentInfo[];
}

export interface AccountUser {
  id: number;
  username: string;
  role: 'admin' | 'user';
  is_active: boolean;
  created_at: string;
}

export interface ConversationSummary {
  id: number;
  title: string;
  updated_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: Array<{
    role: 'user' | 'assistant';
    content: string;
    sources?: SourceItem[];
    router?: RouterInfo;
    attachments?: { name: string; kind: 'file' | 'image' }[];
  }>;
}

export type ChatEvent =
  | { type: 'conversation'; id: number; title: string }
  | { type: 'router'; via: 'rule' | 'llm'; departments: { key: string; name: string }[] }
  | { type: 'sources'; sources: SourceItem[] }
  | { type: 'delta'; content: string }
  | { type: 'done' }
  | { type: 'error'; message: string };

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

export async function createFolder(name: string): Promise<{ key: string; name: string }> {
  const { data } = await http.post('/api/folders', { name });
  return data;
}

export async function renameFolder(folderKey: string, name: string): Promise<{ key: string; name: string }> {
  const { data } = await http.patch(`/api/folders/${encodeURIComponent(folderKey)}`, { name });
  return data;
}

export async function deleteFolder(folderKey: string): Promise<void> {
  await http.delete(`/api/folders/${encodeURIComponent(folderKey)}`);
}

export async function fetchConfig(): Promise<AppConfig> {
  const { data } = await http.get('/api/config');
  return data;
}

export async function retryParse(department: string, filename: string): Promise<void> {
  await http.post(`/api/documents/${encodeURIComponent(department)}/${encodeURIComponent(filename)}/retry`);
}

export async function uploadDocument(
  file: File,
  department: string
): Promise<{ status: string; filename: string; department: string }> {
  const form = new FormData();
  form.append('department', department);
  form.append('file', file);
  const { data } = await http.post('/api/upload', form);
  return data;
}

export async function deleteDocument(department: string, filename: string): Promise<void> {
  await http.delete(`/api/documents/${encodeURIComponent(department)}/${encodeURIComponent(filename)}`);
}

export async function moveDocument(department: string, filename: string, target: string): Promise<void> {
  await http.post(`/api/documents/${encodeURIComponent(department)}/${encodeURIComponent(filename)}/move`, { target });
}

export interface DocumentPreview {
  filename: string;
  kind: string;
  preview: string;
  size: number;
}

export async function previewDocument(department: string, filename: string): Promise<DocumentPreview> {
  const { data } = await http.get(
    `/api/documents/${encodeURIComponent(department)}/${encodeURIComponent(filename)}/preview`
  );
  return data;
}

export async function fetchDocumentContent(department: string, filename: string): Promise<Blob> {
  const { data } = await http.get(
    `/api/documents/${encodeURIComponent(department)}/${encodeURIComponent(filename)}/content`,
    { responseType: 'blob' }
  );
  return data;
}

export async function rebuildIndex(department?: string): Promise<IndexResponse> {
  const { data } = await http.post('/api/index', null, { params: department ? { department } : {} });
  return data;
}

export async function listDepartments(): Promise<DepartmentInfo[]> {
  const { data } = await http.get('/api/departments');
  return data.departments ?? [];
}

export async function listDocuments(): Promise<DocumentInfo[]> {
  const { data } = await http.get('/api/documents');
  return data.files ?? [];
}

export async function fetchStats(): Promise<number> {
  const { data } = await http.get('/api/stats');
  return data.chunks ?? 0;
}

export async function listConversations(keyword = ''): Promise<ConversationSummary[]> {
  const { data } = await http.get('/api/conversations', { params: { keyword: keyword || undefined } });
  return data.items ?? [];
}

export async function getConversation(id: number): Promise<ConversationDetail> {
  const { data } = await http.get(`/api/conversations/${id}`);
  return data;
}

export async function deleteConversation(id: number): Promise<void> {
  await http.delete(`/api/conversations/${id}`);
}

export async function listUsers(page: number, size = 20): Promise<{ total: number; page: number; size: number; items: AccountUser[] }> {
  const { data } = await http.get('/api/admin/users', { params: { page, size } });
  return data;
}

export async function createUser(payload: { username: string; password: string; role: 'admin' | 'user' }): Promise<AccountUser> {
  const { data } = await http.post('/api/admin/users', payload);
  return data;
}

export async function updateUser(
  id: number,
  payload: { role?: 'admin' | 'user'; is_active?: boolean; password?: string }
): Promise<AccountUser> {
  const { data } = await http.put(`/api/admin/users/${id}`, payload);
  return data;
}

export async function deleteUser(id: number): Promise<void> {
  await http.delete(`/api/admin/users/${id}`);
}

export async function changePassword(oldPassword: string, newPassword: string): Promise<void> {
  await http.post('/api/auth/change-password', { old_password: oldPassword, new_password: newPassword });
}

export async function streamChat(
  message: string,
  config: ModelConfig,
  signal: AbortSignal,
  onEvent: (event: ChatEvent) => void,
  conversationId?: number | null,
  files: File[] = []
): Promise<void> {
  const token = localStorage.getItem(TOKEN_KEY);
  const form = new FormData();
  form.append('message', message);
  form.append('api_key', config.api_key);
  form.append('base_url', config.base_url);
  form.append('model_name', config.model_name);
  if (conversationId) form.append('conversation_id', String(conversationId));
  files.forEach((file) => form.append('files', file));
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: form,
    signal,
  });

  if (!response.ok) {
    const fallback = response.status === 401 ? '登录已失效，请重新登录' : `请求失败 (${response.status})`;
    const messageText = await readError(response, fallback);
    if (response.status === 401 && (messageText.includes('凭证') || messageText.includes('禁用') || messageText.includes('不存在'))) {
      clearSession();
      window.location.assign('/login');
    }
    throw new ApiError(response.status, messageText);
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
