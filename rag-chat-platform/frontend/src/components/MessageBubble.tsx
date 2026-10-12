import type { Message } from '../hooks/useChat';

interface Props {
  message: Message;
  streaming?: boolean;
}

export function MessageBubble({ message, streaming = false }: Props) {
  const isUser = message.role === 'user';
  return (
    <article className={isUser ? 'bubble-row user' : 'bubble-row'}>
      <div className={message.error ? 'bubble error' : 'bubble'}>
        <p>
          {message.content || (streaming ? '' : '…')}
          {streaming && <span className="caret" aria-hidden="true" />}
        </p>
        {message.sources && message.sources.length > 0 && (
          <div className="sources">
            {message.sources.map((source) => (
              <div key={source.index} className="source">
                <strong>
                  {source.index}. {source.source}
                </strong>
                <span>{source.preview}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}
