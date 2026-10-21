# Terminal_To_Do: Postgres / PostgREST Migration Plan

**Plan, 2026-08-27. Scaffolding for the work; not part of the implementation.**

This moves task storage from a synced SQLite file to a schema in a shared
Postgres database, served over HTTP by PostgREST. The data model is one table
and the failure blast radius is a personal task list, so it is a small,
low-risk migration.

The target follows a set of conventions shared by the other apps on the same
database:

- each app owns its own schema in the shared cluster;
- apps reach the database only through PostgREST, never a direct driver;
- each app has a `NOLOGIN` database role that PostgREST switches to;
- row-level security (RLS) scopes every row to the `user_id` claim in the JWT;
- schema bootstrap runs at app start, is additive and idempotent, and is
  gated on a schema version so later runs are a cheap no-op;
- there is one store per app: no SQLite, no fallback store;
- PostgREST requests pin the schema with `Accept-Profile` / `Content-Profile`;
- tests run against the real database and real PostgREST, with no skips;
- a new schema is registered by adding it to PostgREST's `PGRST_DB_SCHEMAS`.

---

## 1. Current state

A terminal task app run from several machines. Persistence is a SQLite file
round-tripped through S3 on every session:

- `get_sqlite_connection()` in `src/main.py` opens `data/tasks.db` and
  creates the one table:
  `tasks(id INTEGER PK AUTOINCREMENT, priority INTEGER DEFAULT 0, category TEXT, title TEXT NOT NULL, description TEXT, status TEXT NOT NULL)`.
- `main()` downloads the file from S3 at start and re-uploads it at the end
  (`readable_utils.s3_tools`).
- `backup_database_as_csv()` writes `data/tasks_backup_most_recent.csv`
  plus a dated copy under `data/archive/`.

Gaps against the conventions: no schema in the shared cluster, no PostgREST,
no RLS, no version-gated bootstrap, SQLite as the store.

The real defect is not SQLite. It is that **whole-file sync is the concurrency
control**. Two machines in the same day means one silently overwrites the
other's tasks, with no conflict and no error. That is the thing this migration
fixes. The repo is cloned on four machines, so the overwrite hazard is live.

## 2. Target

Schema `terminal_to_do` in the shared apps database, role `terminal_to_do_user`
(`NOLOGIN`), served by the shared PostgREST instance. That instance is already
reachable from off-LAN machines, which is what makes this viable for a CLI.

### 2.1 `deploy/02_schema.sql`

```sql
CREATE SCHEMA IF NOT EXISTS terminal_to_do;

CREATE TABLE IF NOT EXISTS terminal_to_do.users (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    username            text UNIQUE NOT NULL,
    password_hash       text NOT NULL,
    role                text NOT NULL DEFAULT 'user',
    display_name        text NOT NULL DEFAULT '',
    disabled            boolean NOT NULL DEFAULT false,
    created_at          timestamptz NOT NULL DEFAULT now(),
    password_changed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS terminal_to_do.tasks (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid NOT NULL REFERENCES terminal_to_do.users (id) ON DELETE CASCADE,
    legacy_id   integer,          -- the old sqlite rowid, kept for traceability
    priority    integer NOT NULL DEFAULT 0,
    category    text NOT NULL DEFAULT '',
    title       text NOT NULL,
    description text NOT NULL DEFAULT '',
    status      text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_terminal_to_do_tasks_user   ON terminal_to_do.tasks (user_id);
CREATE INDEX IF NOT EXISTS idx_terminal_to_do_tasks_status ON terminal_to_do.tasks (status);

GRANT USAGE ON SCHEMA terminal_to_do TO terminal_to_do_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON terminal_to_do.tasks TO terminal_to_do_user;
```

Two deliberate changes from the SQLite shape, both required by the conventions
rather than chosen for taste:

- **`INTEGER AUTOINCREMENT` to `uuid`.** RLS and the JWT `user_id` claim are
  uuid-based across the other apps, and a sequence is exactly the thing that
  collides when two machines write. `legacy_id` preserves the old number so a
  task can still be traced back to the CSV backups.
- **`NULL`-able TEXT to `NOT NULL DEFAULT ''`.** SQLite let `category` and
  `description` be null; the other apps use empty-string defaults. Normalize
  during the import (section 4), not with a later `ALTER`.

`created_at`/`updated_at` do not exist in the source data. Backfill them to the
import timestamp and say so in the import output; do not fabricate plausible
per-task dates.

### 2.2 `deploy/03_secure_users.sql` / `deploy/04_rls.sql`

Standard. Copy the reference app's, rename to `terminal_to_do`, apply the
policy to `terminal_to_do.tasks`. Both `USING` and `WITH CHECK`.

## 3. Code changes

`src/main.py` is one long module holding config, storage, and UI together.
Split it; the storage seam is the whole point:

