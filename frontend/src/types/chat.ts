import { TraceEvent } from '../api/types';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  status?: 'sending' | 'streaming' | 'complete' | 'partial_success' | 'error';
  planId?: string | null;
  trace?: TraceEvent[];
  error?: string | null;
  timestamp?: number;
}
