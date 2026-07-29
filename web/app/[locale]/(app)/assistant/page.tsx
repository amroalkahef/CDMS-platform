"use client";

import { Bot, Send, Sparkles } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { api, ChatEvent } from "@/lib/api";
import { ApiError, apiErrorMessage } from "@/lib/errors";

interface ChatMessage {
  role: "user" | "assistant" | "error";
  content: string;
}

export default function AssistantPage() {
  const t = useTranslations("assistant");
  const tc = useTranslations("common");
  const locale = useLocale();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const threadRef = useRef<HTMLDivElement | null>(null);

  const suggestions = [t("suggestion1"), t("suggestion2"), t("suggestion3"), t("suggestion4")];

  function scrollToBottom() {
    setTimeout(() => threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" }), 50);
  }

  async function send(text: string) {
    const question = text.trim();
    if (!question || loading) return;

    const history = [...messages, { role: "user" as const, content: question }];
    setMessages([...history, { role: "assistant", content: "" }]);
    setInput("");
    setLoading(true);
    setSearching(false);
    scrollToBottom();

    let assistantContent = "";
    const appendToAssistant = (chunk: string) => {
      assistantContent += chunk;
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = { role: "assistant", content: assistantContent };
        return next;
      });
      scrollToBottom();
    };

    try {
      await api.chatStream(
        history.map((m) => ({ role: m.role, content: m.content })),
        (event: ChatEvent) => {
          if (event.type === "tool_call") {
            setSearching(true);
          } else if (event.type === "token" && event.content) {
            setSearching(false);
            appendToAssistant(event.content);
          } else if (event.type === "error") {
            setSearching(false);
            setMessages((prev) => {
              const next = [...prev];
              if (next[next.length - 1]?.role === "assistant" && !next[next.length - 1].content) {
                next.pop();
              }
              next.push({ role: "error", content: apiErrorMessage(new ApiError(event.error_code ?? "requestFailed"), tc) });
              return next;
            });
          }
        },
        locale
      );
    } catch (e) {
      setMessages((prev) => {
        const next = [...prev];
        if (next[next.length - 1]?.role === "assistant" && !next[next.length - 1].content) {
          next.pop();
        }
        next.push({ role: "error", content: apiErrorMessage(e, tc) });
        return next;
      });
    } finally {
      setLoading(false);
      setSearching(false);
      scrollToBottom();
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(input);
    }
  }

  return (
    <div className="chat-shell">
      <div className="eyebrow">
        <Sparkles className="sparkle" />
        {t("title")}
      </div>
      <p className="page-subtitle">{t("subtitle")}</p>

      {messages.length === 0 ? (
        <div className="chat-empty">
          <div className="chat-empty-icon">
            <Bot size={30} />
          </div>
          <h2>{t("greeting")}</h2>
          <p className="muted" style={{ maxWidth: 520 }}>
            {t("greetingSubtitle")}
          </p>
          <div className="suggestion-grid">
            {suggestions.map((s) => (
              <button key={s} type="button" className="suggestion-card" onClick={() => send(s)}>
                {s}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <>
          <div className="chat-thread-header">
            <button type="button" className="btn-secondary" onClick={() => setMessages([])} disabled={loading}>
              {t("newChatButton")}
            </button>
          </div>
          <div className="chat-thread" ref={threadRef}>
            {messages.map((m, i) => (
              <div key={i} className={`chat-message ${m.role}`}>
                {m.content || (loading && i === messages.length - 1 ? "…" : "")}
              </div>
            ))}
            {searching && <div className="chat-tool-indicator">{t("searchingIndicator")}</div>}
          </div>
        </>
      )}

      <div className="chat-input-row">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={t("inputPlaceholder")}
        />
        <button className="btn-primary chat-send-btn" disabled={loading || !input.trim()} onClick={() => send(input)}>
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}
