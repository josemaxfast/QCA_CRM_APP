"""Tenancy, companies, users, accounts, contacts, customer numbers and the audit log.

How the separation works (plain words):
- Every request switches to the restricted role `crm_app`. It owns no tables, is not a
  superuser and cannot bypass row-level security.
- At the start of each transaction the API records who is asking:
    app.tenant_id  the customer group
    app.entity_id  the user's company (blank for top Admins)
    app.user_id    the user
    app.level      sales | manager | admin | system
  ("system" is only used by setup scripts and background jobs, never by a signed-in person.)
- Row-level security policies on every table compare each row with those values. If nothing
  has been recorded, every policy fails and the request sees nothing.

Revision ID: 0001
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = r"""
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'crm_app') THEN
    CREATE ROLE crm_app NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
  END IF;
END $$;

-- ---------------------------------------------------------------------------------------
-- Who is asking (recorded per transaction by the API)
-- ---------------------------------------------------------------------------------------
CREATE FUNCTION app_setting(name text) RETURNS text LANGUAGE sql STABLE AS $$
  SELECT nullif(current_setting(name, true), '')
$$;
CREATE FUNCTION app_tenant() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT app_setting('app.tenant_id')::uuid
$$;
CREATE FUNCTION app_entity() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT app_setting('app.entity_id')::uuid
$$;
CREATE FUNCTION app_user_id() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT app_setting('app.user_id')::uuid
$$;
CREATE FUNCTION app_level() RETURNS text LANGUAGE sql STABLE AS $$
  SELECT app_setting('app.level')
$$;
-- Top Admins (and setup/background jobs) see every company in their tenant.
CREATE FUNCTION app_is_admin() RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT coalesce(app_level() IN ('admin', 'system'), false)
$$;
-- May the current user see records of company e?
CREATE FUNCTION app_sees_entity(e uuid) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT coalesce(app_is_admin() OR (e = app_entity()), false)
$$;
-- Does the current user manage company e (Sales Manager of e, or Admin)?
CREATE FUNCTION app_manages_entity(e uuid) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT coalesce(app_is_admin() OR (app_level() = 'manager' AND e = app_entity()), false)
$$;
-- May the current user change a record of company e owned by `owner`?
CREATE FUNCTION app_can_edit(e uuid, owner uuid) RETURNS boolean LANGUAGE sql STABLE AS $$
  SELECT coalesce(
    app_manages_entity(e)
    OR (app_level() = 'sales' AND e = app_entity() AND owner = app_user_id()),
  false)
$$;

-- ---------------------------------------------------------------------------------------
-- Tenants, companies and users
-- ---------------------------------------------------------------------------------------
CREATE TABLE tenant (
  tenant_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name       text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE entity (
  entity_id  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL REFERENCES tenant,
  code       text NOT NULL CHECK (code ~ '^[A-Z0-9]{2,6}$'),
  name       text NOT NULL,
  address    text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, code),
  UNIQUE (tenant_id, entity_id)
);

CREATE TABLE app_user (
  user_id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    uuid NOT NULL REFERENCES tenant,
  entity_id    uuid,
  level        text NOT NULL CHECK (level IN ('sales', 'manager', 'admin')),
  email        text NOT NULL,
  display_name text NOT NULL,
  entra_oid    text UNIQUE,
  active       boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, entity_id) REFERENCES entity (tenant_id, entity_id),
  -- Top Admins belong to no single company; everyone else belongs to exactly one.
  CHECK ((level = 'admin') = (entity_id IS NULL)),
  UNIQUE (user_id, entity_id)
);
CREATE UNIQUE INDEX app_user_email ON app_user (lower(email));

-- ---------------------------------------------------------------------------------------
-- Customer numbers
-- ---------------------------------------------------------------------------------------
CREATE TABLE number_series (
  tenant_id  uuid NOT NULL,
  entity_id  uuid NOT NULL,
  kind       text NOT NULL CHECK (kind IN ('existing', 'new')),
  prefix     text NOT NULL,
  next_value integer NOT NULL CHECK (next_value > 0),
  max_value  integer,
  PRIMARY KEY (entity_id, kind),
  FOREIGN KEY (tenant_id, entity_id) REFERENCES entity (tenant_id, entity_id)
);

