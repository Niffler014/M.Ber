/**
 * M.Ber Web API Client.
 */

import { API_BASE_URL } from './config';
import { SSEParser } from './sseParser';
import {
  ChatRequest,
  ChatResponse,
  ErrorDetail,
  ErrorResponse,
  FinalStreamPayload,
  HealthResponse,
  TraceEvent,
} from './types';

export interface StreamChatCallbacks {
  onTrace?: (event: TraceEvent) => void;
  onFinal?: (payload: FinalStreamPayload) => void;
  onError?: (error: ErrorDetail) => void;
}

/**
 * 檢查後端健康狀態.
 */
export async function getHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE_URL}/api/health`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!res.ok) {
    throw new Error(`Health check failed with status: ${res.status}`);
  }

  return (await res.json()) as HealthResponse;
}

/**
 * 非串流對話請求 (Fallback / 一次性請求).
 */
export async function sendChat(
  message: string,
  conversationId?: string | null,
): Promise<ChatResponse> {
  const reqBody: ChatRequest = {
    message,
    conversation_id: conversationId,
  };

  const res = await fetch(`${API_BASE_URL}/api/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(reqBody),
  });

  if (!res.ok) {
    const errorData = (await res.json().catch(() => null)) as ErrorResponse | null;
    const msg = errorData?.error?.message || `Chat request failed: HTTP ${res.status}`;
    throw new Error(msg);
  }

  return (await res.json()) as ChatResponse;
}

/**
 * POST SSE 即時串流對話請求.
 */
export async function streamChat(
  message: string,
  conversationId: string | null | undefined,
  callbacks: StreamChatCallbacks,
): Promise<void> {
  const reqBody: ChatRequest = {
    message,
    conversation_id: conversationId,
  };

  const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(reqBody),
  });

  if (!response.ok) {
    const errorData = (await response.json().catch(() => null)) as ErrorResponse | null;
    const errDetail: ErrorDetail = errorData?.error || {
      code: 'http_error',
      message: `連線失敗 (HTTP ${response.status})`,
    };
    callbacks.onError?.(errDetail);
    return;
  }

  if (!response.body) {
    callbacks.onError?.({
      code: 'no_stream_body',
      message: '瀏覽器未能取得 SSE 串流本體',
    });
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  const parser = new SSEParser();

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      const chunk = decoder.decode(value, { stream: true });
      const events = parser.push(chunk);

      for (const evt of events) {
        if (evt.event === 'trace') {
          try {
            const traceEvent = JSON.parse(evt.data) as TraceEvent;
            callbacks.onTrace?.(traceEvent);
          } catch {
            // 忽略 JSON 解析異常
          }
        } else if (evt.event === 'final') {
          try {
            const finalPayload = JSON.parse(evt.data) as FinalStreamPayload;
            callbacks.onFinal?.(finalPayload);
          } catch {
            // 忽略 JSON 解析異常
          }
        } else if (evt.event === 'error') {
          try {
            const errPayload = JSON.parse(evt.data) as ErrorDetail;
            callbacks.onError?.(errPayload);
          } catch {
            callbacks.onError?.({
              code: 'stream_error',
              message: evt.data,
            });
          }
        }
      }
    }
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      return;
    }
    callbacks.onError?.({
      code: 'stream_read_error',
      message: err instanceof Error ? err.message : '串流讀取中斷',
    });
  }
}

/**
 * 取得 MCP 系統狀態與已探索工具清單.
 */
export async function getMcpStatus(): Promise<import('./types').McpStatusResponse> {
  const res = await fetch(`${API_BASE_URL}/api/mcp/status`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!res.ok) {
    throw new Error(`MCP status request failed with status: ${res.status}`);
  }

  return (await res.json()) as import('./types').McpStatusResponse;
}

/**
 * 取得最近 MCP 工具活動紀錄清單.
 */
export async function getMcpActivity(
  limit: number = 20,
): Promise<import('./types').McpActivityResponse> {
  const res = await fetch(`${API_BASE_URL}/api/mcp/activity?limit=${limit}`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
  });

  if (!res.ok) {
    throw new Error(`MCP activity request failed with status: ${res.status}`);
  }

  return (await res.json()) as import('./types').McpActivityResponse;
}

