import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Bot, User, AlertTriangle, AlertCircle, Copy, Check } from 'lucide-react';
import { ChatMessage } from '../types/chat';

interface MessageBubbleProps {
  message: ChatMessage;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const { role, content, status, error } = message;
  const isUser = role === 'user';
  const isStreaming = status === 'streaming';
  const isError = status === 'error';
  const isPartialSuccess = status === 'partial_success';

  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (!content) return;
    navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className={`message-row ${isUser ? 'user-row' : 'assistant-row'}`}>
      <div className="message-avatar">
        {isUser ? <User size={18} /> : <Bot size={18} />}
      </div>

      <div className={`message-bubble ${isUser ? 'user-bubble' : 'assistant-bubble'}`}>
        <div className="message-bubble-header">
          <span className="sender-name">{isUser ? 'You' : 'M.Ber'}</span>

          {!isUser && isPartialSuccess && (
            <span className="badge-partial-success">
              <AlertTriangle size={12} /> Partial Success
            </span>
          )}

          {!isUser && content && !isStreaming && (
            <button
              type="button"
              className="btn-copy"
              onClick={handleCopy}
              title="Copy message"
              aria-label="Copy message"
            >
              {copied ? <Check size={13} className="text-green" /> : <Copy size={13} />}
            </button>
          )}
        </div>

        <div className="message-content">
          {isStreaming && !content ? (
            <div className="streaming-placeholder">
              <span className="pulse-dot" />
              <span className="streaming-text">M.Ber is thinking & orchestrating...</span>
            </div>
          ) : isError ? (
            <div className="error-message-content">
              <AlertCircle className="text-red inline-icon" size={16} />
              <span>{error || content || 'Something went wrong while processing this request.'}</span>
            </div>
          ) : isUser ? (
            <p className="user-text">{content}</p>
          ) : (
            <div className="markdown-body">
              <ReactMarkdown>{content}</ReactMarkdown>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