-- ---------------------------------------------------------------------------------------
-- Accounts and contacts
-- ---------------------------------------------------------------------------------------
CREATE TABLE account (
  account_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id         uuid NOT NULL,
  entity_id         uuid NOT NULL,
  customer_number   text NOT NULL,
  kind              text NOT NULL DEFAULT 'customer' CHECK (kind IN ('customer', 'prospect', 'vendor')),
  intercompany      boolean NOT NULL DEFAULT false,
  name              text NOT NULL CHECK (btrim(name) <> ''),
  dba               text NOT NULL DEFAULT '',
  website           text NOT NULL DEFAULT '',
  industry          text NOT NULL DEFAULT '',
  status            text NOT NULL DEFAULT 'prospect' CHECK (status IN ('prospect', 'active', 'inactive')),
  bill_to           jsonb NOT NULL DEFAULT '{}',
  ship_to           jsonb NOT NULL DEFAULT '{}',
  payment_terms     text NOT NULL DEFAULT '',
  pricing_tier      text NOT NULL DEFAULT '',
  tax_exempt        boolean NOT NULL DEFAULT false,
  owner_user_id     uuid NOT NULL,
  source            text NOT NULL DEFAULT '',
  parent_account_id uuid,
  fulcrum_id        text NOT NULL DEFAULT '',
  existed_at_golive boolean NOT NULL DEFAULT false,
  confidential      boolean NOT NULL DEFAULT false,
  last_activity_at  timestamptz,
  created_by        uuid,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, entity_id) REFERENCES entity (tenant_id, entity_id),
  -- The owner must be a user of the same company (so Admins, who have no company, can't own).
  FOREIGN KEY (owner_user_id, entity_id) REFERENCES app_user (user_id, entity_id),
  UNIQUE (account_id, entity_id),
  FOREIGN KEY (parent_account_id, entity_id) REFERENCES account (account_id, entity_id),
  UNIQUE (entity_id, customer_number)
);
CREATE INDEX account_owner ON account (owner_user_id);
CREATE INDEX account_name ON account (entity_id, lower(name));

CREATE TABLE contact (
  contact_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL,
  entity_id        uuid NOT NULL,
  account_id       uuid NOT NULL,
  first_name       text NOT NULL DEFAULT '',
  last_name        text NOT NULL DEFAULT '',
  title            text NOT NULL DEFAULT '',
  email            text NOT NULL DEFAULT '',
  phone            text NOT NULL DEFAULT '',
  role             text NOT NULL DEFAULT 'other' CHECK (role IN ('buyer', 'engineer', 'ap', 'other')),
  preferred_method text NOT NULL DEFAULT 'email' CHECK (preferred_method IN ('email', 'phone', 'text', 'in_person')),
  do_not_contact   boolean NOT NULL DEFAULT false,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tenant_id, entity_id) REFERENCES entity (tenant_id, entity_id),
  -- A contact always carries its account's company.
  FOREIGN KEY (account_id, entity_id) REFERENCES account (account_id, entity_id),
  CHECK (btrim(first_name || last_name) <> '')
);
CREATE INDEX contact_account ON contact (account_id);

-- ---------------------------------------------------------------------------------------
-- Audit log (append-only)
-- ---------------------------------------------------------------------------------------
CREATE TABLE audit_log (
  id           bigserial PRIMARY KEY,
  tenant_id    uuid NOT NULL,
  entity_id    uuid,
  user_id      uuid,
  action       text NOT NULL,
  target_table text NOT NULL,
  target_id    text NOT NULL,
  before       jsonb,
  after        jsonb,
  at           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_target ON audit_log (target_table, target_id);

-- Every change to a business table is written to the audit log automatically.
CREATE FUNCTION audit_row() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  old_j jsonb := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END;
  new_j jsonb := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END;
  r jsonb := coalesce(new_j, old_j);
BEGIN
  IF TG_OP = 'UPDATE' AND old_j - 'updated_at' = new_j - 'updated_at' THEN
    RETURN NEW;  -- nothing really changed
  END IF;
  INSERT INTO audit_log (tenant_id, entity_id, user_id, action, target_table, target_id, before, after)
  VALUES ((r->>'tenant_id')::uuid, (r->>'entity_id')::uuid, app_user_id(), lower(TG_OP),
          TG_TABLE_NAME, r->>TG_ARGV[0], old_j, new_j);
  RETURN coalesce(NEW, OLD);
END $$;

CREATE FUNCTION touch_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END $$;

-- Only a Sales Manager or Admin may change a number format; anyone allowed to create an
-- account may advance the counter, but never move it backwards.
CREATE FUNCTION guard_number_series() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.prefix, NEW.max_value, NEW.kind, NEW.entity_id, NEW.tenant_id)
     IS DISTINCT FROM (OLD.prefix, OLD.max_value, OLD.kind, OLD.entity_id, OLD.tenant_id)
     AND NOT app_manages_entity(OLD.entity_id) THEN
    RAISE EXCEPTION 'Only a Sales Manager or Admin can change the customer-number format'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NEW.next_value < OLD.next_value AND NOT app_manages_entity(OLD.entity_id) THEN
    RAISE EXCEPTION 'Customer-number counters never go backwards'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER number_series_guard BEFORE UPDATE ON number_series
  FOR EACH ROW EXECUTE FUNCTION guard_number_series();
