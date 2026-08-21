import React from 'react';
import { ChatMessage } from '../types/chat';
import { MessageList } from './MessageList';
import { ChatComposer } from './ChatComposer';

interface ChatPanelProps {
  messages: ChatMessage[];
  isStreaming: boolean;
  onSend: (message: string) => void;
  onSelectSuggestion: (prompt: string) => void;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  isStreaming,
  onSend,
  onSelectSuggestion,
}) => {
  return (
    <main className="chat-panel" aria-label="Chat Interaction Area">
      <MessageList
        messages={messages}
        onSelectSuggestion={onSelectSuggestion}
      />

      <div className="composer-wrapper">
        <ChatComposer
          onSend={onSend}
          disabled={isStreaming}
          placeholder={isStreaming ? 'M.Ber is orchestrating, please wait...' : 'Ask M.Ber anything...'}
        />
      </div>
    </main>
  );
};
