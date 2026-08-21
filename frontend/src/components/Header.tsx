import React from 'react';
import { Activity, Cpu, Layers } from 'lucide-react';
import { HealthResponse } from '../api/types';

interface HeaderProps {
  health: HealthResponse | null;
  isCheckingHealth: boolean;
  isTraceOpen?: boolean;
  onToggleTrace?: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  health,
  isCheckingHealth,
  isTraceOpen,
  onToggleTrace,
}) => {
  const isOnline = Boolean(health && health.status === 'ok');

  return (
    <header className="app-header">
      <div className="header-brand">
        <div className="brand-logo">
          <Cpu className="brand-icon" size={22} />
        </div>
        <div className="brand-info">
          <div className="brand-title">
            M.Ber
            <span className="brand-badge">Agentic</span>
          </div>
          <div className="brand-subtitle">Personal AI Orchestrator</div>
        </div>
      </div>

      <div className="header-actions">
        {/* Mobile Trace Toggle Button */}
        {onToggleTrace && (
          <button
            type="button"
            className={`btn-icon-toggle ${isTraceOpen ? 'active' : ''}`}
            onClick={onToggleTrace}
            aria-label="Toggle Execution Trace Panel"
            title="Toggle Execution Trace"
          >
            <Layers size={18} />
            <span className="btn-toggle-text">Trace</span>
          </button>
        )}

        {/* Backend Status Indicator */}
        <div
          className={`status-pill ${isOnline ? 'online' : 'offline'}`}
          role="status"
          aria-live="polite"
        >
          {isCheckingHealth ? (
            <>
              <Activity className="status-icon spin" size={14} />
              <span className="status-text">Connecting...</span>
            </>
          ) : isOnline ? (
            <>
              <span className="status-dot online-dot" />
              <span className="status-text">
                Online <span className="status-version">v{health?.version}</span>
              </span>
            </>
          ) : (
            <>
              <span className="status-dot offline-dot" />
              <span className="status-text">Backend Offline</span>
            </>
          )}
        </div>
      </div>
    </header>
  );
};
