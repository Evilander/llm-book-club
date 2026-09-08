"use client";

import { useCallback, useEffect, useState } from "react";
import { BookOpen, Loader2, LogIn, LogOut } from "lucide-react";
import { toast } from "sonner";
import type { AuthStatusPayload, ProviderStatus } from "@/types/api";
import { API_BASE } from "@/lib/utils";

async function readAuthStatus(): Promise<AuthStatusPayload> {
  const response = await fetch(`${API_BASE}/v1/auth/status`, {
    credentials: "include",
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Failed to load auth status" }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }
  return response.json();
}

function statusBadge(provider: ProviderStatus) {
  const label = provider.oauth_supported
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

export function ProviderConnections() {
  const [status, setStatus] = useState<AuthStatusPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyProvider, setBusyProvider] = useState<string | null>(null);

  const refreshStatus = useCallback(async () => {
    setLoading(true);
    try {
      setStatus(await readAuthStatus());
      setLoadError(null);
    } catch (error) {
      if (!(error instanceof TypeError)) {
        console.error("Failed to load auth status:", error);
      }
      setStatus(null);
      setLoadError(statusErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
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

  return <section className="provider-settings" aria-labelledby="connections-title">
    <div className="settings-intro"><h2 id="connections-title">Your reading partner</h2><p>Connect a model once, then settle into your book.</p></div>
    {loading ? <p className="connection-loading" role="status"><Loader2 size={16} className="animate-spin" /> Checking connections…</p> : loadError ? <div className="companion-error" role="alert"><p>{loadError}</p><button onClick={() => void refreshStatus()}>Try again</button></div> : <>
      <div className="connection-list">{status?.providers.slice().sort((a, b) => ["openai", "anthropic", "google"].indexOf(a.provider) - ["openai", "anthropic", "google"].indexOf(b.provider)).map((provider) => <article className="connection-row" key={provider.provider}>
        <div><h3>{provider.provider === "openai" ? "OpenAI" : provider.provider === "anthropic" ? "Claude" : "Google Gemini"}</h3>
          <p>{provider.provider === "openai" ? "Uses your OpenAI API account. ChatGPT subscription sign-in is not connected in this version." : provider.provider === "anthropic" ? "Uses your Anthropic API account. Claude subscription sign-in is not connected in this version." : provider.configured_auth_mode === "oauth" ? "Connect your Google account to read with Gemini." : "Gemini is set up to use an API key."}</p>
          {provider.account_email ? <p className="connection-email">{provider.account_email}</p> : null}
          {provider.provider === "google" && provider.oauth_ready ? <div className="connection-actions"><button className="reading-button secondary" disabled={!!busyProvider} onClick={() => handleConnect(provider)}>{provider.connected ? "Reconnect Google" : "Connect Google"}<LogIn size={14} /></button>{provider.connected ? <button className="text-link" disabled={!!busyProvider} onClick={() => void handleDisconnectGoogle()}>Disconnect</button> : null}</div> : null}
        </div>{statusBadge(provider)}
      </article>)}</div>
      {status?.authenticated && status.user ? <div className="settings-account"><p>Signed in as {status.user.display_name || status.user.email}</p><button className="text-link" disabled={!!busyProvider} onClick={() => void handleLogout()}>Sign out <LogOut size={14} /></button></div> : null}
    </>}
    <div className="settings-memory"><BookOpen size={22} strokeWidth={1.3} /><div><h3>A memory for each book</h3><p>Your conversations and margin questions are saved in this library. Your partner recalls relevant earlier thoughts as you read, so you can return to an idea in another chapter—even when you change models.</p></div></div>
  </section>;
}
