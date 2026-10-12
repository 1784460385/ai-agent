import { useCallback, useRef, useState } from 'react';
import { streamChat, type SourceItem } from '../api/client';

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceItem[];
  error?: boolean;
}

export function useChat(apiKey: string, modelName: string) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const updateAssistant = useCallback((patch: Partial<Message>) => {
    setMessages((prev) => {
      const updated = [...prev];
      const last = updated[updated.length - 1];
      if (!last || last.role !== 'assistant') return prev;
      updated[updated.length - 1] = { ...last, ...patch };
      return updated;
    });
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      const content = text.trim();
      if (!content || isLoading) return;
      if (!apiKey) {
        setError('请先在左侧保存 DeepSeek API Key');
        return;
      }

      setError(null);
      setMessages((prev) => [
        ...prev,
        { role: 'user', content },
        { role: 'assistant', content: '' },
      ]);
      setIsLoading(true);

      const controller = new AbortController();
      abortRef.current = controller;
      let assistantContent = '';
      let sources: SourceItem[] | undefined;
      let streamError = false;

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
            if (event.type === 'sources') {
              sources = event.sources;
              updateAssistant({ sources });
              return;
            }
            if (event.type === 'delta') {
              assistantContent += event.content;
              updateAssistant({ content: assistantContent, sources });
              return;
            }
            if (event.type === 'error') {
              streamError = true;
              const message = event.message || '生成失败';
              updateAssistant({
                content: assistantContent ? `${assistantContent}\n\n${message}` : message,
                sources,
                error: !assistantContent,
              });
            }
          }
        );

        if (!assistantContent && !streamError) {
          updateAssistant({
            content: '没有收到模型输出',
            sources,
            error: true,
          });
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          if (!assistantContent) {
            updateAssistant({ content: '已停止生成' });
          }
          return;
        }
        const message = err instanceof Error ? err.message : '发送失败';
        updateAssistant({
          content: assistantContent || message,
          sources,
          error: !assistantContent,
        });
      } finally {
        setIsLoading(false);
        abortRef.current = null;
      }
    },
    [apiKey, isLoading, modelName, updateAssistant]
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { messages, isLoading, error, sendMessage, stop };
}
