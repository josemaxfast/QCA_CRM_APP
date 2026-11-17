import { useEffect, useState } from "react";
import { api, type Account, type Me, type User } from "../api";
import { ErrorBanner, Field, Select, Text } from "../components/ui";

export default function Accounts({ me, go }: { me: Me; go: (h: string) => void }) {
  const [list, setList] = useState<Account[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [q, setQ] = useState("");
  const [owner, setOwner] = useState("");
  const [error, setError] = useState("");
  const [adding, setAdding] = useState(false);

  const load = () => {
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (owner) p.set("owner", owner);
    api<Account[]>(`/api/accounts?${p}`).then(setList).catch((e) => setError(e.message));
  };
  useEffect(load, [q, owner]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { api<User[]>("/api/users").then(setUsers).catch(() => {}); }, []);

  const owners = users.filter((u) => u.level !== "admin");

  return (
    <div>
      <div className="toolbar">
        <h2>Accounts</h2>
        <input placeholder="Search name or customer number" value={q} onChange={(e) => setQ(e.target.value)} />
        <Select value={owner} blank="All salespeople" onChange={setOwner}
                options={owners.map((u) => [u.user_id, `${u.display_name}${u.entity_code && me.level === "admin" ? ` (${u.entity_code})` : ""}`])} />
        <div className="spacer" />
        <button className="primary" onClick={() => setAdding(true)}>New account</button>
      </div>
      <ErrorBanner error={error} onClose={() => setError("")} />
      {adding && <NewAccount me={me} owners={owners} onCancel={() => setAdding(false)}
                             onSaved={(a) => go(`/accounts/${a.account_id}`)} />}
      <table className="grid clickable">
        <thead>
          <tr>
            <th>Number</th><th>Name</th>{me.level === "admin" && <th>Company</th>}
            <th>Kind</th><th>Status</th><th>Salesperson</th>
          </tr>
        </thead>
        <tbody>
          {list.map((a) => (
            <tr key={a.account_id} onClick={() => go(`/accounts/${a.account_id}`)}>
              <td>{a.customer_number}</td>
              <td>
                {a.name}
                {a.intercompany && <span className="chip"> Intercompany</span>}
                {a.confidential && <span className="chip"> Confidential</span>}
              </td>
              {me.level === "admin" && <td>{a.entity_code}</td>}
              <td style={{ textTransform: "capitalize" }}>{a.kind}</td>
              <td style={{ textTransform: "capitalize" }}>{a.status}</td>
              <td>{a.owner_name}</td>
            </tr>
          ))}
          {!list.length && <tr><td colSpan={6} className="muted">No accounts yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function NewAccount({ me, owners, onCancel, onSaved }: {
  me: Me; owners: User[]; onCancel: () => void; onSaved: (a: Account) => void;
}) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState("customer");
  const [entity, setEntity] = useState(me.level === "admin" ? "" : (me.entities[0]?.code ?? ""));
  const [owner, setOwner] = useState(me.level === "admin" ? "" : me.user_id);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const entityId = me.entities.find((e) => e.code === entity)?.entity_id;
  const ownerChoices = owners.filter((u) => u.entity_id === entityId);

  const save = () => {
    setBusy(true);
    api<Account>("/api/accounts", {
      method: "POST",
      body: { name, kind, entity_code: entity || undefined, owner_user_id: owner || undefined },
    }).then(onSaved).catch((e) => setError(e.message)).finally(() => setBusy(false));
  };

  return (
    <div className="card">
      <h3>New account</h3>
      <ErrorBanner error={error} onClose={() => setError("")} />
      <div className="fields">
        <Field label="Company name" flag={name.trim() ? undefined : "bad"} wide>
          <Text value={name} onChange={setName} />
        </Field>
        <Field label="Kind">
          <Select value={kind} onChange={setKind} options={[["customer", "Customer"], ["prospect", "Prospect"], ["vendor", "Vendor"]]} />
        </Field>
        {me.level === "admin" && (
          <Field label="Company" flag={entity ? undefined : "bad"}>
            <Select value={entity} blank="Pick…" onChange={(v) => { setEntity(v); setOwner(""); }}
                    options={me.entities.map((e) => [e.code, e.name])} />
          </Field>
        )}
        {me.level !== "sales" && (
          <Field label="Salesperson" flag={owner ? undefined : "bad"}>
            <Select value={owner} blank="Pick…" onChange={setOwner}
                    options={ownerChoices.map((u) => [u.user_id, u.display_name])} />
          </Field>
        )}
      </div>
      <p className="muted">The customer number is given automatically when you save.</p>
      <button className="primary" disabled={busy || !name.trim() || !owner || !entity} onClick={save}>Save</button>{" "}
      <button className="link" onClick={onCancel}>Cancel</button>
    </div>
  );
}
