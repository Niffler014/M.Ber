import { describe, it, expect, beforeEach } from 'vitest';
import { SSEParser } from '../src/api/sseParser';

describe('SSEParser', () => {
  let parser: SSEParser;

  beforeEach(() => {
    parser = new SSEParser();
  });

  it('should parse a single complete SSE event', () => {
    const chunk = 'event: trace\ndata: {"event_type":"task_started"}\n\n';
    const events = parser.push(chunk);

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('trace');
    expect(JSON.parse(events[0].data)).toEqual({ event_type: 'task_started' });
  });

  it('should parse multiple events in a single chunk', () => {
    const chunk =
      'event: trace\ndata: {"event_type":"task_started"}\n\n' +
      'event: trace\ndata: {"event_type":"task_completed"}\n\n' +
      'event: final\ndata: {"message":"Done","status":"success"}\n\n';

    const events = parser.push(chunk);

    expect(events).toHaveLength(3);
    expect(events[0].event).toBe('trace');
    expect(events[1].event).toBe('trace');
    expect(events[2].event).toBe('final');
    expect(JSON.parse(events[2].data)).toEqual({ message: 'Done', status: 'success' });
  });

  it('should handle an event split across multiple chunks', () => {
    const chunk1 = 'event: trace\ndata: {"event_';
    const chunk2 = 'type":"planning_';
    const chunk3 = 'started"}\n\n';

    const events1 = parser.push(chunk1);
    expect(events1).toHaveLength(0);

    const events2 = parser.push(chunk2);
    expect(events2).toHaveLength(0);

    const events3 = parser.push(chunk3);
    expect(events3).toHaveLength(1);
    expect(events3[0].event).toBe('trace');
    expect(JSON.parse(events3[0].data)).toEqual({ event_type: 'planning_started' });
  });

  it('should parse error events', () => {
    const chunk = 'event: error\ndata: {"code":"internal_error","message":"Server failed"}\n\n';
    const events = parser.push(chunk);

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('error');
    expect(JSON.parse(events[0].data)).toEqual({
      code: 'internal_error',
      message: 'Server failed',
    });
  });

  it('should handle Windows CRLF line breaks seamlessly', () => {
    const chunk = 'event: trace\r\ndata: {"status":"success"}\r\n\r\n';
    const events = parser.push(chunk);

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('trace');
    expect(JSON.parse(events[0].data)).toEqual({ status: 'success' });
  });

  it('should ignore comment lines starting with colon', () => {
    const chunk = ': keep-alive heartbeat\nevent: trace\ndata: {"event_type":"heartbeat"}\n\n';
    const events = parser.push(chunk);

    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('trace');
  });

  it('should support reset buffer', () => {
    parser.push('event: partial_');
    parser.reset();
    const events = parser.push('event: trace\ndata: {"ok":true}\n\n');
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe('trace');
  });
});
