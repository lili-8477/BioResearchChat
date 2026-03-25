"use client";

import { useState, useEffect, useRef } from "react";
import ChatWindow from "./components/ChatWindow";
import PaperUpload from "./components/PaperUpload";
import Nav from "./components/Nav";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export interface Message {
  role: "user" | "assistant" | "system";
  content: string;
  type: "text" | "plan" | "code" | "output" | "result" | "error" | "system";
  data?: Record<string, any>;
  state?: string;
}

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isConnected, setIsConnected] = useState(false);
  const [agentState, setAgentState] = useState("idle");
  const [paperUrl, setPaperUrl] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Create session and connect WebSocket
  useEffect(() => {
    async function init() {
      try {
        const res = await fetch(`${BACKEND_URL}/api/sessions`, { method: "POST" });
        const data = await res.json();
        const sid = data.session_id;
        setSessionId(sid);

        // Connect WebSocket
        let wsBase: string;
        if (BACKEND_URL.startsWith("http")) {
          wsBase = BACKEND_URL.replace(/^http/, "ws").replace(/\/api\/?$/, "");
        } else {
          const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
          wsBase = `${proto}//${window.location.host}`;
        }
        const ws = new WebSocket(`${wsBase}/ws/${sid}`);

        ws.onopen = () => setIsConnected(true);
        ws.onclose = () => setIsConnected(false);
        ws.onerror = () => setIsConnected(false);

        ws.onmessage = (event) => {
          const msg: Message = JSON.parse(event.data);
          setMessages((prev) => [...prev, msg]);
          if (msg.state) setAgentState(msg.state);
        };

        wsRef.current = ws;
      } catch (err) {
        console.error("Failed to initialize session:", err);
      }
    }

    init();

    return () => {
      wsRef.current?.close();
    };
  }, []);

  const sendMessage = (content: string) => {
    if (!wsRef.current || !content.trim()) return;

    const userMsg: Message = { role: "user", content, type: "text" };
    setMessages((prev) => [...prev, userMsg]);

    wsRef.current.send(
      JSON.stringify({
        content,
        paper_url: paperUrl,
      })
    );

    // Clear URL attachment after first message that uses it
    if (paperUrl) setPaperUrl(null);
    setInput("");
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  return (
    <div className="flex flex-col h-screen">
      <Nav />
      <div className="flex flex-col flex-1 max-w-5xl mx-auto w-full overflow-hidden">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-[var(--border)]">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold">Research Agent</h1>
          <span className="text-xs px-2 py-0.5 rounded bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
            MVP
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`text-xs px-2 py-1 rounded ${
              agentState === "idle" || agentState === "completed"
                ? "bg-[var(--bg-tertiary)] text-[var(--text-secondary)]"
                : agentState === "failed"
                ? "bg-red-900/30 text-red-400"
                : agentState === "awaiting_approval"
                ? "bg-yellow-900/30 text-yellow-400"
                : "bg-indigo-900/30 text-indigo-400"
            }`}
          >
            {agentState.replace("_", " ")}
          </span>
          <div
            className={`w-2 h-2 rounded-full ${
              isConnected ? "bg-[var(--success)]" : "bg-[var(--error)]"
            }`}
            title={isConnected ? "Connected" : "Disconnected"}
          />
        </div>
      </header>

      {/* Chat area */}
      <ChatWindow messages={messages} sessionId={sessionId} backendUrl={BACKEND_URL} />

      {/* Input area */}
      <div className="border-t border-[var(--border)] px-6 py-4">
        <PaperUpload
          onUrl={(url) => {
            setPaperUrl(url);
            setMessages((prev) => [
              ...prev,
              { role: "system", content: `Paper URL attached: ${url}`, type: "system" },
            ]);
          }}
          paperUrl={paperUrl}
        />

        <div className="flex gap-3 mt-3">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              paperUrl
                ? "Ask a research question about the attached paper..."
                : "Paste a paper URL or ask a research question..."
            }
            className="flex-1 bg-[var(--bg-secondary)] border border-[var(--border)] rounded-lg px-4 py-3 text-sm resize-none focus:outline-none focus:border-[var(--accent)] transition-colors"
            rows={2}
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || !isConnected}
            className="px-6 py-3 bg-[var(--accent)] hover:bg-[var(--accent-hover)] disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors self-end"
          >
            Send
          </button>
        </div>
      </div>
      </div>
    </div>
  );
}
