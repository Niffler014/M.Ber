/**
 * M.Ber Public API Data Transfer Objects (DTOs).
 *
 * 嚴格對應後端公用 API 契約，不引入後端內部模型。
 */

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string | null;
}

export interface TraceEvent {
  event_id?: string | null;
  event_type: string;
  plan_id?: string | null;
  task_id?: string | null;
  execution_type?: 'local' | 'mcp' | 'a2a' | string | null;
  target?: string | null;
  status?: 'running' | 'success' | 'failed' | 'skipped' | 'timeout' | string | null;
  message?: string | null;
  duration_ms?: number | null;
  metadata?: Record<string, unknown> | null;
}

export interface ChatResponse {
  message: string;
  status: 'success' | 'partial_success' | 'failed' | string;
  plan_id?: string | null;
  conversation_id?: string | null;
  trace: TraceEvent[];
}

export interface FinalStreamPayload {
  message: string;
  status: 'success' | 'partial_success' | 'failed' | string;
  plan_id?: string | null;
  conversation_id?: string | null;
}

export interface ErrorDetail {
  code: string;
  message: string;
}

export interface ErrorResponse {
  error: ErrorDetail;
}

export interface McpToolInfo {
  name: string;
  server: string;
  safety_level: 'read_only' | 'write' | string;
  description?: string | null;
}

export interface McpStatusResponse {
  status: 'online' | 'unavailable' | string;
  tool_count: number;
  server_count: number;
  tools: McpToolInfo[];
}

export interface McpActivityItem {
  activity_id: string;
  tool_name: string;
  server_name: string;
  status: 'success' | 'failed' | 'timeout' | 'running' | string;
  duration_ms?: number | null;
  timestamp: string;
  task_id?: string | null;
  safety_level?: string | null;
  error_summary?: string | null;
}

export interface McpActivityResponse {
  items: McpActivityItem[];
  total: number;
}

