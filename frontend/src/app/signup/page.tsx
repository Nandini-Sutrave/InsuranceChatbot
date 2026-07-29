"use client";

import { AlertCircle, ArrowRight, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.register({ full_name: fullName, email, password });
      router.push("/login");
    } catch (err: any) {
      setError(err.message || "Unable to create account.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="surface w-full max-w-md p-8">
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground"><ShieldCheck className="h-5 w-5" /></div>
          <div><h1 className="text-xl font-semibold">Create Insurance AI account</h1><p className="text-sm text-muted-foreground">Register a secured workspace identity.</p></div>
        </div>
        {error && <div className="mb-4 flex gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"><AlertCircle className="h-4 w-4" />{error}</div>}
        <form onSubmit={submit} className="space-y-4">
          <input className="control w-full" value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Full name" required />
          <input className="control w-full" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="agent@company.com" required />
          <input className="control w-full" type="password" minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" required />
          <button className="btn-primary w-full" disabled={loading}>{loading ? "Creating..." : "Create account"}<ArrowRight className="h-4 w-4" /></button>
        </form>
        <p className="mt-6 text-center text-sm text-muted-foreground">Already registered? <Link href="/login" className="font-semibold text-primary">Sign in</Link></p>
      </div>
    </main>
  );
}
