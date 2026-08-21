import React, { useRef, useEffect, useState } from 'react';
import { Layers, Activity, ChevronRight, CheckCircle2, AlertCircle, Wrench } from 'lucide-react';
import { TraceEvent } from '../api/types';
import { TraceItem } from './TraceItem';
import { McpActivityPanel } from './McpActivityPanel';

interface ExecutionTracePanelProps {
  trace: TraceEvent[];
  isStreaming: boolean;
  isOpen?: boolean;
  onClose?: () => void;
  planId?: string | null;
  overallStatus?: string | null;
}

export const ExecutionTracePanel: React.FC<ExecutionTracePanelProps> = ({
  trace,
  isStreaming,
  isOpen = true,
  onClose,
  planId,
  overallStatus,
}) => {
  const [activeTab, setActiveTab] = useState<'trace' | 'mcp'>('trace');
  const scrollRef = useRef<HTMLDivElement>(null);

  // 當有新事件推入時自動切換至 trace tab 並滾動至最底部
  useEffect(() => {
    if (isStreaming) {
      setActiveTab('trace');
    }
  }, [isStreaming]);

  useEffect(() => {
    if (activeTab === 'trace' && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [trace, activeTab]);

  const hasEvents = trace.length > 0;

  return (
    <aside
      className={`trace-panel ${isOpen ? 'open' : 'closed'}`}
      aria-label="Execution & Activity Panel"
    >
      {/* Tab Header Bar */}
      <div className="panel-tab-bar">
        <button
          type="button"
          className={`panel-tab-btn ${activeTab === 'trace' ? 'active' : ''}`}
          onClick={() => setActiveTab('trace')}
          aria-label="Execution Trace Tab"
        >
          <Layers size={15} />
          <span>Trace</span>
          {isStreaming && (
            <span className="tab-live-badge">
              <span className="live-pulse" /> LIVE
            </span>
          )}
        </button>

        <button
          type="button"
          className={`panel-tab-btn ${activeTab === 'mcp' ? 'active' : ''}`}
          onClick={() => setActiveTab('mcp')}
          aria-label="MCP Activity Tab"
        >
          <Wrench size={14} className="text-orange" />
          <span>MCP Activity</span>
        </button>

        <div className="panel-tab-actions">
          {overallStatus && activeTab === 'trace' && (
            <span className={`status-badge badge-${overallStatus}`}>
              {overallStatus === 'success' && <CheckCircle2 size={11} />}
              {overallStatus === 'partial_success' && <AlertCircle size={11} />}
              {overallStatus}
            </span>
          )}
          {onClose && (
            <button
              type="button"
              className="btn-close-trace"
              onClick={onClose}
              aria-label="Close panel"
            >
              <ChevronRight size={18} />
            </button>
          )}
        </div>
      </div>

      {activeTab === 'trace' ? (
        <>
          {planId && (
            <div className="trace-plan-banner">
              <span className="plan-label">Plan ID:</span>
              <code className="plan-id">{planId}</code>
            </div>
          )}

          <div className="trace-panel-body" ref={scrollRef}>
            {!hasEvents ? (
              <div className="trace-empty-state">
                <Activity className="empty-icon text-muted" size={32} />
                <p className="empty-title">No Active Execution</p>
                <p className="empty-desc">
                  Send a request to observe real-time orchestration across Planner, LOCAL, MCP, and A2A agents.
                </p>
              </div>
            ) : (
              <div className="trace-timeline">
                {trace.map((evt, idx) => (
                  <TraceItem
                    key={evt.event_id || `${evt.event_type}-${idx}`}
                    event={evt}
                    isLatest={idx === trace.length - 1}
                  />
                ))}
              </div>
            )}
          </div>
        </>
      ) : (
        <div className="trace-panel-body">
          <McpActivityPanel isOpen={isOpen && activeTab === 'mcp'} />
        </div>
      )}
    </aside>
  );
};
