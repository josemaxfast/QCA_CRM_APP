import { Component, useEffect, useState, type ReactNode } from "react";
import { api, type Me } from "./api";
import { devUser, entraEnabled, initAuth, setDevUser, signIn, signOut } from "./auth";
import Accounts from "./pages/Accounts";
import AccountPage from "./pages/AccountPage";

// Dark is the default (same as QCA Quote); light is remembered per browser.
function applyTheme(t: string) { document.documentElement.dataset.theme = t; }
try { applyTheme(localStorage.getItem("qca-theme") ?? "dark"); } catch { applyTheme("dark"); }
function toggleTheme() {
  const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  applyTheme(next);
  try { localStorage.setItem("qca-theme", next); } catch { /* private window */ }
}

const APP_VERSION = (import.meta.env.VITE_APP_VERSION as string | undefined) || "dev";

class ErrorBoundary extends Component<{ children: ReactNode }, { error: string }> {
  state = { error: "" };
  static getDerivedStateFromError(e: Error) {
    return { error: e?.message ?? String(e) };
  }
  render() {
    if (this.state.error)
      return <div className="banner error">This page hit an error: {this.state.error}. Reload the page; if it
        happens again, send a screenshot of this message.</div>;
    return this.props.children;
  }
}

const route = () => {
  const h = window.location.hash.slice(1);
  return h.startsWith("/") && h.length > 1 ? h : "/my-day";
};

function useHash(): [string, (h: string) => void, () => void] {
  const [hash, setHash] = useState(route);
  useEffect(() => {
    const on = () => setHash(route());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const go = (h: string) => {
    if (window.location.hash.slice(1) === h) setHash(h);
    else window.location.hash = h;
  };
  return [hash, go, () => setHash(route())];
}

function SignIn({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState("");
  return (
    <div className="signin">
      <h1>QCA CRM</h1>
      {entraEnabled ? (
        <button className="primary" onClick={() => signIn()}>Sign in with Microsoft</button>
      ) : (
        <form onSubmit={(e) => { e.preventDefault(); setDevUser(email.trim()); onDone(); }}>
          <p className="muted">Development sign-in: enter an email an Admin has added.</p>
          <input autoFocus type="email" placeholder="you@company.com" value={email}
                 onChange={(e) => setEmail(e.target.value)} />
          <button className="primary" type="submit">Sign in</button>
        </form>
      )}
    </div>
  );
}

function ComingSoon({ title, step }: { title: string; step: string }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      <p className="muted">This screen arrives in {step} of the Phase 1 plan.</p>
    </div>
  );
}

export default function App() {
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState("");
  const [hash, go, rereadHash] = useHash();

  useEffect(() => {
    initAuth()
      .then((ok) => setSignedIn(ok))
      .catch((e) => setError(`Microsoft sign-in failed: ${e?.message ?? e}`))
      .finally(() => { rereadHash(); setReady(true); });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!signedIn) return;
    api<Me>("/api/me")
      .then((m) => { setMe(m); setError(""); })
      .catch((e) => { setError(e.message); if (!entraEnabled) setDevUser(null); });
  }, [signedIn]);

  if (!ready) return null;
  if (!signedIn || (!me && error))
    return (
      <>
        {error && <div className="banner error">{error}</div>}
        <SignIn onDone={() => { setError(""); setSignedIn(Boolean(devUser())); }} />
      </>
    );
  if (!me) return <div className="page">Loading…</div>;

  const [section, arg] = hash.split("/").filter(Boolean);
  const runsSettings = me.level !== "sales";
  const company = me.entity_id ? me.entities.find((e) => e.entity_id === me.entity_id)?.name : "All companies";

  const nav: [string, string][] = [
    ["my-day", "My day"],
    ["pipeline", "Pipeline"],
    ["accounts", "Accounts"],
    ["leaderboard", "Leaderboard"],
    ...(runsSettings ? [["settings", "Settings"] as [string, string]] : []),
  ];

  return (
    <div>
      <header className="top">
        <div className="brand" title={`Version ${APP_VERSION}`}>QCA CRM</div>
        <nav>
          {nav.map(([k, label]) => (
            <a key={k} href={`#/${k}`} className={section === k ? "active" : ""}>{label}</a>
          ))}
        </nav>
        <div className="spacer" />
        <span className="user">{company}</span>
        <button className="link" title="Switch light / dark" onClick={toggleTheme}>Theme</button>
        <span className="user" title={me.email}>{me.display_name} · {me.level_name}</span>
        <button className="link" onClick={() => signOut().then(() => { setMe(null); setSignedIn(false); })}>
          Sign out
        </button>
      </header>
      <main className="page">
        <ErrorBoundary key={hash}>
          {section === "my-day" && <ComingSoon title="My day" step="step 11" />}
          {section === "pipeline" && <ComingSoon title="Pipeline" step="step 11" />}
          {section === "accounts" && !arg && <Accounts me={me} go={go} />}
          {section === "accounts" && arg && <AccountPage me={me} id={arg} go={go} />}
          {section === "leaderboard" && <ComingSoon title="Leaderboard" step="step 11" />}
          {section === "settings" && runsSettings && <ComingSoon title="Settings" step="step 5" />}
        </ErrorBoundary>
      </main>
      <footer className="muted version">Version {APP_VERSION}</footer>
    </div>
  );
}
