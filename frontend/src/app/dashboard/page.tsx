"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight, FileText, MessageSquare, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { api } from "@/lib/api";

export default function DashboardPage() {
  const sessions = useQuery({ queryKey: ["chat-sessions"], queryFn: api.listChatSessions });
  const documents = useQuery({ queryKey: ["documents"], queryFn: api.listDocuments });
  const kbs = useQuery({ queryKey: ["knowledge-bases"], queryFn: api.listKnowledgeBases });

  return (
    <div className="h-full overflow-y-auto p-6 lg:p-8">
      <div className="mx-auto max-w-6xl space-y-8">
        <section className="surface p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <div className="mb-3 inline-flex items-center gap-2 rounded-lg border border-border bg-muted px-3 py-1.5 text-xs font-semibold text-muted-foreground">
                <Sparkles className="h-4 w-4 text-primary" /> Production RAG Workspace
              </div>
              <h1 className="text-3xl font-semibold tracking-tight">Insurance AI command center</h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Review knowledge base health, continue recent policy investigations, and launch cited clause analysis for client-ready answers.</p>
            </div>
            <Link href="/dashboard/chat" className="btn-primary">Open assistant <ArrowRight className="h-4 w-4" /></Link>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-3">
          <Metric icon={MessageSquare} label="Chat threads" value={sessions.data?.length || 0} />
          <Metric icon={FileText} label="Uploaded documents" value={documents.data?.length || 0} />
          <Metric icon={ShieldCheck} label="Knowledge bases" value={kbs.data?.length || 0} />
        </section>

        <section className="grid gap-6 lg:grid-cols-[1fr_0.9fr]">
          <div className="surface p-5">
            <h2 className="mb-4 font-semibold">Recent conversations</h2>
            <div className="space-y-2">
              {sessions.data?.slice(0, 8).map((session) => (
                <Link key={session.id} href="/dashboard/chat" className="flex items-center justify-between rounded-lg border border-border p-3 text-sm transition hover:border-primary hover:bg-muted/50">
                  <span className="line-clamp-1 font-medium">{session.title}</span>
                  <span className="text-xs text-muted-foreground">{new Date(session.created_at).toLocaleDateString()}</span>
                </Link>
              ))}
              {!sessions.isLoading && !sessions.data?.length && <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">No chats yet. Start with a policy question.</p>}
            </div>
          </div>

          <div className="surface p-5">
            <h2 className="mb-4 font-semibold">Document status</h2>
            <div className="space-y-3">
              {documents.data?.slice(0, 7).map((doc) => (
                <div key={doc.id} className="flex items-center justify-between gap-3 rounded-lg bg-muted/50 p-3 text-sm">
                  <span className="line-clamp-1 font-medium">{doc.filename}</span>
                  <span className="rounded-md border border-border bg-card px-2 py-1 text-xs text-muted-foreground">{doc.status}</span>
                </div>
              ))}
              {!documents.isLoading && !documents.data?.length && <p className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">No uploaded documents found.</p>}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function Metric({ icon: Icon, label, value }: { icon: any; label: string; value: number }) {
  return <div className="surface p-5"><div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-primary/10 text-primary"><Icon className="h-5 w-5" /></div><p className="text-3xl font-semibold">{value}</p><p className="mt-1 text-sm text-muted-foreground">{label}</p></div>;
}
