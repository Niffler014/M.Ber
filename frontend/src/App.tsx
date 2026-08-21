import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Header } from './components/Header';
import { ChatPanel } from './components/ChatPanel';
import { ExecutionTracePanel } from './components/ExecutionTracePanel';
import { getHealth, streamChat, sendChat } from './api/client';
import { HealthResponse, TraceEvent, FinalStreamPayload, ErrorDetail } from './api/types';
import { ChatMessage } from './types/chat';

export const App: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [isCheckingHealth, setIsCheckingHealth] = useState<boolean>(true);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [currentTrace, setCurrentTrace] = useState<TraceEvent[]>([]);
  const [currentPlanId, setCurrentPlanId] = useState<string | null>(null);
  const [currentStatus, setCurrentStatus] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [isTraceOpen, setIsTraceOpen] = useState<boolean>(true);

  // 產生單一工作階段 conversation_id
  const conversationIdRef = useRef<string>(
    typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `session_${Date.now()}`
  );

  // 1. 定期與初始健康檢查
  const checkBackendHealth = useCallback(async () => {
    try {
      const res = await getHealth();
      setHealth(res);
    } catch {
      setHealth(null);
    } finally {
      setIsCheckingHealth(false);
    }
  }, []);

  useEffect(() => {
    checkBackendHealth();
    const timer = setInterval(checkBackendHealth, 15000);
    return () => clearInterval(timer);
  }, [checkBackendHealth]);

  // 2. 發送使用者訊息處理
  const handleSend = async (text: string) => {
    if (!text.trim() || isStreaming) return;

    const userMessageId = `msg_user_${Date.now()}`;
    const assistantMessageId = `msg_asst_${Date.now() + 1}`;

    const userMsg: ChatMessage = {
      id: userMessageId,
      role: 'user',
      content: text,
      status: 'complete',
      timestamp: Date.now(),
    };

    const assistantMsgPlaceholder: ChatMessage = {
      id: assistantMessageId,
      role: 'assistant',
      content: '',
      status: 'streaming',
      timestamp: Date.now(),
    };

    // 建立新對話氣泡
    setMessages((prev) => [...prev, userMsg, assistantMsgPlaceholder]);
    setCurrentTrace([]);
    setCurrentPlanId(null);
    setCurrentStatus(null);
    setIsStreaming(true);

    const accumulatedTrace: TraceEvent[] = [];

    try {
      await streamChat(text, conversationIdRef.current, {
        onTrace: (event: TraceEvent) => {
          accumulatedTrace.push(event);
          setCurrentTrace([...accumulatedTrace]);
          if (event.plan_id) {
            setCurrentPlanId(event.plan_id);
          }
        },
        onFinal: (payload: FinalStreamPayload) => {
          const finalStatus =
            payload.status === 'partial_success'
              ? 'partial_success'
              : payload.status === 'failed'
              ? 'complete' // 應用層 failed 仍完整呈現 final message
              : 'complete';

          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? {
                    ...msg,
                    content: payload.message,
                    status: finalStatus,
                    planId: payload.plan_id,
                    trace: [...accumulatedTrace],
                  }
                : msg
            )
          );
          setCurrentStatus(payload.status);
          if (payload.plan_id) {
            setCurrentPlanId(payload.plan_id);
          }
          setIsStreaming(false);
        },
        onError: async (err: ErrorDetail) => {
          // 若為連線或串流讀取中斷，嘗試使用 Non-streaming /api/chat 作為安全 Fallback
          if (err.code === 'http_error' || err.code === 'stream_read_error') {
            try {
              const fallbackRes = await sendChat(text, conversationIdRef.current);
              setMessages((prev) =>
                prev.map((msg) =>
                  msg.id === assistantMessageId
                    ? {
                        ...msg,
                        content: fallbackRes.message,
                        status:
                          fallbackRes.status === 'partial_success'
                            ? 'partial_success'
                            : 'complete',
                        planId: fallbackRes.plan_id,
                        trace: fallbackRes.trace || accumulatedTrace,
                      }
                    : msg
                )
              );
              setCurrentStatus(fallbackRes.status);
              if (fallbackRes.plan_id) {
                setCurrentPlanId(fallbackRes.plan_id);
              }
              if (fallbackRes.trace) {
                setCurrentTrace(fallbackRes.trace);
              }
              setIsStreaming(false);
              return;
            } catch {
              // Fallback 也失敗時呈現錯誤
            }
          }

          setMessages((prev) =>
            prev.map((msg) =>
              msg.id === assistantMessageId
                ? {
                    ...msg,
                    status: 'error',
                    error: err.message || '無法連線至 M.Ber 後端服務。',
                  }
                : msg
            )
          );
          setCurrentStatus('failed');
          setIsStreaming(false);
        },
      });
    } catch (exc) {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMessageId
            ? {
                ...msg,
                status: 'error',
                error: exc instanceof Error ? exc.message : '發生未預期異常。',
              }
            : msg
        )
      );
      setCurrentStatus('failed');
      setIsStreaming(false);
    }
  };

  return (
    <div className="app-container">
      <Header
        health={health}
        isCheckingHealth={isCheckingHealth}
        isTraceOpen={isTraceOpen}
        onToggleTrace={() => setIsTraceOpen(!isTraceOpen)}
      />

      <div className="app-main-layout">
        <ChatPanel
          messages={messages}
          isStreaming={isStreaming}
          onSend={handleSend}
          onSelectSuggestion={handleSend}
        />

        <ExecutionTracePanel
          trace={currentTrace}
          isStreaming={isStreaming}
          isOpen={isTraceOpen}
          onClose={() => setIsTraceOpen(false)}
          planId={currentPlanId}
          overallStatus={currentStatus}
        />
      </div>
    </div>
  );
};
