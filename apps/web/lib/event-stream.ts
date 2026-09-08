/** Decode SSE framing across arbitrary network/UTF-8 boundaries. */
export async function* readEventStream(body: ReadableStream<Uint8Array>): AsyncGenerator<Record<string, unknown>> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let data: string[] = [];
  let dataLength = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });
      if (buffer.length > 1_000_000) throw new Error("Stream frame exceeds the supported size.");
      while (true) {
        const newline = /\r\n|\r|\n/.exec(buffer);
        if (!newline || (!done && newline[0] === "\r" && newline.index === buffer.length - 1)) break;
        const line = buffer.slice(0, newline.index);
        buffer = buffer.slice(newline.index + newline[0].length);
        if (!line) {
          if (data.length) {
            const event: unknown = JSON.parse(data.join("\n"));
            if (event && typeof event === "object" && !Array.isArray(event)) yield event as Record<string, unknown>;
            data = [];
            dataLength = 0;
          }
        } else if (line === "data" || line.startsWith("data:")) {
          data.push(line.slice(5).replace(/^ /, ""));
          dataLength += line.length;
          if (dataLength > 1_000_000) throw new Error("Stream frame exceeds the supported size.");
        }
      }
      // An unterminated frame is not a complete SSE event.
      if (done) break;
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
