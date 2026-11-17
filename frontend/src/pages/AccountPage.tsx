import { useEffect, useState } from "react";
import { api, canEdit, type Account, type Contact, type Me } from "../api";
import { ErrorBanner, Field, Select, Text } from "../components/ui";

const EDITABLE: (keyof Account)[] = ["name", "dba", "website", "industry", "payment_terms", "pricing_tier", "source", "fulcrum_id"];
const LABELS: Partial<Record<keyof Account, string>> = {
  name: "Company name", dba: "DBA", website: "Website", industry: "Industry",
  payment_terms: "Payment terms", pricing_tier: "Pricing tier", source: "Source", fulcrum_id: "Fulcrum customer ID",
};

export default function AccountPage({ me, id, go }: { me: Me; id: string; go: (h: string) => void }) {
  const [a, setA] = useState<Account | null>(null);
  const [draft, setDraft] = useState<Partial<Account>>({});
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  useEffect(() => {
    api<Account>(`/api/accounts/${id}`).then((x) => { setA(x); setDraft({}); }).catch((e) => setError(e.message));
    api<Contact[]>(`/api/accounts/${id}/contacts`).then(setContacts).catch(() => {});
  }, [id]);

  if (error && !a) return <ErrorBanner error={error} />;
  if (!a) return <div>Loading…</div>;
  const editable = canEdit(me, a.entity_id, a.owner_user_id);
  const val = <K extends keyof Account>(k: K) => (k in draft ? draft[k] : a[k]) as Account[K];
  const dirty = Object.keys(draft).length > 0;

  const save = () => {
    api<Account>(`/api/accounts/${id}`, { method: "PATCH", body: draft })
      .then((x) => { setA(x); setDraft({}); setSaved("Saved"); setTimeout(() => setSaved(""), 2000); })
      .catch((e) => setError(e.message));
  };

  return (
    <div>
      <div className="toolbar">
        <button className="link" onClick={() => go("/accounts")}>← Accounts</button>
        <h2>{a.customer_number} · {a.name}</h2>
        {a.intercompany && <span className="chip">Intercompany</span>}
        {a.confidential && <span className="chip">Confidential</span>}
        <div className="spacer" />
        <span className="muted">Salesperson: {a.owner_name}</span>
      </div>
      {!editable && (
        <div className="banner info">You can view this account. Only {a.owner_name}, the Sales Manager or an Admin can change it.</div>
      )}
      <ErrorBanner error={error} onClose={() => setError("")} />
      <div className="card">
        <div className="fields">
          {EDITABLE.map((k) => (
            <Field key={k} label={LABELS[k] ?? k} flag={k === "name" && !String(val(k)).trim() ? "bad" : undefined}>
              <Text value={String(val(k) ?? "")} disabled={!editable} onChange={(v) => setDraft({ ...draft, [k]: v })} />
            </Field>
          ))}
          <Field label="Kind">
            <Select value={val("kind")} disabled={!editable} onChange={(v) => setDraft({ ...draft, kind: v as Account["kind"] })}
                    options={[["customer", "Customer"], ["prospect", "Prospect"], ["vendor", "Vendor"]]} />
          </Field>
          <Field label="Status">
            <Select value={val("status")} disabled={!editable} onChange={(v) => setDraft({ ...draft, status: v as Account["status"] })}
                    options={[["prospect", "Prospect"], ["active", "Active"], ["inactive", "Inactive"]]} />
          </Field>
        </div>
        {editable && (
          <p>
            <button className="primary" disabled={!dirty || !String(val("name")).trim()} onClick={save}>Save changes</button>{" "}
            {saved && <span className="muted">{saved}</span>}
          </p>
        )}
      </div>
      <div className="card">
        <h3>Contacts</h3>
        <table className="grid">
          <thead><tr><th>Name</th><th>Title</th><th>Role</th><th>Email</th><th>Phone</th><th></th></tr></thead>
          <tbody>
            {contacts.map((c) => (
              <tr key={c.contact_id}>
                <td>{c.first_name} {c.last_name}</td><td>{c.title}</td><td>{c.role}</td>
                <td>{c.email}</td><td>{c.phone}</td>
                <td>{c.do_not_contact && <span className="chip">Do not contact</span>}</td>
              </tr>
            ))}
            {!contacts.length && <tr><td colSpan={6} className="muted">No contacts yet.</td></tr>}
          </tbody>
        </table>
        {editable && <NewContact accountId={id} onSaved={(c) => setContacts([...contacts, c])} />}
      </div>
    </div>
  );
}

function NewContact({ accountId, onSaved }: { accountId: string; onSaved: (c: Contact) => void }) {
  const blank = { first_name: "", last_name: "", title: "", email: "", phone: "", role: "buyer" };
  const [c, setC] = useState(blank);
  const [error, setError] = useState("");
  const set = (k: keyof typeof blank) => (v: string) => setC({ ...c, [k]: v });
  const ok = c.first_name.trim() || c.last_name.trim();
  return (
    <div>
      <h4>Add a contact</h4>
      <ErrorBanner error={error} onClose={() => setError("")} />
      <div className="fields">
        <Field label="First name" flag={ok ? undefined : "bad"}><Text value={c.first_name} onChange={set("first_name")} /></Field>
        <Field label="Last name" flag={ok ? undefined : "bad"}><Text value={c.last_name} onChange={set("last_name")} /></Field>
        <Field label="Title"><Text value={c.title} onChange={set("title")} /></Field>
        <Field label="Role">
          <Select value={c.role} onChange={set("role")} options={[["buyer", "Buyer"], ["engineer", "Engineer"], ["ap", "AP"], ["other", "Other"]]} />
        </Field>
        <Field label="Email"><Text value={c.email} onChange={set("email")} /></Field>
        <Field label="Phone"><Text value={c.phone} onChange={set("phone")} /></Field>
      </div>
      <button className="primary" disabled={!ok} onClick={() =>
        api<Contact>(`/api/accounts/${accountId}/contacts`, { method: "POST", body: c })
          .then((x) => { onSaved(x); setC(blank); }).catch((e) => setError(e.message))}>Add contact</button>
    </div>
  );
}
