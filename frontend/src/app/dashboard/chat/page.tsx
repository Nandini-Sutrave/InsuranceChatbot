"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { BookOpen, Clipboard, FileText, Loader2, PanelRightOpen, RefreshCcw, Send, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type ChatMessage, type ChatSession, type KnowledgeBase, type Source } from "@/lib/api";

export default function ChatPage() {
  const queryClient = useQueryClient();
  const [conversationId, setConversationId] = useState<string | undefined>();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [kb, setKb] = useState("");
  const [activeSource, setActiveSource] = useState<Source | null>(null);
  const [lastLatency, setLastLatency] = useState<number | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const sessions = useQuery<ChatSession[]>({ queryKey: ["chat-sessions"], queryFn: api.listChatSessions });
  const kbs = useQuery<KnowledgeBase[]>({ queryKey: ["knowledge-bases"], queryFn: api.listKnowledgeBases });

  const send = useMutation({
    mutationFn: async (content: string) => {
      const start = performance.now();
      const response = await api.sendMessage({ content, conversation_id: conversationId, product_id: kb || undefined });
      setLastLatency(Math.round(performance.now() - start));
      return response;
    },
    onSuccess: async (assistantMessage) => {
      setMessages((prev) => [...prev, assistantMessage]);
      if (!conversationId) {
        await queryClient.invalidateQueries({ queryKey: ["chat-sessions"] });
        const refreshed = await api.listChatSessions();
        setConversationId(refreshed[0]?.id);
      }
    },
    onError: (err: any) => {
      setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: "assistant", content: err.message || "Unable to reach the insurance RAG service.", created_at: new Date().toISOString() }]);
    },
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, send.isPending]);

  const loadSession = async (sessionId: string) => {
    setConversationId(sessionId);
    const detail = await api.getChatSession(sessionId);
    setMessages(detail.messages || []);
  };

  const submit = (event?: FormEvent) => {
    event?.preventDefault();
    const text = input.trim();
    if (!text || send.isPending) return;
    const userMessage: ChatMessage = { id: crypto.randomUUID(), role: "user", content: text, created_at: new Date().toISOString() };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    send.mutate(text);
  };

  const regenerate = () => {
    const lastUser = [...messages].reverse().find((message) => message.role === "user");
    if (lastUser && !send.isPending) send.mutate(lastUser.content);
  };

  const suggestions = useMemo(() => [
    "What is the maternity waiting period in Health Protector Policy?",
    "Compare PED waiting periods across retrieved health policies.",
    "What documents are needed for cashless hospitalization claims?",
    "Explain suicide exclusion terms in HDFC Life policy.",
  ], []);

  return (
    <div className="grid h-full grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)]">
      <aside className="hidden border-r border-border bg-card lg:flex lg:flex-col h-full overflow-hidden">
        <div className="border-b border-border p-4">
          <button className="btn-primary w-full" onClick={() => { setConversationId(undefined); setMessages([]); }}>New Chat</button>
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Chat History</p>
          {sessions.isLoading ? <SkeletonRows /> : sessions.data?.map((session) => (
            <button key={session.id} onClick={() => loadSession(session.id)} className={`mb-1 w-full rounded-lg px-3 py-2 text-left text-sm transition ${conversationId === session.id ? "bg-muted font-semibold" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}>
              <span className="line-clamp-2">{session.title}</span>
            </button>
          ))}
        </div>
      </aside>

      <section className="flex min-w-0 flex-col h-full overflow-hidden">
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border bg-card px-4 py-3">
          <div>
            <h1 className="text-sm font-semibold">Policy Intelligence Chat</h1>
            <p className="text-xs text-muted-foreground">Structured answers with citations and page references.</p>
          </div>
          <div className="flex items-center gap-2">
            <select value={kb} onChange={(e) => setKb(e.target.value)} className="control max-w-[260px]">
              <option value="">All policy documents</option>
              {kbs.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
            {lastLatency !== null && <span className="badge">{lastLatency} ms</span>}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto px-4 py-6 lg:px-8">
          {messages.length === 0 ? (
            <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center">
              <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-lg border border-border bg-card text-primary"><BookOpen className="h-6 w-6" /></div>
              <h2 className="text-3xl font-semibold tracking-tight">Ask across your insurance policy vault.</h2>
              <p className="mt-3 max-w-2xl text-muted-foreground">The assistant retrieves policy chunks, separates primary matches from cross-policy references, and returns cited Markdown for client-ready review.</p>
              <div className="mt-6 grid gap-3 sm:grid-cols-2">
                {suggestions.map((item) => <button key={item} className="surface p-4 text-left text-sm text-muted-foreground transition hover:border-primary hover:text-foreground" onClick={() => setInput(item)}>{item}</button>)}
              </div>
            </div>
          ) : (
            <div className="mx-auto max-w-4xl space-y-6">
              {messages.map((message) => <MessageBubble key={message.id} message={message} onSource={setActiveSource} />)}
              {send.isPending && <div className="surface inline-flex items-center gap-3 px-4 py-3 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin text-primary" />Retrieving policy clauses and drafting answer...</div>}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <form onSubmit={submit} className="shrink-0 border-t border-border bg-card p-4">
          <div className="mx-auto flex max-w-4xl items-end gap-3">
            <button type="button" className="btn-secondary hidden h-11 w-11 p-0 sm:inline-flex" title="Attach PDF"><FileText className="h-4 w-4" /></button>
            <textarea value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }} rows={1} placeholder="Ask about waiting periods, exclusions, claim documents, policy limits..." className="control max-h-40 min-h-11 flex-1 resize-none" />
            <button className="btn-primary h-11 w-11 p-0" disabled={!input.trim() || send.isPending} type="submit" title="Send"><Send className="h-4 w-4" /></button>
            <button type="button" className="btn-secondary hidden h-11 w-11 p-0 sm:inline-flex" onClick={regenerate} title="Regenerate"><RefreshCcw className="h-4 w-4" /></button>
          </div>
        </form>
      </section>

      <SourceDrawer source={activeSource} onClose={() => setActiveSource(null)} />
    </div>
  );
}

function MessageBubble({ message, onSource }: { message: ChatMessage; onSource: (source: Source) => void }) {
  const isUser = message.role === "user";
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[92%] rounded-lg border p-4 shadow-sm ${isUser ? "border-primary bg-primary text-primary-foreground" : "border-border bg-card"}`}>
        {isUser ? <p className="whitespace-pre-wrap text-sm leading-6">{message.content}</p> : <div className="prose-policy text-sm leading-6"><ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown></div>}
        {!isUser && message.sources?.length ? (
          <div className="mt-4 border-t border-border pt-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Sources Used</p>
            <div className="flex flex-wrap gap-2">
              {message.sources.map((source, index) => <button key={`${source.filename}-${index}`} onClick={() => onSource(source)} className="badge hover:border-primary hover:text-foreground"><PanelRightOpen className="h-3 w-3" />{source.filename} · Page {source.page_number || "U"}</button>)}
            </div>
            <div className="mt-3 flex gap-2 text-muted-foreground">
              <button className="rounded-md p-1 hover:bg-muted" title="Copy response" onClick={() => navigator.clipboard.writeText(message.content)}><Clipboard className="h-4 w-4" /></button>
              <button className="rounded-md p-1 hover:bg-muted" title="Helpful"><ThumbsUp className="h-4 w-4" /></button>
              <button className="rounded-md p-1 hover:bg-muted" title="Not helpful"><ThumbsDown className="h-4 w-4" /></button>
              <span className="ml-auto text-xs">{new Date(message.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
            </div>
          </div>
        ) : null}
      </div>
    </motion.div>
  );
}

function SourceDrawer({ source, onClose }: { source: Source | null; onClose: () => void }) {
  return (
    <AnimatePresence>
      {source && <>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />
        <motion.aside initial={{ x: 420 }} animate={{ x: 0 }} exit={{ x: 420 }} className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-border bg-card shadow-xl">
          <div className="flex items-center justify-between border-b border-border p-4"><h2 className="font-semibold">Source citation</h2><button className="rounded-md p-2 hover:bg-muted" onClick={onClose}><X className="h-4 w-4" /></button></div>
          <div className="space-y-4 overflow-y-auto p-4 text-sm">
            <div className="surface p-4"><p className="text-xs uppercase text-muted-foreground">Document</p><p className="mt-1 font-semibold">{source.filename}</p><p className="mt-1 text-muted-foreground">Page {source.page_number || "Unknown"}</p></div>
            <div><p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Extracted chunk</p><pre className="max-h-[60vh] whitespace-pre-wrap rounded-lg border border-border bg-muted p-4 text-xs leading-5 text-foreground">{source.chunk_text || "No chunk text returned by API."}</pre></div>
          </div>
        </motion.aside>
      </>}
    </AnimatePresence>
  );
}

function SkeletonRows() {
  return <div className="space-y-2">{Array.from({ length: 6 }).map((_, index) => <div key={index} className="h-10 animate-pulse rounded-lg bg-muted" />)}</div>;
}
