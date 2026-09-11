"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Copy, Loader2 } from "lucide-react";
import { API_BASE } from "@/lib/utils";
import type { ProviderStatus } from "@/types/api";

interface Login {
  login_id: string;
  state: "pending" | "completed" | "failed" | "expired" | "cancelled";
  user_code: string | null;
  verification_url: string | null;
  expires_in: number;
}

export async function connectionRequest<T>(path: string, body: object = {}, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE}/v1/${path}`, {
    method: "POST",
    credentials: "include",
    cache: "no-store",
    headers: { "Content-Type": "application/json", "X-ReadAgain-Settings": "1" },
    body: JSON.stringify(body),
    signal,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "The connection could not be updated. Please try again.");
  return payload as T;
}

function errorMessage(error: unknown) {
  return error instanceof TypeError ? "The reading service is unavailable. Please try again." : error instanceof Error ? error.message : "Sign-in could not finish. Please try again.";
}

export function ChatGPTConnection({ provider, onChange, onBusyChange, disabled = false }: { provider: ProviderStatus; onChange: () => Promise<void>; onBusyChange: (busy: boolean) => void; disabled?: boolean }) {
  const [login, setLogin] = useState<Login | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const operation = useRef<AbortController | null>(null);
  const loginId = login?.state === "pending" ? login.login_id : null;

  useEffect(() => () => operation.current?.abort(), []);
  useEffect(() => {
    onBusyChange(busy || !!loginId);
    return () => onBusyChange(false);
  }, [busy, loginId, onBusyChange]);

  useEffect(() => {
    if (!loginId) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await connectionRequest<Login>("auth/chatgpt/login/status", { login_id: loginId }, controller.signal);
        if (controller.signal.aborted) return;
        if (next.state === "completed") {
          setBusy(true);
          await connectionRequest("providers/active", { provider: "chatgpt" }, controller.signal);
          if (!controller.signal.aborted) {
            setLogin(null);
            await onChange();
          }
        } else if (next.state !== "pending") {
          setLogin(null);
          setError(next.state === "expired" ? "That sign-in code expired. Start again for a new code." : "Sign-in did not finish. You can try again.");
        } else {
          setLogin(next);
          timer = setTimeout(poll, 2500);
        }
      } catch (failure) {
        if (!controller.signal.aborted) {
          setError(errorMessage(failure));
          setLogin(null);
        }
      } finally {
        if (!controller.signal.aborted) setBusy(false);
      }
    }
    timer = setTimeout(poll, 1000);
    return () => { controller.abort(); clearTimeout(timer); };
  }, [loginId, onChange]);

  async function start() {
    operation.current?.abort();
    const controller = new AbortController();
    operation.current = controller;
    setBusy(true);
    setError(null);
    setCopied(false);
    try {
      if (provider.connected) {
        await connectionRequest("providers/active", { provider: "chatgpt" }, controller.signal);
        await onChange();
      } else {
        const next = await connectionRequest<Login>("auth/chatgpt/login", {}, controller.signal);
        if (next.state === "completed") {
          await connectionRequest("providers/active", { provider: "chatgpt" }, controller.signal);
          await onChange();
        } else if (next.state === "pending") {
          setLogin(next);
        } else {
          setError("Sign-in did not finish. Please try again.");
        }
      }
    } catch (failure) {
      if (!controller.signal.aborted) setError(errorMessage(failure));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  async function cancel() {
    const id = login?.login_id;
    setLogin(null); // Immediately stop polling and any automatic activation.
    setBusy(true);
    try {
      if (id) await connectionRequest("auth/chatgpt/login/cancel", { login_id: id });
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }

  async function disconnect() {
    setBusy(true);
    setError(null);
    try {
      await connectionRequest("auth/chatgpt/disconnect");
      await onChange();
    } catch (failure) { setError(errorMessage(failure)); }
    finally { setBusy(false); }
  }

  return <>
    {error ? <p className="connection-error" role="alert">{error}</p> : null}
    {login?.state === "pending" ? <div className="chatgpt-sign-in" aria-label="ChatGPT sign-in">
      <p>Enter this code on OpenAI’s sign-in page to connect this library.</p>
      <div className="device-code"><code>{login.user_code}</code><button type="button" className="text-link" aria-label="Copy sign-in code" onClick={() => {
        if (!login.user_code) return;
        if (!navigator.clipboard) { setError("Select and copy the code above."); return; }
        void navigator.clipboard.writeText(login.user_code).then(() => setCopied(true)).catch(() => setError("Select and copy the code above."));
      }}><Copy size={15} />{copied ? "Copied" : "Copy"}</button></div>
      <div className="connection-actions"><a className="reading-button secondary" href={login.verification_url || "https://auth.openai.com/codex/device"} target="_blank" rel="noopener noreferrer">Continue at OpenAI <ArrowUpRight size={14} /></a><button className="text-link" type="button" disabled={busy} onClick={() => void cancel()}>Cancel</button></div>
      <p className="connection-loading" role="status"><Loader2 size={14} className="animate-spin" /> Waiting for you to finish sign-in. This code expires in about {Math.max(1, Math.ceil(login.expires_in / 60))} minutes.</p>
      <p>If OpenAI asks, enable device-code sign-in in your ChatGPT security settings.</p>
    </div> : <div className="connection-actions">
      {!provider.active || !provider.connected ? <button className="reading-button secondary" type="button" disabled={disabled || busy || !provider.oauth_ready} onClick={() => void start()}>{busy ? <Loader2 size={14} className="animate-spin" /> : null}{provider.connected ? "Read with ChatGPT" : "Connect & read with ChatGPT"}</button> : null}
      {provider.connected ? <button className="text-link" type="button" disabled={disabled || busy} onClick={() => void disconnect()}>Disconnect</button> : null}
    </div>}
  </>;
}