CREATE TRIGGER account_touch BEFORE UPDATE ON account
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER contact_touch BEFORE UPDATE ON contact
  FOR EACH ROW EXECUTE FUNCTION touch_updated_at();
CREATE TRIGGER account_audit AFTER INSERT OR UPDATE OR DELETE ON account
  FOR EACH ROW EXECUTE FUNCTION audit_row('account_id');
CREATE TRIGGER contact_audit AFTER INSERT OR UPDATE OR DELETE ON contact
  FOR EACH ROW EXECUTE FUNCTION audit_row('contact_id');
CREATE TRIGGER app_user_audit AFTER INSERT OR UPDATE OR DELETE ON app_user
  FOR EACH ROW EXECUTE FUNCTION audit_row('user_id');
CREATE TRIGGER number_series_audit AFTER INSERT OR UPDATE ON number_series
  FOR EACH ROW EXECUTE FUNCTION audit_row('kind');
"""

POLICIES = r"""
-- Tenants: you see only your own. Only setup scripts create them.
CREATE POLICY tenant_read ON tenant FOR SELECT USING (tenant_id = app_tenant());
CREATE POLICY tenant_create ON tenant FOR INSERT WITH CHECK (app_level() = 'system');
CREATE POLICY tenant_update ON tenant FOR UPDATE
  USING (tenant_id = app_tenant() AND app_is_admin())
  WITH CHECK (tenant_id = app_tenant() AND app_is_admin());

-- Companies: you see your own company (Admins see all in the tenant).
CREATE POLICY entity_read ON entity FOR SELECT
  USING (tenant_id = app_tenant() AND app_sees_entity(entity_id));
CREATE POLICY entity_create ON entity FOR INSERT
  WITH CHECK (tenant_id = app_tenant() AND app_is_admin());
CREATE POLICY entity_update ON entity FOR UPDATE
  USING (tenant_id = app_tenant() AND app_is_admin())
  WITH CHECK (tenant_id = app_tenant() AND app_is_admin());

-- Users: you see the people of your own company and the top Admins.
-- Sales Managers add and change users of their own company (never Admins).
CREATE POLICY user_read ON app_user FOR SELECT
  USING (tenant_id = app_tenant() AND (entity_id IS NULL OR app_sees_entity(entity_id)));
-- Sign-in looks a person up by email before their tenant is known. That one lookup runs
-- with app.auth_lookup = on and no other setting, and can only read.
CREATE POLICY user_sign_in ON app_user FOR SELECT
  USING (app_setting('app.auth_lookup') = 'on' AND app_tenant() IS NULL);
CREATE POLICY user_create ON app_user FOR INSERT
  WITH CHECK (tenant_id = app_tenant()
              AND (app_is_admin() OR (app_level() = 'manager' AND entity_id = app_entity()
                                      AND level <> 'admin')));
CREATE POLICY user_update ON app_user FOR UPDATE
  USING (tenant_id = app_tenant()
         AND (app_is_admin() OR (app_level() = 'manager' AND entity_id = app_entity()
                                 AND level <> 'admin')))
  WITH CHECK (tenant_id = app_tenant()
              AND (app_is_admin() OR (app_level() = 'manager' AND entity_id = app_entity()
                                      AND level <> 'admin')));

-- Customer-number counters: readable and advanceable by your company; format changes are
-- limited by the trigger above; new series only by managers.
CREATE POLICY series_read ON number_series FOR SELECT
  USING (tenant_id = app_tenant() AND app_sees_entity(entity_id));
CREATE POLICY series_create ON number_series FOR INSERT
  WITH CHECK (tenant_id = app_tenant() AND app_manages_entity(entity_id));
CREATE POLICY series_update ON number_series FOR UPDATE
  USING (tenant_id = app_tenant() AND app_sees_entity(entity_id))
  WITH CHECK (tenant_id = app_tenant() AND app_sees_entity(entity_id));

