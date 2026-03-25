"use client";

import { useState, useEffect, useRef } from "react";
import ChatWindow from "./components/ChatWindow";
import PaperUpload from "./components/PaperUpload";
import DataUpload from "./components/DataUpload";
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
  // Track how many messages the server has sent — used to detect reconnect catch-up
  const serverMsgCount = useRef(0);

  // Persist session ID in sessionStorage so navigating between tabs keeps the session
  useEffect(() => {
    const stored = sessionStorage.getItem("bioChat_sessionId");
    if (stored) setSessionId(stored);
  }, []);

  // Create or restore session and connect WebSocket with auto-reconnect
  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let disposed = false;

    function getWsBase() {
      if (BACKEND_URL.startsWith("http")) {
        return BACKEND_URL.replace(/^http/, "ws").replace(/\/api\/?$/, "");
      }
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      return `${proto}//${window.location.host}`;
    }

    function connectWs(sid: string) {
      if (disposed) return;
      const ws = new WebSocket(`${getWsBase()}/ws/${sid}`);

      ws.onopen = () => {
        setIsConnected(true);
        // On reconnect, server replays all messages from the start.
        // Reset local messages so we rebuild from the server's authoritative list.
        serverMsgCount.current = 0;
        setMessages([]);
      };

      ws.onclose = () => {
        setIsConnected(false);
        if (!disposed) {
          reconnectTimer = setTimeout(() => connectWs(sid), 2000);
        }
      };

      ws.onerror = () => {
        setIsConnected(false);
        ws.close();
      };

      ws.onmessage = (event) => {
        const msg: Message = JSON.parse(event.data);
        serverMsgCount.current++;
        setMessages((prev) => [...prev, msg]);
        if (msg.state) setAgentState(msg.state);
      };

      wsRef.current = ws;
    }

    async function init() {
      try {
        // Try to restore existing session from the backend
        const stored = sessionStorage.getItem("bioChat_sessionId");
        if (stored) {
          const checkRes = await fetch(`${BACKEND_URL}/api/sessions/${stored}`);
          if (checkRes.ok) {
            // Session still exists on the backend — reconnect
            setSessionId(stored);
            connectWs(stored);
            return;
          }
        }

        // No valid session — create a new one
        const res = await fetch(`${BACKEND_URL}/api/sessions`, { method: "POST" });
        const data = await res.json();
        const sid = data.session_id;
        setSessionId(sid);
        sessionStorage.setItem("bioChat_sessionId", sid);
        connectWs(sid);
      } catch (err) {
        console.error("Failed to initialize session:", err);
      }
    }

    init();

    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, []);

  const startNewSession = async () => {
    try {
      wsRef.current?.close();
      const res = await fetch(`${BACKEND_URL}/api/sessions`, { method: "POST" });
      const data = await res.json();
      sessionStorage.setItem("bioChat_sessionId", data.session_id);
      // Full reload to cleanly reconnect
      window.location.reload();
    } catch (err) {
      console.error("Failed to create new session:", err);
    }
  };

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
          <button
            onClick={startNewSession}
            className="text-xs px-2 py-1 rounded border border-[var(--border)] hover:bg-[var(--bg-tertiary)] text-[var(--text-secondary)] transition-colors"
            title="Start a new session"
          >
            New Session
          </button>
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
        <div className="flex items-start gap-4">
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
          <DataUpload backendUrl={BACKEND_URL} />
        </div>

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
