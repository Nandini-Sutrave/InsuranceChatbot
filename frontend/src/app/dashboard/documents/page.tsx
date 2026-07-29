"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, FileText, FolderPlus, Loader2, Search, Trash2, UploadCloud } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { api, type DocumentItem, type KnowledgeBase } from "@/lib/api";
import { AuthGuard } from "@/components/auth-guard";

export default function DocumentsPage() {
  const queryClient = useQueryClient();
  const [selectedKb, setSelectedKb] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [search, setSearch] = useState("");
  const [kbName, setKbName] = useState("");
  const [kbDescription, setKbDescription] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  const kbs = useQuery<KnowledgeBase[]>({ queryKey: ["knowledge-bases"], queryFn: api.listKnowledgeBases });
  const docs = useQuery<DocumentItem[]>({ queryKey: ["documents"], queryFn: api.listDocuments });

  const createKb = useMutation({
    mutationFn: api.createKnowledgeBase,
    onSuccess: (kb) => {
      setKbName("");
      setKbDescription("");
      setSelectedKb(kb.id);
      setNotice("Knowledge base created.");
      queryClient.invalidateQueries({ queryKey: ["knowledge-bases"] });
    },
  });

  const upload = useMutation({
    mutationFn: async () => {
      if (!file || !selectedKb) throw new Error("Select a PDF and knowledge base first.");
      return api.uploadDocument(selectedKb, file, setProgress);
    },
    onSuccess: () => {
      setFile(null);
      setProgress(0);
      setNotice("Document uploaded. Ingestion has been queued by the backend.");
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  const remove = useMutation({
    mutationFn: api.deleteDocument,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents"] }),
  });

  const filteredDocs = useMemo(() => {
    const q = search.toLowerCase();
    return (docs.data || []).filter((doc) => doc.filename.toLowerCase().includes(q) || doc.status.toLowerCase().includes(q));
  }, [docs.data, search]);

  const submitKb = (event: FormEvent) => {
    event.preventDefault();
    if (kbName.trim()) createKb.mutate({ name: kbName.trim(), description: kbDescription.trim() || undefined });
  };

  return (
    <AuthGuard adminOnly>
      <div className="h-full overflow-y-auto p-6 lg:p-8">
        <div className="mx-auto max-w-6xl space-y-6">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Document Vault</h1>
            <p className="mt-2 text-sm text-muted-foreground">Upload insurance PDFs, monitor ingestion status, and manage product-specific knowledge bases.</p>
          </div>

          {(notice || upload.error || createKb.error) && (
            <div className={`flex gap-3 rounded-lg border p-3 text-sm ${notice ? "border-green-200 bg-green-50 text-green-700 dark:border-green-900 dark:bg-green-950/30 dark:text-green-300" : "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300"}`}>
              {notice ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
              <span>{notice || (upload.error as Error)?.message || (createKb.error as Error)?.message}</span>
            </div>
          )}

          <section className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
            <form onSubmit={(e) => { e.preventDefault(); upload.mutate(); }} className="surface p-5">
              <div className="mb-4 flex items-center gap-2"><UploadCloud className="h-5 w-5 text-primary" /><h2 className="font-semibold">Upload policy document</h2></div>
              <div className="grid gap-4">
                <select className="control" value={selectedKb} onChange={(e) => setSelectedKb(e.target.value)}>
                  <option value="">Select knowledge base</option>
                  {kbs.data?.map((kb) => <option key={kb.id} value={kb.id}>{kb.name}</option>)}
                </select>
                <label className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-border bg-muted/40 p-8 text-center transition hover:border-primary">
                  <FileText className="mb-3 h-9 w-9 text-muted-foreground" />
                  <span className="text-sm font-semibold">{file ? file.name : "Drop or choose a PDF"}</span>
                  <span className="mt-1 text-xs text-muted-foreground">PDF, DOCX, TXT supported by backend</span>
                  <input type="file" className="hidden" accept=".pdf,.docx,.txt" onChange={(e) => setFile(e.target.files?.[0] || null)} />
                </label>
                {upload.isPending && <div className="h-2 overflow-hidden rounded-full bg-muted"><div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} /></div>}
                <button className="btn-primary" disabled={upload.isPending || !file || !selectedKb}>{upload.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <UploadCloud className="h-4 w-4" />} Upload & ingest</button>
              </div>
            </form>

            <form onSubmit={submitKb} className="surface p-5">
              <div className="mb-4 flex items-center gap-2"><FolderPlus className="h-5 w-5 text-primary" /><h2 className="font-semibold">Create knowledge base</h2></div>
              <div className="space-y-4">
                <input className="control w-full" value={kbName} onChange={(e) => setKbName(e.target.value)} placeholder="Health Protector Policy" />
                <textarea className="control min-h-28 w-full resize-none" value={kbDescription} onChange={(e) => setKbDescription(e.target.value)} placeholder="Scope, carrier, or policy family notes" />
                <button className="btn-secondary w-full" disabled={createKb.isPending}>{createKb.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <FolderPlus className="h-4 w-4" />} Create segment</button>
              </div>
            </form>
          </section>

          <section className="surface p-5">
            <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <h2 className="font-semibold">Document registry</h2>
              <div className="relative max-w-sm flex-1 sm:flex-none"><Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" /><input className="control w-full pl-9" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search documents" /></div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border text-xs uppercase text-muted-foreground"><tr><th className="py-3">Document</th><th>Status</th><th>Size</th><th>Uploaded</th><th className="text-right">Action</th></tr></thead>
                <tbody className="divide-y divide-border">
                  {filteredDocs.map((doc) => <tr key={doc.id}><td className="max-w-md py-3 font-medium"><span className="line-clamp-1">{doc.filename}</span></td><td><span className="badge">{doc.status}</span></td><td className="text-muted-foreground">{formatBytes(doc.file_size)}</td><td className="text-muted-foreground">{new Date(doc.created_at).toLocaleDateString()}</td><td className="text-right"><button className="rounded-md p-2 text-muted-foreground hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/30" onClick={() => remove.mutate(doc.id)}><Trash2 className="h-4 w-4" /></button></td></tr>)}
                  {!docs.isLoading && filteredDocs.length === 0 && <tr><td colSpan={5} className="py-10 text-center text-muted-foreground">No documents match this view.</td></tr>}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      </div>
    </AuthGuard>
  );
}

function formatBytes(bytes: number) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, index)).toFixed(index ? 1 : 0)} ${units[index]}`;
}
