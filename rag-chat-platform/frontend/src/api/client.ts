import { ApiError, TOKEN_KEY, http } from './http';
import { streamChatEvents } from '../lib/sse';

export { ApiError };

export interface ModelConfig {
  api_key_id: number;
}

export interface ApiKeyItem {
  id: number;
  name: string;
  masked_key: string;
  model: string;
  base_url: string;
  is_default: boolean;
  created_at: string;
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
  ocr_enabled?: boolean;
  image_max_mb?: number;
  ocr_timeout_seconds?: number;
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

function asChatEvent(evt: { type: string; [k: string]: unknown }): ChatEvent {
  switch (evt.type) {
    case 'conversation':
      return {
        type: 'conversation',
        id: Number(evt.id),
        title: String(evt.title ?? ''),
      };
    case 'router':
      return {
        type: 'router',
        via: evt.via === 'llm' ? 'llm' : 'rule',
        departments: Array.isArray(evt.departments)
          ? (evt.departments as { key: string; name: string }[])
          : [],
      };
    case 'sources':
      return {
        type: 'sources',
        sources: Array.isArray(evt.sources) ? (evt.sources as SourceItem[]) : [],
      };
    case 'delta':
      return { type: 'delta', content: String(evt.content ?? '') };
    case 'done':
      return { type: 'done' };
    case 'error':
      return { type: 'error', message: String(evt.message ?? '未知错误') };
    default:
      return { type: 'delta', content: JSON.stringify(evt) };
  }
}

export async function createFolder(name: string): Promise<{ key: string; name: string }> {
  const { data } = await http.post('/api/folders', { name });
  return data;
}

export async function renameFolder(
  folderKey: string,
  name: string
): Promise<{ key: string; name: string }> {
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
  await http.post(
    `/api/documents/${encodeURIComponent(department)}/${encodeURIComponent(filename)}/retry`
  );
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

export async function moveDocument(
  department: string,
  filename: string,
  target: string
): Promise<void> {
  await http.post(
    `/api/documents/${encodeURIComponent(department)}/${encodeURIComponent(filename)}/move`,
    { target }
  );
}

export interface DocumentPreview {
  filename: string;
  kind: string;
  preview: string;
  size: number;
}

export async function previewDocument(
  department: string,
  filename: string
): Promise<DocumentPreview> {
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
  const { data } = await http.post('/api/index', null, {
    params: department ? { department } : {},
  });
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
  const { data } = await http.get('/api/conversations', {
    params: { keyword: keyword || undefined },
  });
  return data.items ?? [];
}

export async function getConversation(id: number): Promise<ConversationDetail> {
  const { data } = await http.get(`/api/conversations/${id}`);
  return data;
}

export async function deleteConversation(id: number): Promise<void> {
  await http.delete(`/api/conversations/${id}`);
}

export async function listUsers(
  page: number,
  size = 20
): Promise<{ total: number; page: number; size: number; items: AccountUser[] }> {
  const { data } = await http.get('/api/admin/users', { params: { page, size } });
  return data;
}

export async function createUser(payload: {
  username: string;
  password: string;
  role: 'admin' | 'user';
}): Promise<AccountUser> {
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
  await http.post('/api/auth/change-password', {
    old_password: oldPassword,
    new_password: newPassword,
  });
}

export async function listApiKeys(): Promise<ApiKeyItem[]> {
  const { data } = await http.get('/api/keys');
  return data.items ?? [];
}

export async function createApiKey(payload: {
  name: string;
  api_key: string;
  model: string;
  base_url: string;
}): Promise<ApiKeyItem> {
  const { data } = await http.post('/api/keys', payload);
  return data;
}

export async function updateApiKey(
  id: number,
  payload: { name: string; api_key?: string; model: string; base_url: string }
): Promise<ApiKeyItem> {
  const { data } = await http.put(`/api/keys/${id}`, payload);
  return data;
}

export async function deleteApiKey(id: number): Promise<void> {
  await http.delete(`/api/keys/${id}`);
}

export async function setDefaultApiKey(id: number): Promise<ApiKeyItem> {
  const { data } = await http.post(`/api/keys/${id}/default`);
  return data;
}

/** 调用方决定 401 时怎么跳转;本函数只负责把服务端事件透传给 onEvent(类型收窄为 ChatEvent)。 */
export async function streamChat(
  message: string,
  config: ModelConfig,
  signal: AbortSignal,
  onEvent: (event: ChatEvent) => void,
  conversationId?: number | null,
  files: File[] = []
): Promise<void> {
  const form = new FormData();
  form.append('message', message);
  form.append('api_key_id', String(config.api_key_id));
  if (conversationId) form.append('conversation_id', String(conversationId));
  files.forEach((file) => form.append('files', file));

  for await (const evt of streamChatEvents('/api/chat', {
    method: 'POST',
    headers: { Authorization: `Bearer ${localStorage.getItem(TOKEN_KEY) ?? ''}` },
    body: form,
    signal,
    idleTimeoutMs: 180_000, // 大模型长链路
  })) {
    const chatEvent = asChatEvent(evt);
    onEvent(chatEvent);
    if (chatEvent.type === 'done' || chatEvent.type === 'error') {
      return;
    }
  }
}

export { http } from './http';
