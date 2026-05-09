// Alpine component for the chat bubble. Uses fetch + ReadableStream to consume
// SSE from POST /api/chat. (HTMX's SSE extension assumes a long-lived GET
// subscription; we want POST → stream → close, so plain fetch is simpler.)

window.chat = function () {
    return {
        open: false,
        input: "",
        streaming: false,
        thinking: false,
        messages: [],

        render(text) {
            // marked.js may not be ready in tests; degrade to plain text.
            try {
                return window.marked ? window.marked.parse(text || "") : text;
            } catch (e) {
                return text;
            }
        },

        scrollDown() {
            this.$nextTick(() => {
                const el = this.$refs.scroll;
                if (el) el.scrollTop = el.scrollHeight;
            });
        },

        async send() {
            const question = this.input.trim();
            if (!question || this.streaming) return;
            this.input = "";

            const history = this.messages.map((m) => ({ role: m.role, content: m.content }));
            this.messages.push({ role: "user", content: question });
            this.scrollDown();

            this.streaming = true;
            this.thinking = true;

            const assistant = { role: "assistant", content: "", sources: [] };
            this.messages.push(assistant);
            // The push above triggers reactivity; but we'll mutate in place below.
            const idx = this.messages.length - 1;

            try {
                const resp = await fetch("/api/chat", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
                    body: JSON.stringify({ question, history }),
                });
                if (!resp.ok || !resp.body) {
                    throw new Error(`HTTP ${resp.status}`);
                }

                const reader = resp.body.getReader();
                const decoder = new TextDecoder("utf-8");
                let buffer = "";

                while (true) {
                    const { value, done } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });

                    // SSE frames are separated by a blank line.
                    let sep;
                    while ((sep = buffer.indexOf("\n\n")) !== -1) {
                        const frame = buffer.slice(0, sep);
                        buffer = buffer.slice(sep + 2);
                        this._handleFrame(frame, idx);
                    }
                }
            } catch (err) {
                this.messages[idx].content =
                    "Hubo un problema al conectar con el asistente. Intenta de nuevo en unos segundos.";
                console.error(err);
            } finally {
                this.streaming = false;
                this.thinking = false;
                this.scrollDown();
            }
        },

        _handleFrame(frame, idx) {
            let event = "message";
            const dataLines = [];
            for (const line of frame.split("\n")) {
                if (line.startsWith("event:")) event = line.slice(6).trim();
                else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
            }
            const data = dataLines.join("\n");

            if (event === "sources") {
                try {
                    this.messages[idx].sources = JSON.parse(data);
                } catch (e) {
                    /* ignore */
                }
            } else if (event === "token") {
                this.thinking = false;
                this.messages[idx].content += data;
                this.scrollDown();
            } else if (event === "done") {
                this.thinking = false;
            } else if (event === "error") {
                let msg = "Error inesperado.";
                try {
                    const parsed = JSON.parse(data);
                    msg = parsed.error || msg;
                } catch (e) {
                    /* ignore */
                }
                this.messages[idx].content = msg;
            }
        },
    };
};
