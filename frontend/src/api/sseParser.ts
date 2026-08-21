/**
 * Robust Server-Sent Events (SSE) Stream Parser.
 *
 * 能夠處理：
 * 1. 跨 Chunk 切割的 Event (Split across chunks)
 * 2. 一個 Chunk 內包含多個 Events (Multiple events in one chunk)
 * 3. 不同的換行符號 (\r\n vs \n)
 * 4. 任意 event: 與 data: 欄位
 */

export interface ParsedSSEEvent {
  event: string;
  data: string;
}

export class SSEParser {
  private buffer: string = '';

  /**
   * 輸入新的字串 chunk 並解析出所有完整的 SSE 事件.
   */
  public push(chunk: string): ParsedSSEEvent[] {
    this.buffer += chunk.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
    const events: ParsedSSEEvent[] = [];

    // SSE 事件以雙換行 \n\n 作為邊界
    while (true) {
      const boundaryIndex = this.buffer.indexOf('\n\n');
      if (boundaryIndex === -1) {
        break;
      }

      const eventBlock = this.buffer.slice(0, boundaryIndex);
      this.buffer = this.buffer.slice(boundaryIndex + 2);

      const parsed = this.parseEventBlock(eventBlock);
      if (parsed) {
        events.push(parsed);
      }
    }

    return events;
  }

  /**
   * 處理單一事件區塊.
   */
  private parseEventBlock(block: string): ParsedSSEEvent | null {
    const lines = block.split('\n');
    let eventName = 'message';
    const dataLines: string[] = [];

    for (const line of lines) {
      if (!line || line.startsWith(':')) {
        // 註解行或空行
        continue;
      }

      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim());
      }
    }

    if (dataLines.length === 0) {
      return null;
    }

    return {
      event: eventName,
      data: dataLines.join('\n'),
    };
  }

  /**
   * 重設內部緩衝區.
   */
  public reset(): void {
    this.buffer = '';
  }
}
