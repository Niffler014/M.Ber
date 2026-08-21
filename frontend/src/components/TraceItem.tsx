import React from 'react';
import {
  CheckCircle2,
  XCircle,
  Clock,
  MinusCircle,
  Loader2,
  Brain,
  Share2,
  Wrench,
  Database,
  Layers,
  Sparkles,
} from 'lucide-react';
import { TraceEvent } from '../api/types';

interface TraceItemProps {
  event: TraceEvent;
  isLatest?: boolean;
}

export const TraceItem: React.FC<TraceItemProps> = ({ event }) => {
  const { event_type, execution_type, target, status, message, duration_ms, metadata } = event;

  // 1. 決定適當圖示
  const getIcon = () => {
    if (status === 'running') {
      return <Loader2 className="trace-status-icon spin text-blue" size={16} />;
    }
    if (status === 'success') {
      return <CheckCircle2 className="trace-status-icon text-green" size={16} />;
    }
    if (status === 'failed') {
      return <XCircle className="trace-status-icon text-red" size={16} />;
    }
    if (status === 'skipped') {
      return <MinusCircle className="trace-status-icon text-amber" size={16} />;
    }
    if (status === 'timeout') {
      return <Clock className="trace-status-icon text-amber" size={16} />;
    }

    // 依事件類型決定預設圖示
    switch (event_type) {
      case 'planning_started':
      case 'plan_created':
        return <Brain className="trace-type-icon text-purple" size={16} />;
      case 'task_started':
      case 'task_completed':
      case 'task_failed':
      case 'task_skipped':
        if (execution_type === 'a2a') {
          return <Share2 className="trace-type-icon text-cyan" size={16} />;
        }
        if (execution_type === 'mcp') {
          return <Wrench className="trace-type-icon text-orange" size={16} />;
        }
        if (target === 'memory_store' || target?.includes('memory')) {
          return <Database className="trace-type-icon text-emerald" size={16} />;
        }
        return <Layers className="trace-type-icon text-slate" size={16} />;
      case 'aggregation_completed':
      case 'response_ready':
        return <Sparkles className="trace-type-icon text-indigo" size={16} />;
      default:
        return <CheckCircle2 className="trace-type-icon text-slate" size={16} />;
    }
  };

  // 2. 決定親切易懂的標題文字
  const getLabel = () => {
    switch (event_type) {
      case 'request_received':
        return 'Request Received';
      case 'planning_started':
        return 'Planning Analysis';
      case 'plan_created':
        const taskCount = (metadata?.task_count as number) || 1;
        return `Plan Created (${taskCount} ${taskCount === 1 ? 'task' : 'tasks'})`;
      case 'task_started':
        if (execution_type === 'a2a') return 'PCforge Working';
        if (execution_type === 'mcp') return `MCP Tool: ${target || 'Calling'}`;
        if (target === 'memory_store' || target?.includes('memory')) return 'Saving Memory';
        return `Local Reasoning: ${target || 'Processing'}`;
      case 'task_completed':
        if (execution_type === 'a2a') return 'PCforge Complete';
        if (execution_type === 'mcp') return `MCP Tool Complete`;
        if (target === 'memory_store' || target?.includes('memory')) return 'Memory Saved';
        return `Task Complete`;
      case 'task_failed':
        if (execution_type === 'a2a') return 'PCforge Failed';
        if (execution_type === 'mcp') return 'MCP Tool Failed';
        if (target === 'memory_store' || target?.includes('memory')) return 'Memory Save Failed';
        return 'Task Failed';
      case 'task_skipped':
        if (target === 'memory_store' || target?.includes('memory')) return 'Memory Skipped';
        return 'Task Skipped';
      case 'task_timeout':
        return 'Task Timeout';
      case 'aggregation_completed':
        return 'Aggregating Results';
      case 'response_ready':
        return 'Synthesizing Response';
      default:
        return event_type.replace(/_/g, ' ');
    }
  };

  // 3. 耗時格式化
  const formatDuration = (ms?: number | null) => {
    if (ms === undefined || ms === null) return null;
    if (ms >= 1000) {
      return `${(ms / 1000).toFixed(2)}s`;
    }
    return `${Math.round(ms)}ms`;
  };

  return (
    <div className={`trace-item trace-status-${status || 'default'}`}>
      <div className="trace-icon-container">{getIcon()}</div>
      <div className="trace-body">
        <div className="trace-header-row">
          <span className="trace-label">{getLabel()}</span>
          {duration_ms !== undefined && duration_ms !== null && (
            <span className="trace-duration">{formatDuration(duration_ms)}</span>
          )}
        </div>

        {/* 顯示細節目標或補充訊息 */}
        {(target || message || execution_type) && (
          <div className="trace-meta-row">
            {execution_type && (
              <span className={`trace-tag tag-${execution_type}`}>{execution_type.toUpperCase()}</span>
            )}
            {target && <span className="trace-target">{target}</span>}
            {message && !target && <span className="trace-msg">{message}</span>}
          </div>
        )}
      </div>
    </div>
  );
};
