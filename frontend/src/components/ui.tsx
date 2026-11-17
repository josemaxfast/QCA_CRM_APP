import { ReactNode, useState } from "react";

export type Flag = "bad" | "warn";

/** A labelled input. `flag` tints it red (blocks sending) or gold (check it), matching the messages. */
export function Field({ label, children, wide, flag, hint }: {
  label: string; children: ReactNode; wide?: boolean; flag?: Flag; hint?: string;
}) {
  return (
    <label className={`field${wide ? " wide" : ""}${flag ? ` flag-${flag}` : ""}`} title={hint}>
      <span>{label}</span>
      {children}
    </label>
  );
}

/** Number input that stores null when empty (so the engine uses its default). */
export function Num({
  value, onChange, step = "any", placeholder, disabled,
}: {
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  step?: string;
  placeholder?: string;
  disabled?: boolean;
}) {
  return (
    <input type="number" step={step} value={value ?? ""} placeholder={placeholder} disabled={disabled}
           onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))} />
  );
}

export function Text({ value, onChange, placeholder, disabled }: {
  value: string | null | undefined; onChange: (v: string) => void; placeholder?: string; disabled?: boolean;
}) {
  return <input value={value ?? ""} placeholder={placeholder} disabled={disabled}
                onChange={(e) => onChange(e.target.value)} />;
}

export function Select({ value, options, onChange, disabled, blank }: {
  value: string | null | undefined;
  options: (string | [string, string])[];
  onChange: (v: string) => void;
  disabled?: boolean;
  blank?: string;
}) {
  return (
    <select value={value ?? ""} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
      {blank !== undefined && <option value="">{blank}</option>}
      {/* A saved value that isn't in the list is still shown as-is, never as the first option. */}
      {value && !options.some((o) => (Array.isArray(o) ? o[0] : o) === value) && <option value={value}>{value}</option>}
      {options.map((o) => {
        const [v, l] = Array.isArray(o) ? o : [o, o];
        return <option key={v} value={v}>{l}</option>;
      })}
    </select>
  );
}

export function Messages({ warnings = [], issues = [] }: { warnings?: string[]; issues?: string[] }) {
  const [open, setOpen] = useState(false);
  if (!warnings.length && !issues.length) return null;
  return (
    <div className="messages">
      {issues.map((i) => <div key={i} className="issue">⛔ {i}</div>)}
      {warnings.length > 0 && (
        <div className="warnings">
          <button className="link warn-link" onClick={() => setOpen(!open)}>
            {open ? "▾" : "▸"} {warnings.length} assumption{warnings.length > 1 ? "s" : ""} / note{warnings.length > 1 ? "s" : ""}
          </button>
          {open && <ul>{warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
        </div>
      )}
    </div>
  );
}

export function ErrorBanner({ error, onClose }: { error: string; onClose?: () => void }) {
  if (!error) return null;
  return (
    <div className="banner error">
      {error} {onClose && <button className="link" onClick={onClose}>dismiss</button>}
    </div>
  );
}

export function StatusChip({ status }: { status: string }) {
  return <span className={`chip s-${status.replace(" ", "")}`}>{status}</span>;
}
