import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { McpActivityPanel } from '../src/components/McpActivityPanel';
import * as apiClient from '../src/api/client';

describe('McpActivityPanel Component', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders MCP online status, tool count, and server count', async () => {
    vi.spyOn(apiClient, 'getMcpStatus').mockResolvedValue({
      status: 'online',
      tool_count: 8,
      server_count: 2,
      tools: [
        {
          name: 'get_current_time',
          server: 'own_server',
          safety_level: 'read_only',
          description: '取得當前時間',
        },
      ],
    });

    vi.spyOn(apiClient, 'getMcpActivity').mockResolvedValue({
      items: [],
      total: 0,
    });

    render(<McpActivityPanel isOpen={true} />);

    await waitFor(() => {
      expect(screen.getByText('MCP Subsystem')).toBeInTheDocument();
      expect(screen.getByText('Online')).toBeInTheDocument();
      expect(screen.getByText('8')).toBeInTheDocument();
      expect(screen.getByText('2')).toBeInTheDocument();
    });
  });

  it('renders available tools and toggles collapsible list', async () => {
    vi.spyOn(apiClient, 'getMcpStatus').mockResolvedValue({
      status: 'online',
      tool_count: 2,
      server_count: 1,
      tools: [
        {
          name: 'get_current_time',
          server: 'own_server',
          safety_level: 'read_only',
          description: '取得時間',
        },
        {
          name: 'calendar_add_event',
          server: 'calendar',
          safety_level: 'write',
          description: '新增行程',
        },
      ],
    });

    vi.spyOn(apiClient, 'getMcpActivity').mockResolvedValue({
      items: [],
      total: 0,
    });

    render(<McpActivityPanel isOpen={true} />);

    await waitFor(() => {
      expect(screen.getByText(/Available Tools \(2\)/i)).toBeInTheDocument();
    });

    // Expand tools
    fireEvent.click(screen.getByText(/Available Tools \(2\)/i));

    expect(screen.getByText('get_current_time')).toBeInTheDocument();
    expect(screen.getByText('calendar_add_event')).toBeInTheDocument();
    expect(screen.getByText('Read only')).toBeInTheDocument();
    expect(screen.getByText('Writes data')).toBeInTheDocument();
  });

  it('renders recent MCP activity items and format durations', async () => {
    vi.spyOn(apiClient, 'getMcpStatus').mockResolvedValue({
      status: 'online',
      tool_count: 1,
      server_count: 1,
      tools: [],
    });

    vi.spyOn(apiClient, 'getMcpActivity').mockResolvedValue({
      items: [
        {
          activity_id: 'act_1',
          tool_name: 'get_current_time',
          server_name: 'own_server',
          status: 'success',
          duration_ms: 120.4,
          timestamp: '2026-08-21T16:00:00Z',
        },
        {
          activity_id: 'act_2',
          tool_name: 'query_events',
          server_name: 'calendar',
          status: 'failed',
          duration_ms: 340.0,
          timestamp: '2026-08-21T16:00:01Z',
          error_summary: 'Connection refused',
        },
      ],
      total: 2,
    });

    render(<McpActivityPanel isOpen={true} />);

    await waitFor(() => {
      expect(screen.getByText('get_current_time')).toBeInTheDocument();
      expect(screen.getByText('120ms')).toBeInTheDocument();
      expect(screen.getByText('query_events')).toBeInTheDocument();
      expect(screen.getByText('Connection refused')).toBeInTheDocument();
    });
  });

  it('renders empty activity state when no activity is present', async () => {
    vi.spyOn(apiClient, 'getMcpStatus').mockResolvedValue({
      status: 'online',
      tool_count: 0,
      server_count: 0,
      tools: [],
    });

    vi.spyOn(apiClient, 'getMcpActivity').mockResolvedValue({
      items: [],
      total: 0,
    });

    render(<McpActivityPanel isOpen={true} />);

    await waitFor(() => {
      expect(screen.getByText('No MCP Activity Yet')).toBeInTheDocument();
    });
  });

  it('handles MCP API failure gracefully without crashing', async () => {
    vi.spyOn(apiClient, 'getMcpStatus').mockRejectedValue(new Error('MCP Server Offline'));
    vi.spyOn(apiClient, 'getMcpActivity').mockRejectedValue(new Error('Activity error'));

    render(<McpActivityPanel isOpen={true} />);

    await waitFor(() => {
      expect(screen.getByText('Unavailable')).toBeInTheDocument();
    });
  });
});
