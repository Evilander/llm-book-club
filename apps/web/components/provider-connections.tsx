"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { BookOpen, Loader2, LogIn, LogOut } from "lucide-react";
import { toast } from "sonner";
import type { AuthStatusPayload, ProviderStatus } from "@/types/api";
import { API_BASE } from "@/lib/utils";
import { ChatGPTConnection, connectionRequest } from "./chatgpt-connection";

async function readAuthStatus(signal: AbortSignal): Promise<AuthStatusPayload> {
  const response = await fetch(`${API_BASE}/v1/auth/status`, {
    credentials: "include",
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to load auth status" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function statusBadge(provider: ProviderStatus) {
  const label = provider.active ? provider.connected ? "Your reading partner" : "Selected · reconnect" : provider.configured_auth_mode === "local" ? provider.connected ? "Local model available" : "Local model unavailable" : provider.oauth_supported
    ? provider.connected ? "Connected" : provider.oauth_ready ? "Ready to connect" : "Setup needed"
    : provider.connected ? "API key configured" : "API key needed";
  return <span className={`connection-status ${provider.connected ? "is-connected" : ""}`}>{label}</span>;
}

function statusErrorMessage(error: unknown) {
  if (error instanceof TypeError) {
    return "The reading service is unavailable. Please try again in a moment.";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Connection status is unavailable.";
}

export function ProviderConnections({ onReady }: { onReady?: () => void } = {}) {
  const [status, setStatus] = useState<AuthStatusPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyProvider, setBusyProvider] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [readyError, setReadyError] = useState<string | null>(null);
  const [chatgptBusy, setChatgptBusy] = useState(false);

  const statusRequest = useRef<AbortController | null>(null);
  const readyRequest = useRef<AbortController | null>(null);
  const mounted = useRef(false);
  const refreshStatus = useCallback(async () => {
    if (!mounted.current) return;
    statusRequest.current?.abort();
    const controller = new AbortController();
    statusRequest.current = controller;
    setLoading(true);
    try {
      const next = await readAuthStatus(controller.signal);
      if (controller.signal.aborted) return;
      setStatus(next);
      setLoadError(null);
    } catch (error) {
      if (controller.signal.aborted) return;
      setStatus(null);
      setLoadError(statusErrorMessage(error));
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void refreshStatus();
    return () => { mounted.current = false; statusRequest.current?.abort(); readyRequest.current?.abort(); };
  }, [refreshStatus]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const auth = params.get("auth");
    const authError = params.get("auth_error");
    if (auth === "google_connected") {
      toast.success("Google connected. Gemini OAuth is ready.");
    } else if (authError) {
      toast.error(`Google sign-in failed: ${authError}`);
    } else {
      return;
    }

    params.delete("auth");
    params.delete("auth_error");
    const query = params.toString();
    const nextUrl = `${window.location.pathname}${query ? `?${query}` : ""}`;
    window.history.replaceState({}, "", nextUrl);
  }, []);

  async function handleLogout() {
    setBusyProvider("session");
    try {
      const response = await fetch(`${API_BASE}/v1/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      toast.success("Signed out");
      await refreshStatus();
    } catch (error) {
      console.error("Logout failed:", error);
      toast.error("Could not sign out");
    } finally {
      setBusyProvider(null);
    }
  }

  async function handleDisconnectGoogle() {
    setBusyProvider("google");
    try {
      const response = await fetch(`${API_BASE}/v1/auth/google/disconnect`, {
        method: "POST",
        credentials: "include",
      });
      if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Disconnect failed" }));
        throw new Error(error.detail || `HTTP ${response.status}`);
      }
      toast.success("Google connection removed");
      await refreshStatus();
    } catch (error) {
      console.error("Disconnect failed:", error);
      toast.error(error instanceof Error ? error.message : "Could not disconnect Google");
    } finally {
      setBusyProvider(null);
    }
  }

  function handleConnect(provider: ProviderStatus) {
    if (!provider.connect_path) {
      toast.error("This provider cannot start an OAuth flow from the app yet.");
      return;
    }
    window.location.assign(`${API_BASE}${provider.connect_path}`);
  }

  async function selectProvider(provider: ProviderStatus) {
    setBusyProvider(provider.provider);
    try {
      await connectionRequest("providers/active", { provider: provider.provider === "google" ? "gemini" : provider.provider });
      await refreshStatus();
    } catch (error) { toast.error(statusErrorMessage(error)); }
    finally { setBusyProvider(null); }
  }

  async function returnToReading() {
    const controller = new AbortController();
    readyRequest.current?.abort();
    readyRequest.current = controller;
    setChecking(true);
    setReadyError(null);
    try {
      const connection = await connectionRequest<{ connected: boolean; message: string }>("providers/reading-status", {}, controller.signal);
      if (controller.signal.aborted) return;
      if (connection.connected) onReady?.();
      else { setReadyError(connection.message); await refreshStatus(); }
    } catch (error) { if (!controller.signal.aborted) setReadyError(statusErrorMessage(error)); }
    finally { if (!controller.signal.aborted) setChecking(false); }
  }

  const providers = status?.providers.slice().sort((a, b) => ["chatgpt", "anthropic", "openai", "google", "grok", "local"].indexOf(a.provider) - ["chatgpt", "anthropic", "openai", "google", "grok", "local"].indexOf(b.provider)) || [];
  const renderProvider = (provider: ProviderStatus) => <article className="connection-row" key={provider.provider}>
        <div><h3>{provider.provider === "anthropic" ? "Claude" : provider.label}</h3>
          <p>{provider.provider === "openai" ? "Uses your OpenAI API account, billed separately from ChatGPT." : provider.provider === "anthropic" ? "Uses your Anthropic API account. Claude subscription sign-in is not connected in this version." : provider.note}</p>
          {provider.account_email ? <p className="connection-email">{provider.account_email}</p> : null}
          {provider.provider === "chatgpt" ? <ChatGPTConnection provider={provider} onChange={refreshStatus} onBusyChange={setChatgptBusy} disabled={!!busyProvider} /> : null}
          {provider.provider === "google" && provider.oauth_ready && provider.configured_auth_mode === "oauth" && !onReady ? <div className="connection-actions"><button className="reading-button secondary" disabled={!!busyProvider || chatgptBusy} onClick={() => handleConnect(provider)}>{provider.connected ? "Reconnect Google" : "Connect Google"}<LogIn size={14} /></button>{provider.connected ? <button className="text-link" disabled={!!busyProvider || chatgptBusy} onClick={() => void handleDisconnectGoogle()}>Disconnect</button> : null}</div> : null}
          {provider.provider !== "chatgpt" && provider.connected && !provider.active ? <div className="connection-actions"><button className="reading-button secondary" disabled={!!busyProvider || chatgptBusy} onClick={() => void selectProvider(provider)}>Read with {provider.provider === "anthropic" ? "Claude" : provider.label}</button></div> : null}
        </div>{statusBadge(provider)}
      </article>;

  return <section className="provider-settings" aria-label={onReady ? "Reading connections" : undefined} aria-labelledby={onReady ? undefined : "connections-title"}>
    {!onReady ? <div className="settings-intro"><h2 id="connections-title">Your reading partner</h2><p>Connect a model once, then settle into your book.</p></div> : null}
    {loading ? <p className="connection-loading" role="status"><Loader2 size={16} className="animate-spin" /> Checking connections…</p> : loadError ? <div className="companion-error" role="alert"><p>{loadError}</p><button onClick={() => void refreshStatus()}>Try again</button></div> : <>
      <div className="connection-list">{providers.filter(provider => !onReady || provider.provider === "chatgpt" || provider.active).map(renderProvider)}
        {onReady && providers.some(provider => provider.provider !== "chatgpt" && !provider.active) ? <details className="connection-alternatives"><summary>Other reading partners</summary>{providers.filter(provider => provider.provider !== "chatgpt" && !provider.active).map(renderProvider)}</details> : null}
      </div>
      {status?.authenticated && status.user ? <div className="settings-account"><p>Signed in as {status.user.display_name || status.user.email}</p><button className="text-link" disabled={!!busyProvider || chatgptBusy} onClick={() => void handleLogout()}>Sign out <LogOut size={14} /></button></div> : null}
    </>}
    {onReady ? <div className="connection-return">
      {readyError ? <p className="connection-error" role="alert">{readyError}</p> : null}
      <button className="reading-button" type="button" disabled={loading || checking || !!busyProvider || chatgptBusy || !status?.providers.some(provider => provider.active && provider.connected)} onClick={() => void returnToReading()}>{checking ? "Checking connection…" : "Continue reading"}</button>
      <button className="text-link" type="button" disabled={loading || checking || !!busyProvider || chatgptBusy} onClick={() => void refreshStatus()}>Check connections again</button>
      <a className="text-link" href="/settings" target="_blank" rel="noopener noreferrer">More connection settings ↗</a>
    </div> : null}
    <div className="settings-memory"><BookOpen size={22} strokeWidth={1.3} /><div><h3>A memory for each book</h3><p>Your conversations and margin questions are saved in this library. Your partner recalls relevant earlier thoughts as you read, so you can return to an idea in another chapter—even when you change models. Book memory stays with this library; connecting ChatGPT does not import your other chats.</p></div></div>
  </section>;
}
