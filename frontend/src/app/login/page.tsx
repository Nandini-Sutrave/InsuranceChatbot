"use client";

import { motion } from "framer-motion";
import { AlertCircle, ArrowRight, Building2, LockKeyhole, Mail, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";

export default function LoginPage() {
  const { login, startOAuth, isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectPath = searchParams.get("redirect") || "/dashboard/chat";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const sessionExpired = searchParams.get("session_expired") === "true";

  useEffect(() => {
    if (isAuthenticated && !isLoading) router.push(redirectPath);
  }, [isAuthenticated, isLoading, redirectPath, router]);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      await login(email, password);
      router.push(redirectPath);
    } catch (err: any) {
      setError(err.message || "Unable to sign in with those credentials.");
    } finally {
      setSubmitting(false);
    }
  };

  const oauth = async (provider: "google" | "microsoft") => {
    setError("");
    try {
      await startOAuth(provider);
    } catch (err: any) {
      setError(err.message || `Unable to start ${provider} sign-in.`);
    }
  };

  return (
    <main className="grid min-h-screen bg-background lg:grid-cols-[1.05fr_0.95fr]">
      <section className="hidden border-r border-border bg-muted/35 px-12 py-10 lg:flex lg:flex-col lg:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-bold">Insurance AI</p>
            <p className="text-xs text-muted-foreground">Compliance Intelligence Workspace</p>
          </div>
        </div>

        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="max-w-xl">
          <div className="mb-6 inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-xs font-semibold text-muted-foreground">
            <Building2 className="h-4 w-4 text-primary" />
            Enterprise policy reasoning for agents
          </div>
          <h1 className="text-5xl font-semibold leading-tight tracking-tight text-foreground">
            Search policy wordings, compare clauses, and cite every answer.
          </h1>
          <p className="mt-5 max-w-lg text-base leading-7 text-muted-foreground">
            Built for insurance operations teams that need reliable answers from approved policy PDFs, not generic chatbot guesses.
          </p>
        </motion.div>

        <div className="grid grid-cols-3 gap-3 text-sm">
          {["Hybrid retrieval", "Inline citations", "Secure JWT sessions"].map((item) => (
            <div key={item} className="surface p-4 text-muted-foreground">
              <p className="font-semibold text-foreground">{item}</p>
              <p className="mt-1 text-xs">Production-ready controls for client demos.</p>
            </div>
          ))}
        </div>
      </section>

      <section className="flex items-center justify-center px-5 py-10">
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <h1 className="text-2xl font-semibold">Insurance AI</h1>
          </div>

          <div className="surface p-6 sm:p-8">
            <div className="mb-6">
              <h2 className="text-2xl font-semibold tracking-tight">Sign in</h2>
              <p className="mt-2 text-sm text-muted-foreground">Use your workspace account or continue with Google SSO.</p>
            </div>

            {(sessionExpired || error) && (
              <div className="mb-5 flex gap-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                <span>{error || "Your session expired. Please sign in again."}</span>
              </div>
            )}

            <div className="grid gap-3">
              <button type="button" onClick={() => oauth("google")} className="btn-secondary w-full">
                <span className="flex h-5 w-5 items-center justify-center rounded-full border text-[11px] font-bold">G</span>
                Continue with Google
              </button>
              <button type="button" onClick={() => oauth("microsoft")} className="btn-secondary w-full">
                <span className="grid h-4 w-4 grid-cols-2 gap-0.5"><i className="bg-red-500" /><i className="bg-green-500" /><i className="bg-blue-500" /><i className="bg-amber-400" /></span>
                Continue with Microsoft
              </button>
            </div>

            <div className="my-6 flex items-center gap-3 text-xs text-muted-foreground">
              <span className="h-px flex-1 bg-border" />
              Email credentials
              <span className="h-px flex-1 bg-border" />
            </div>

            <form onSubmit={onSubmit} className="space-y-4">
              <label className="block text-sm font-medium">
                Email
                <span className="relative mt-1 block">
                  <Mail className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                  <input className="control w-full pl-9" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="agent@company.com" required />
                </span>
              </label>
              <label className="block text-sm font-medium">
                Password
                <span className="relative mt-1 block">
                  <LockKeyhole className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                  <input className="control w-full pl-9" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter password" required />
                </span>
              </label>

              <div className="flex items-center justify-between text-sm">
                <label className="flex items-center gap-2 text-muted-foreground">
                  <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} className="h-4 w-4 rounded border-border" />
                  Remember me
                </label>
                <button type="button" className="font-medium text-primary">Forgot password?</button>
              </div>

              <button className="btn-primary w-full" disabled={submitting} type="submit">
                {submitting ? "Signing in..." : "Sign in"}
                <ArrowRight className="h-4 w-4" />
              </button>
            </form>

            <p className="mt-6 text-center text-sm text-muted-foreground">
              New workspace? <Link href="/signup" className="font-semibold text-primary">Create an account</Link>
            </p>
          </div>
        </motion.div>
      </section>
    </main>
  );
}