| File | Change |
|---|---|
| `src/store.py` (new) | Copy the reference app's `store.py`. `add_task`/`edit_task`/`delete_task`/list-and-filter become PostgREST calls with `Accept-Profile`/`Content-Profile` pinned. |
| `src/bootstrap.py` (new) | Copy the reference app's `bootstrap.py`. `SCHEMA_VERSION = 1`. Runs at CLI start; the version gate makes it a cheap no-op after the first run. |
| `src/auth.py`, `src/users.py`, `src/users_cli.py` (new) | Copy the reference app's: login and hashing come from the postgrest-auth library (a uv git dependency, conventions §4). Token cached to a mode-`0600` file under the user config dir so the CLI does not prompt every invocation; the cache holds only the JWT, never the password. |
| `src/config.py` (new) | `APP_SCHEMA`, `POSTGREST_URL` and the JWT secret (from the environment), `POSTGRES_*` for bootstrap and login. No fallback store. |
| `src/main.py` | Keeps the UI and the command loop. Every `sqlite3` import, `conn` argument and `get_sqlite_connection` call goes. |
| `pyproject.toml` | Drop the `readable_utils.s3_tools` dependency if nothing else in the repo uses it. Check before removing; `readable_utils` is shared. |
| `.gitignore` / `data/` | `data/tasks.db` stops being written. Leave the existing file and the CSV archive on disk (section 4). |

The S3 download/upload block in `main()` is deleted outright. Do not keep it as
a "backup"; a second write path to a second store is how the two diverge.

## 4. Data migration

Write `scripts/import_sqlite.py`, run once per source database:

1. Take `--sqlite-path` (default `data/tasks.db`) and `--username`.
2. **Reconcile the copies first.** The S3 file and each machine's local file may
   all differ, precisely because of the overwrite bug. Before importing,
   download the S3 copy and diff it against every local `data/tasks.db` you can
   reach. Print the differences and **stop for the owner to resolve them.** Do
   not auto-merge and do not pick a winner by mtime; an mtime heuristic here is
   how tasks get silently deleted.
3. Insert the agreed task set, mapping `id` to `legacy_id`, coalescing null
   `category`/`description` to `''`, stamping `created_at`/`updated_at` to the
   import time.
4. Print a before/after row count and exit non-zero on mismatch.
5. Leave `data/tasks.db` and everything under `data/archive/` **in place**.
   Generated output files are not disposable, and those CSVs are the only
   record of the pre-migration state.

## 5. Registration

- Append `terminal_to_do` to `PGRST_DB_SCHEMAS` in the PostgREST service
  definition; PostgREST must be recreated.
- No container, reverse-proxy config or DNS entry. This app is not deployed as
  a container; it is a CLI that talks to the shared PostgREST from wherever it
  runs. That is a legitimate shape, not an omission. Login runs in-process,
  so the machine also needs the superuser `POSTGRES_*` connection (LAN or
  Tailscale), the same as load-log's TUI.

## 6. Auth: no existing users to protect, but still standard

Unlike some of the other apps, this one has **no accounts today**, so there is
no constraint against forcing password resets. Follow the conventions anyway
(section 2.1 `users` table, standard login, standard token) so all apps stay
uniform.

The auth decision has landed: every app logs in through the postgrest-auth
library in-process (conventions §4). Do not write auth code beyond copying
what the reference app does.

## 7. Explicitly out of scope

- No new features. Recurring tasks, due dates, tags and sub-tasks are all
  tempting while the schema is open; none are in scope.
- `terminal_to_do_config_defaults.json` and the user config file stay as they
  are. Local preferences are not application data and do not belong in Postgres.
- No offline mode. If PostgREST is unreachable, the app fails loudly. If
  offline use turns out to matter, that is a separate design conversation; a
  local cache is not something to bolt on during a storage migration.

## 8. Open questions for the owner (do not guess)

1. **Which copy of `tasks.db` is authoritative?** Section 4 step 2 needs an
   answer, and it is the only step that can lose data.
2. **Does the app need to work without network access?** Answer decides whether
   section 7's "no offline mode" holds.
3. **Is anything else importing `readable_utils.s3_tools`?** Affects whether the
   dependency can be dropped.

## 9. Definition of done

- [ ] `terminal_to_do` in `PGRST_DB_SCHEMAS`; PostgREST recreated
- [ ] Bootstrap version-gated, runs at CLI start, no-op on second run
- [ ] All copies of `tasks.db` reconciled with the owner before import; nothing auto-merged
- [ ] Row counts match; `legacy_id` populated for every imported task
- [ ] `data/tasks.db` and `data/archive/*.csv` still on disk, untouched
- [ ] Zero `sqlite3` and zero `s3_tools` references remain in `src/`
- [ ] Two machines can add tasks in the same session without either losing rows; test this explicitly, it is the bug being fixed
- [ ] A hand-made token for a different `user_id` cannot read the tasks, verified against PostgREST directly
- [ ] Real-DB and real-PostgREST tests green from the dev machine, with no skips
