"use client";

import { motion } from "framer-motion";
import { AlertCircle, Loader2, ShieldCheck } from "lucide-react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { api } from "@/lib/api";

export default function OAuthCallbackPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const { loginWithToken } = useAuth();
  const [error, setError] = useState("");

  const provider = String(params?.provider || "");
  const code = searchParams.get("code") || "";
  const state = searchParams.get("state") || "";

  useEffect(() => {
    const finish = async () => {
      if (!provider || !code) {
        setError("The identity provider did not return a valid authorization code.");
        return;
      }

      const savedState = sessionStorage.getItem(`oauth_state_${provider}`);
      if (savedState && savedState !== state) {
        setError("OAuth state validation failed. Please start sign-in again.");
        return;
      }

      try {
        const token = await api.exchangeOAuthCode(provider, code, state);
        sessionStorage.removeItem(`oauth_state_${provider}`);
        await loginWithToken(token.access_token);
        router.replace("/dashboard/chat");
      } catch (err: any) {
        setError(err.message || "Unable to complete single sign-on.");
      }
    };
    finish();
  }, [code, loginWithToken, provider, router, state]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="surface w-full max-w-md p-8 text-center">
        <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          {error ? <AlertCircle className="h-6 w-6" /> : <ShieldCheck className="h-6 w-6" />}
        </div>
        {error ? (
          <>
            <h1 className="text-xl font-semibold">Authentication failed</h1>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">{error}</p>
            <button className="btn-primary mt-6 w-full" onClick={() => router.replace("/login")}>Return to login</button>
          </>
        ) : (
          <>
            <h1 className="text-xl font-semibold">Completing secure sign-in</h1>
            <p className="mt-3 text-sm text-muted-foreground">Exchanging your {provider} authorization code for an Insurance AI session.</p>
            <Loader2 className="mx-auto mt-6 h-6 w-6 animate-spin text-primary" />
          </>
        )}
      </motion.div>
    </main>
  );
}
