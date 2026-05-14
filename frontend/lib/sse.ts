// Parser SSE mínimo: separa frames por "\n\n", extrae `event:` y agrupa
// líneas `data:` con "\n" entre ellas (espec. SSE). Portado del widget Alpine
// previo. Devuelve un async iterator de { event, data }.

export type SseFrame = { event: string; data: string };

export async function* parseSSE(stream: ReadableStream<Uint8Array>): AsyncGenerator<SseFrame> {
  const reader = stream.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);

        let event = "message";
        const dataLines: string[] = [];
        for (const line of raw.split("\n")) {
          if (line.startsWith("event:")) {
            event = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            // Una sola línea de espacio tras "data:" según la espec.
            dataLines.push(line.startsWith("data: ") ? line.slice(6) : line.slice(5));
          }
        }
        yield { event, data: dataLines.join("\n") };
      }
    }
  } finally {
    reader.releaseLock();
  }
}
