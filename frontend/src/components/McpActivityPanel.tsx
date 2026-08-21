import React, { useState, useEffect, useCallback } from 'react';
import {
  Wrench,
  Server,
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  AlertCircle,
  Shield,
  ShieldAlert,
} from 'lucide-react';
import { McpActivityItem, McpStatusResponse } from '../api/types';
import { getMcpActivity, getMcpStatus } from '../api/client';

interface McpActivityPanelProps {
  isOpen?: boolean;
}

export const McpActivityPanel: React.FC<McpActivityPanelProps> = ({ isOpen = true }) => {
  const [statusData, setStatusData] = useState<McpStatusResponse | null>(null);
  const [activities, setActivities] = useState<McpActivityItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [isToolsExpanded, setIsToolsExpanded] = useState<boolean>(false);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [statusRes, activityRes] = await Promise.all([
        getMcpStatus().catch(() => null),
        getMcpActivity(30).catch(() => null),
      ]);

      if (statusRes) {
        setStatusData(statusRes);
      } else {
        setStatusData({
          status: 'unavailable',
          tool_count: 0,
          server_count: 0,
          tools: [],
        });
      }

      if (activityRes) {
        setActivities(activityRes.items || []);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'MCP status unavailable');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    fetchData();
    const timer = setInterval(fetchData, 4000);
    return () => clearInterval(timer);
  }, [isOpen, fetchData]);

  const isOnline = statusData?.status === 'online';

  const formatDuration = (ms?: number | null) => {
    if (ms === undefined || ms === null) return null;
    if (ms >= 1000) {
      return `${(ms / 1000).toFixed(2)}s`;
    }
    return `${Math.round(ms)}ms`;
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'success':
        return <CheckCircle2 className="text-green" size={15} />;
      case 'failed':
        return <XCircle className="text-red" size={15} />;
      case 'timeout':
        return <Clock className="text-amber" size={15} />;
      default:
        return <Activity className="text-blue spin" size={15} />;
    }
  };

  return (
    <div className="mcp-panel-container" aria-label="MCP Activity & Inspector Panel">
      {/* 1. MCP Overview Banner */}
      <div className="mcp-overview-card">
        <div className="mcp-status-row">
          <div className="mcp-status-title">
            <Wrench size={16} className="text-orange" />
            <span>MCP Subsystem</span>
          </div>

          <div className="mcp-header-actions">
            <button
              type="button"
              className="btn-refresh"
              onClick={fetchData}
              title="Refresh MCP Status"
              aria-label="Refresh MCP Status"
            >
              <RefreshCw size={13} className={isLoading ? 'spin' : ''} />
            </button>

            <span className={`status-pill ${isOnline ? 'online' : 'offline'}`}>
              <span className={`status-dot ${isOnline ? 'online-dot' : 'offline-dot'}`} />
              <span className="status-text">{isOnline ? 'Online' : 'Unavailable'}</span>
            </span>
          </div>
        </div>

        {error && (
          <div className="mcp-error-banner">
            <AlertCircle size={13} className="text-red" />
            <span>{error}</span>
          </div>
        )}

        {/* Metrics Grid */}
        <div className="mcp-metrics-grid">
          <div className="mcp-metric-card">
            <div className="metric-label">Tools Available</div>
            <div className="metric-value">{statusData?.tool_count ?? 0}</div>
          </div>
          <div className="mcp-metric-card">
            <div className="metric-label">Servers Connected</div>
            <div className="metric-value">{statusData?.server_count ?? 0}</div>
          </div>
        </div>
      </div>

      {/* 2. Collapsible Available Tools */}
      {statusData && statusData.tools.length > 0 && (
        <div className="mcp-tools-section">
          <button
            type="button"
            className="mcp-tools-toggle"
            onClick={() => setIsToolsExpanded(!isToolsExpanded)}
            aria-expanded={isToolsExpanded}
          >
            <div className="tools-toggle-title">
              <Server size={14} className="text-muted" />
              <span>Available Tools ({statusData.tools.length})</span>
            </div>
            {isToolsExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
          </button>

          {isToolsExpanded && (
            <div className="mcp-tools-list">
              {statusData.tools.map((tool) => (
                <div key={tool.name} className="mcp-tool-item">
                  <div className="tool-item-header">
                    <span className="tool-name">{tool.name}</span>
                    <span
                      className={`safety-badge ${
                        tool.safety_level === 'read_only' ? 'safety-read' : 'safety-write'
                      }`}
                    >
                      {tool.safety_level === 'read_only' ? (
                        <>
                          <Shield size={10} /> Read only
                        </>
                      ) : (
                        <>
                          <ShieldAlert size={10} /> Writes data
                        </>
                      )}
                    </span>
                  </div>
                  <div className="tool-item-meta">
                    <span className="tool-server-tag">{tool.server}</span>
                    {tool.description && <span className="tool-desc">{tool.description}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 3. Recent Activity Section */}
      <div className="mcp-activity-section">
        <div className="activity-section-header">
          <Activity size={14} className="text-accent" />
          <span>Recent Activity</span>
        </div>

        <div className="mcp-activity-list">
          {activities.length === 0 ? (
            <div className="activity-empty-state">
              <Activity className="empty-icon text-muted" size={24} />
              <p className="empty-title">No MCP Activity Yet</p>
              <p className="empty-desc">
                Execute an MCP tool (e.g. ask &quot;現在幾點？&quot;) to observe live global tool calls.
              </p>
            </div>
          ) : (
            activities.map((act) => (
              <div
                key={act.activity_id}
                className={`mcp-activity-item activity-status-${act.status}`}
              >
                <div className="activity-icon-container">{getStatusIcon(act.status)}</div>
                <div className="activity-body">
                  <div className="activity-header-row">
                    <span className="activity-tool-name">{act.tool_name}</span>
                    {act.duration_ms !== undefined && act.duration_ms !== null && (
                      <span className="activity-duration">{formatDuration(act.duration_ms)}</span>
                    )}
                  </div>
                  <div className="activity-meta-row">
                    <span className="activity-server-tag">{act.server_name}</span>
                    <span className={`activity-status-tag tag-${act.status}`}>{act.status}</span>
                    {act.error_summary && (
                      <span className="activity-error-msg">{act.error_summary}</span>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
