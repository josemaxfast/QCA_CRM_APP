import { authHeaders } from "./auth";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function detail(body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d))
      return d.map((x) => `${(x.loc ?? []).slice(1).join(".")}: ${x.msg}`).join("; ");
  }
  return "Request failed";
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(await authHeaders()) };
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  let r: Response;
  try {
    r = await fetch(BASE + path, {
      method: opts.method ?? "GET",
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Couldn't reach the server. It may be waking up; wait 20 seconds and try again.");
  }
  if (r.status === 204) return undefined as T;
  const text = await r.text();
  let body: unknown;
  try {
    body = text ? JSON.parse(text) : undefined;
  } catch {
    body = undefined;
  }
  if (!r.ok) {
    const d = detail(body);
    if (r.status === 401) throw new ApiError(401, `Not signed in (${d}). Sign out and sign in again.`);
    throw new ApiError(r.status, d === "Request failed" ? `Server error ${r.status}. Try again; if it repeats, tell support.` : d);
  }
  return body as T;
}

export type Me = {
  user_id: string;
  email: string;
  display_name: string;
  level: "sales" | "manager" | "admin";
  level_name: string;
  entity_id: string | null;
  entities: { entity_id: string; code: string; name: string }[];
};

export type User = {
  user_id: string; display_name: string; email: string;
  level: "sales" | "manager" | "admin"; entity_id: string | null; entity_code: string | null;
};

export type Account = {
  account_id: string; entity_id: string; entity_code: string; customer_number: string;
  kind: "customer" | "prospect" | "vendor"; intercompany: boolean; name: string; dba: string;
  website: string; industry: string; status: "prospect" | "active" | "inactive";
  payment_terms: string; pricing_tier: string; tax_exempt: boolean;
  owner_user_id: string; owner_name: string; source: string; fulcrum_id: string;
  existed_at_golive: boolean; confidential: boolean; updated_at: string;
};

export type Contact = {
  contact_id: string; account_id: string; first_name: string; last_name: string; title: string;
  email: string; phone: string; role: "buyer" | "engineer" | "ap" | "other";
  preferred_method: "email" | "phone" | "text" | "in_person"; do_not_contact: boolean;
};

/** Can this person change a record of company `entityId` owned by `ownerId`? (The server decides; this only hides buttons.) */
export function canEdit(me: Me, entityId: string, ownerId: string): boolean {
  if (me.level === "admin") return true;
  if (me.entity_id !== entityId) return false;
  return me.level === "manager" || ownerId === me.user_id;
}
