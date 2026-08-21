import React, { useState, useRef, useEffect } from 'react';
import { Send, CornerDownLeft } from 'lucide-react';

interface ChatComposerProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export const ChatComposer: React.FC<ChatComposerProps> = ({
  onSend,
  disabled = false,
  placeholder = 'Ask M.Ber anything...',
}) => {
  const [input, setInput] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 自動調整高度
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [input]);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || disabled) return;

    onSend(trimmed);
    setInput('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <form className="chat-composer-form" onSubmit={handleSubmit}>
      <div className="composer-container">
        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className="composer-textarea"
          aria-label="Message input"
        />

        <div className="composer-footer">
          <div className="composer-hints">
            <span className="hint-pill">
              <CornerDownLeft size={11} /> <strong>Enter</strong> to send, <strong>Shift+Enter</strong> for newline
            </span>
          </div>

          <button
            type="submit"
            disabled={!input.trim() || disabled}
            className="btn-send"
            aria-label="Send message"
            title="Send message"
          >
            <Send size={16} />
            <span className="btn-send-text">Send</span>
          </button>
        </div>
      </div>
    </form>
  );
};
