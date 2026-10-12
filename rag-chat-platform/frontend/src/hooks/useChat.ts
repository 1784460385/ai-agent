import { useCallback, useEffect, useRef, useState } from 'react';
import {
  deleteConversation,
  getConversation,
  listConversations,
  streamChat,
  type ConversationSummary,
  type RouterInfo,
  type SourceItem,
} from '../api/client';

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceItem[];
  router?: RouterInfo;
  attachments?: { name: string; kind: 'file' | 'image' }[];
  error?: boolean;
}

export function useChat(apiKey: string, modelName: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const conversationIdRef = useRef<number | null>(null);

  const refreshConversations = useCallback(async () => {
    const items = await listConversations();
    setConversations(items);
  }, []);

  useEffect(() => {
    refreshConversations().catch(() => undefined);
  }, [refreshConversations]);

  const sendMessage = useCallback(
    async (text: string, files: File[] = []) => {
      const content = text.trim();
      if ((!content && !files.length) || isLoading) return;
      if (!apiKey) {
        setError('请先在左侧保存 DeepSeek API Key');
        return;
      }

      const ticket = generation.current;
      setError(null);
      setMessages((prev) => [
        ...prev,
        {
          role: 'user',
          content,
          attachments: files.map((file) => ({
            name: file.name,
            kind: /\.(png|jpe?g|gif|webp)$/i.test(file.name) ? 'image' : 'file',
          })),
        },
        { role: 'assistant', content: '' },
      ]);
      setIsLoading(true);

      const controller = new AbortController();
      abortRef.current = controller;
      let assistantContent = '';
      let sources: SourceItem[] | undefined;
      let router: RouterInfo | undefined;
      let streamError = false;

      const updateAssistant = (patch: Partial<Message>) => {
        if (ticket !== generation.current) return;
        setMessages((prev) => {
          const updated = [...prev];
          const last = updated[updated.length - 1];
          if (!last || last.role !== 'assistant') return prev;
          updated[updated.length - 1] = { ...last, ...patch };
          return updated;
        });
      };

      try {
        await streamChat(
          content,
          {
            api_key: apiKey,
            base_url: 'https://api.deepseek.com',
            model_name: modelName || 'deepseek-flash',
          },
          controller.signal,
          (event) => {
            if (ticket !== generation.current) return;
            if (event.type === 'conversation') {
              conversationIdRef.current = event.id;
              setConversationId(event.id);
              void refreshConversations();
              return;
            }
            if (event.type === 'router') {
              router = { via: event.via, departments: event.departments };
              updateAssistant({ router, sources });
              return;
            }
            if (event.type === 'sources') {
              sources = event.sources;
              updateAssistant({ sources, router });
              return;
            }
            if (event.type === 'delta') {
              assistantContent += event.content;
              updateAssistant({ content: assistantContent, sources, router });
              return;
            }
            if (event.type === 'error') {
              streamError = true;
              const message = event.message || '生成失败';
              updateAssistant({
                content: assistantContent ? `${assistantContent}\n\n${message}` : message,
                sources,
                router,
                error: !assistantContent,
              });
            }
          },
          conversationIdRef.current,
          files
        );

        if (ticket !== generation.current) return;
        if (!assistantContent && !streamError) {
          updateAssistant({ content: '没有收到模型输出', sources, router, error: true });
        }
      } catch (err) {
        if (ticket !== generation.current) return;
        if (err instanceof DOMException && err.name === 'AbortError') {
          if (!assistantContent) updateAssistant({ content: '已停止生成' });
          return;
        }
        const message = err instanceof Error ? err.message : '发送失败';
        updateAssistant({
          content: assistantContent || message,
          sources,
          router,
          error: !assistantContent,
        });
      } finally {
        if (ticket === generation.current) {
          setIsLoading(false);
          abortRef.current = null;
        }
      }
    },
    [apiKey, isLoading, modelName, refreshConversations]
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const startNew = useCallback(() => {
    generation.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    conversationIdRef.current = null;
    setConversationId(null);
    setIsLoading(false);
    setMessages([]);
    setError(null);
  }, []);

  const openConversation = useCallback(async (id: number) => {
    generation.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    setIsLoading(false);
    setError(null);
    const detail = await getConversation(id);
    conversationIdRef.current = detail.id;
    setConversationId(detail.id);
    setMessages(detail.messages);
  }, []);

  const removeConversation = useCallback(
    async (id: number) => {
      await deleteConversation(id);
      if (conversationIdRef.current === id) {
        conversationIdRef.current = null;
        setConversationId(null);
        setMessages([]);
      }
      await refreshConversations();
    },
    [refreshConversations]
  );

  return {
    messages,
    conversations,
    conversationId,
    isLoading,
    error,
    sendMessage,
    stop,
    startNew,
    openConversation,
    removeConversation,
  };
}
