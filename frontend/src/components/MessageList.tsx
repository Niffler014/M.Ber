import React, { useRef, useEffect } from 'react';
import { Sparkles, Cpu, Clock, HardDrive, Compass } from 'lucide-react';
import { ChatMessage } from '../types/chat';
import { MessageBubble } from './MessageBubble';

interface MessageListProps {
  messages: ChatMessage[];
  onSelectSuggestion: (text: string) => void;
}

const SUGGESTIONS = [
  {
    title: 'PCforge 組裝建議',
    desc: '幫我配一台 40000 元遊戲電腦',
    icon: <Cpu size={16} className="text-cyan" />,
    prompt: '幫我配一台 40000 元遊戲電腦',
    badge: 'A2A Agent',
  },
  {
    title: 'MCP 時間工具',
    desc: '幫我查詢現在的系統時間',
    icon: <Clock size={16} className="text-orange" />,
    prompt: '幫我看看現在幾點',
    badge: 'MCP Tool',
  },
  {
    title: '架構概念教學',
    desc: '解釋 dependency injection 依賴注入概念',
    icon: <Compass size={16} className="text-purple" />,
    prompt: '解釋 dependency injection',
    badge: 'LOCAL',
  },
  {
    title: '跨 Agent 記憶工作流',
    desc: '配單並自動儲存至持久化記憶庫',
    icon: <HardDrive size={16} className="text-emerald" />,
    prompt: '幫我配一台 40000 元遊戲電腦，然後記住這套配置',
    badge: 'A2A ➔ Memory',
  },
];

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  onSelectSuggestion,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof bottomRef.current?.scrollIntoView === 'function') {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const isEmpty = messages.length === 0;

  return (
    <div className="message-list" role="log" aria-label="Conversation Messages">
      {isEmpty ? (
        <div className="empty-chat-hero">
          <div className="hero-icon-wrapper">
            <Sparkles className="hero-sparkle" size={28} />
          </div>
          <h2 className="hero-title">Ask M.Ber Anything</h2>
          <p className="hero-subtitle">
            Experience multi-agent orchestration, MCP tool execution, and persistent memory seamlessly.
          </p>

          <div className="suggestion-grid">
            {SUGGESTIONS.map((item, idx) => (
              <button
                key={idx}
                type="button"
                className="suggestion-card"
                onClick={() => onSelectSuggestion(item.prompt)}
              >
                <div className="suggestion-card-header">
                  <div className="suggestion-icon">{item.icon}</div>
                  <span className="suggestion-badge">{item.badge}</span>
                </div>
                <div className="suggestion-card-title">{item.title}</div>
                <div className="suggestion-card-desc">{item.desc}</div>
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="messages-container">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          <div ref={bottomRef} className="scroll-anchor" />
        </div>
      )}
    </div>
  );
};
