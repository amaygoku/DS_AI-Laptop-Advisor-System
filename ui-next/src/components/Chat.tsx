"use client";

import { useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import LaptopCards from "./LaptopCards";
import DebugPanel from "./DebugPanel";

type RecommendResponse = {
  intent?: any;
  query_used?: any;
  total_after_filter?: number;
  results?: any[];
  advice_text?: string;
};

type Msg =
  | { role: "assistant"; type: "text"; text: string }
  | { role: "user"; type: "text"; text: string }
  | { role: "assistant"; type: "cards"; results: any[] };

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

const INITIAL_MESSAGE: Msg = {
  role: "assistant",
  type: "text",
  text: 'Bạn mô tả nhu cầu bằng tiếng Việt (ví dụ: "mình cần laptop học IT và chơi game, ưu tiên nhẹ, giá hợp lý").'
};

export default function Chat() {
  const [messages, setMessages] = useState<Msg[]>([INITIAL_MESSAGE]);
  const [typing, setTyping] = useState(false);
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugData, setDebugData] = useState<any>(null);
  const [userText, setUserText] = useState("");
  const chatRef = useRef<HTMLDivElement | null>(null);

  const canSend = useMemo(() => userText.trim().length > 0 && !typing, [userText, typing]);

  const scrollToBottom = async () => {
    await sleep(0);
    const el = chatRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  };

  const buildPayload = () => {
    return {
      user_text: userText.trim(),
      top_n: 3
    };
  };

  const send = async () => {
    if (!canSend) return;

    const text = userText.trim();
    setUserText("");

    setMessages((m) => [...m, { role: "user", type: "text", text }]);
    setTyping(true);
    await scrollToBottom();

    let data: RecommendResponse | null = null;

    try {
      const payload = buildPayload();
      const r = await fetch("/api/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });

      const ct = r.headers.get("content-type") || "";
      if (ct.includes("application/json")) {
        data = await r.json();
      } else {
        const t = await r.text();
        data = { advice_text: t };
      }

      if (!r.ok) {
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            type: "text",
            text: `Xin lỗi, hệ thống gặp lỗi.\n\n${JSON.stringify(data, null, 2)}`
          }
        ]);
        setDebugData(data);
        return;
      }

      setDebugData({
        intent: data?.intent,
        query_used: data?.query_used,
        total_after_filter: data?.total_after_filter
      });

      // Build messages array - only add cards if there are results
      const newMessages: Msg[] = [
        { role: "assistant", type: "text", text: data?.advice_text || "(Không có advice_text)" }
      ];

      // Only show laptop cards if there are actual results
      if (data?.results && data.results.length > 0) {
        newMessages.push({ role: "assistant", type: "cards", results: data.results });
      }

      setMessages((m) => [...m, ...newMessages]);
    } catch (e: any) {
      setMessages((m) => [
        ...m,
        { role: "assistant", type: "text", text: `Lỗi gọi backend: ${e?.message || String(e)}` }
      ]);
      setDebugData({ error: String(e?.message || e) });
    } finally {
      setTyping(false);
      await scrollToBottom();
    }
  };

  const onKeyDown: React.KeyboardEventHandler<HTMLTextAreaElement> = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <>
      <section className="chat" ref={chatRef}>
        {messages.map((msg, idx) => {
          if (msg.type === "text") {
            return (
              <div key={idx} className={`msg ${msg.role}`}>
                <div className="bubble markdown-content">
                  <ReactMarkdown>{msg.text}</ReactMarkdown>
                </div>
              </div>
            );
          }
          return (
            <div key={idx} className="msg assistant">
              <div className="bubble">
                <LaptopCards results={msg.results} />
              </div>
            </div>
          );
        })}

        {typing && (
          <div className="msg assistant">
            <div className="bubble">
              <div className="typing">
                <span className="dot" />
                <span className="dot" />
                <span className="dot" />
              </div>
            </div>
          </div>
        )}
      </section>

      <footer className="composer">
        <div className="composeBox">
          <textarea
            value={userText}
            onChange={(e) => setUserText(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Mô tả nhu cầu của bạn (VD: laptop học IT, chơi game, giá rẻ)..."
            rows={2}
          />
          <div className="composeActions">
            <button className="ghost" onClick={() => setDebugOpen((v) => !v)} type="button">
              Debug
            </button>
            <button disabled={!canSend} onClick={send} type="button">
              Gửi
            </button>
          </div>
        </div>

        <DebugPanel open={debugOpen} data={debugData} />
      </footer>
    </>
  );
}
