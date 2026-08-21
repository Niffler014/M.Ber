import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { App } from '../src/App';
import * as apiClient from '../src/api/client';

describe('App Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders header and backend online status when health check succeeds', async () => {
    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'ok',
      service: 'mber',
      version: '0.7.0',
    });

    render(<App />);

    expect(screen.getByText('M.Ber')).toBeInTheDocument();
    expect(screen.getByText('Personal AI Orchestrator')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/Online/i)).toBeInTheDocument();
      expect(screen.getByText(/v0.7.0/i)).toBeInTheDocument();
    });
  });

  it('renders backend offline status when health check fails', async () => {
    vi.spyOn(apiClient, 'getHealth').mockRejectedValue(new Error('Network error'));

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/Backend Offline/i)).toBeInTheDocument();
    });
  });

  it('renders demo suggestion cards on empty chat and clicking populates/sends request', async () => {
    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'ok',
      service: 'mber',
      version: '0.7.0',
    });

    const streamSpy = vi.spyOn(apiClient, 'streamChat').mockImplementation(
      async (_msg, _cid, callbacks) => {
        callbacks.onTrace?.({
          event_type: 'planning_started',
          status: 'running',
        });
        callbacks.onFinal?.({
          message: '這是電腦配單結果',
          status: 'success',
          plan_id: 'plan_123',
        });
      }
    );

    render(<App />);

    // Check suggestion cards
    expect(screen.getByText('PCforge 組裝建議')).toBeInTheDocument();
    expect(screen.getByText('MCP 時間工具')).toBeInTheDocument();
    expect(screen.getByText('架構概念教學')).toBeInTheDocument();

    // Click suggestion card
    fireEvent.click(screen.getByText('PCforge 組裝建議'));

    await waitFor(() => {
      expect(streamSpy).toHaveBeenCalledWith(
        '幫我配一台 40000 元遊戲電腦',
        expect.any(String),
        expect.any(Object)
      );
      expect(screen.getByText('這是電腦配單結果')).toBeInTheDocument();
    });
  });

  it('sends message on Enter key, shows trace events and renders final response', async () => {
    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'ok',
      service: 'mber',
      version: '0.7.0',
    });

    vi.spyOn(apiClient, 'streamChat').mockImplementation(
      async (_msg, _cid, callbacks) => {
        callbacks.onTrace?.({
          event_type: 'planning_started',
          status: 'running',
        });
        callbacks.onTrace?.({
          event_type: 'task_started',
          execution_type: 'a2a',
          target: 'pc_recommendation',
          status: 'running',
        });
        callbacks.onTrace?.({
          event_type: 'task_completed',
          execution_type: 'a2a',
          status: 'success',
          duration_ms: 1200,
        });
        callbacks.onFinal?.({
          message: '### PC 配單完成\n- CPU: AMD Ryzen 5 7500F',
          status: 'success',
          plan_id: 'plan_pc_001',
        });
      }
    );

    render(<App />);

    const textarea = screen.getByLabelText('Message input');
    fireEvent.change(textarea, { target: { value: '幫我配電腦' } });

    // Press Enter to submit
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    // User message should appear immediately
    expect(screen.getByText('幫我配電腦')).toBeInTheDocument();

    // Trace events should render
    await waitFor(() => {
      expect(screen.getByText('PCforge Complete')).toBeInTheDocument();
      expect(screen.getByText('1.20s')).toBeInTheDocument();
      expect(screen.getByText('CPU: AMD Ryzen 5 7500F')).toBeInTheDocument();
    });
  });

  it('does not send message on Shift+Enter (allows newline)', async () => {
    const streamSpy = vi.spyOn(apiClient, 'streamChat');

    render(<App />);

    const textarea = screen.getByLabelText('Message input');
    fireEvent.change(textarea, { target: { value: '第一行訊息' } });

    // Press Shift+Enter
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });

    // Should NOT trigger streamChat
    expect(streamSpy).not.toHaveBeenCalled();
  });

  it('renders partial_success badge when response has partial failure', async () => {
    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'ok',
      service: 'mber',
      version: '0.7.0',
    });

    vi.spyOn(apiClient, 'streamChat').mockImplementation(
      async (_msg, _cid, callbacks) => {
        callbacks.onFinal?.({
          message: '推薦單已產出，但記憶存入失敗',
          status: 'partial_success',
          plan_id: 'plan_partial_001',
        });
      }
    );

    render(<App />);

    const textarea = screen.getByLabelText('Message input');
    fireEvent.change(textarea, { target: { value: '配單並記憶' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    await waitFor(() => {
      expect(screen.getByText('Partial Success')).toBeInTheDocument();
      expect(screen.getByText('推薦單已產出，但記憶存入失敗')).toBeInTheDocument();
    });
  });

  it('renders error message when streaming encounters server error', async () => {
    vi.spyOn(apiClient, 'getHealth').mockResolvedValue({
      status: 'ok',
      service: 'mber',
      version: '0.7.0',
    });

    vi.spyOn(apiClient, 'streamChat').mockImplementation(
      async (_msg, _cid, callbacks) => {
        callbacks.onError?.({
          code: 'internal_error',
          message: '伺服器內部發生未預期錯誤，請稍後再試。',
        });
      }
    );

    render(<App />);

    const textarea = screen.getByLabelText('Message input');
    fireEvent.change(textarea, { target: { value: '觸發錯誤' } });
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });

    await waitFor(() => {
      expect(screen.getByText('伺服器內部發生未預期錯誤，請稍後再試。')).toBeInTheDocument();
    });
  });
});