-- Accounts:
--   see:    your company's accounts (all salespeople, read-only on others').
--           Confidential ones only for that company's Sales Manager and Admins.
--   add:    a salesperson can only add accounts they own.
--   change: owner, or the company's Sales Manager, or an Admin. The owner can't hand the
--           account to someone else; only a Sales Manager or Admin can.
CREATE POLICY account_read ON account FOR SELECT
  USING (tenant_id = app_tenant() AND app_sees_entity(entity_id)
         AND (NOT confidential OR app_manages_entity(entity_id)));
CREATE POLICY account_create ON account FOR INSERT
  WITH CHECK (tenant_id = app_tenant() AND app_can_edit(entity_id, owner_user_id)
              AND (NOT confidential OR app_manages_entity(entity_id)));
CREATE POLICY account_update ON account FOR UPDATE
  USING (tenant_id = app_tenant() AND app_can_edit(entity_id, owner_user_id)
         AND (NOT confidential OR app_manages_entity(entity_id)))
  WITH CHECK (tenant_id = app_tenant() AND app_can_edit(entity_id, owner_user_id)
              AND (NOT confidential OR app_manages_entity(entity_id)));

-- Contacts follow their account: visible when the account is visible, changeable when the
-- account is changeable.
CREATE POLICY contact_read ON contact FOR SELECT
  USING (tenant_id = app_tenant() AND app_sees_entity(entity_id)
         AND EXISTS (SELECT 1 FROM account a WHERE a.account_id = contact.account_id));
CREATE POLICY contact_create ON contact FOR INSERT
  WITH CHECK (tenant_id = app_tenant()
              AND EXISTS (SELECT 1 FROM account a WHERE a.account_id = contact.account_id
                          AND app_can_edit(a.entity_id, a.owner_user_id)));
CREATE POLICY contact_update ON contact FOR UPDATE
  USING (tenant_id = app_tenant()
         AND EXISTS (SELECT 1 FROM account a WHERE a.account_id = contact.account_id
                     AND app_can_edit(a.entity_id, a.owner_user_id)))
  WITH CHECK (tenant_id = app_tenant()
              AND EXISTS (SELECT 1 FROM account a WHERE a.account_id = contact.account_id
                          AND app_can_edit(a.entity_id, a.owner_user_id)));

-- Audit log: Sales Managers read their company's history, Admins read everything in the
-- tenant. Anyone can add (the triggers do), nobody can change or delete.
CREATE POLICY audit_read ON audit_log FOR SELECT
  USING (tenant_id = app_tenant()
         AND (CASE WHEN entity_id IS NULL THEN app_is_admin() ELSE app_manages_entity(entity_id) END));
CREATE POLICY audit_write ON audit_log FOR INSERT
  WITH CHECK (tenant_id = app_tenant() AND (entity_id IS NULL OR app_sees_entity(entity_id)));
"""

TABLES = ["tenant", "entity", "app_user", "number_series", "account", "contact", "audit_log"]


def upgrade() -> None:
    op.execute(SCHEMA)
    for t in TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
    op.execute(POLICIES)

    op.execute("GRANT USAGE ON SCHEMA public TO crm_app")
    op.execute("GRANT SELECT, INSERT, UPDATE ON tenant, entity, app_user, number_series, account, contact TO crm_app")
    # Nothing is hard-deleted in Phase 1: accounts are set Inactive, users are deactivated.
    op.execute("GRANT SELECT, INSERT ON audit_log TO crm_app")  # append-only
    op.execute("GRANT USAGE ON SEQUENCE audit_log_id_seq TO crm_app")
    op.execute("REVOKE ALL ON alembic_version FROM crm_app")

    # Let the migration login switch to crm_app (SET LOCAL ROLE). On Azure the admin login
    # isn't a superuser, and from PostgreSQL 16 the creator needs explicit membership.
    op.execute("""
    DO $$ BEGIN
      BEGIN
        EXECUTE 'SET LOCAL ROLE crm_app';
        EXECUTE 'RESET ROLE';
      EXCEPTION WHEN insufficient_privilege THEN
        IF current_setting('server_version_num')::int >= 160000 THEN
          EXECUTE format('GRANT crm_app TO %I WITH SET TRUE, INHERIT FALSE', current_user);
        ELSE
          EXECUTE format('GRANT crm_app TO %I', current_user);
        END IF;
      END;
    END $$;
    """)


def downgrade() -> None:
    for t in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    for f in ["audit_row()", "touch_updated_at()", "guard_number_series()",
              "app_can_edit(uuid, uuid)", "app_manages_entity(uuid)", "app_sees_entity(uuid)",
              "app_is_admin()", "app_level()", "app_user_id()", "app_entity()", "app_tenant()",
              "app_setting(text)"]:
        op.execute(f"DROP FUNCTION IF EXISTS {f}")
