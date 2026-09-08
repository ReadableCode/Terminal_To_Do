# Terminal_To_Do — Postgres / PostgREST Migration Plan

**Uncommitted plan, 2026-08-27. Scaffolding for the work — do not commit it
with the implementation.**

Authority: `~/GitHub/dotfiles/docs/homelab_postgres_app_conventions.md` (**I1**…**I11**
refer to its invariants). Gold standard: `~/GitHub/Solitaire_Associations`.
Read the conventions doc first.

This is the smallest of the three migrations and a good one to do first — the
data model is one table and the failure blast radius is a personal task list,
not financial records or other people's accounts.

---

## 1. Current state

A Textual/terminal task app run from several machines. Persistence is a SQLite
file round-tripped through S3 on every session:

- `src/main.py:117` — `get_sqlite_connection()` opens `data/tasks.db` and
  creates the one table:
  `tasks(id INTEGER PK AUTOINCREMENT, priority INTEGER DEFAULT 0, category TEXT, title TEXT NOT NULL, description TEXT, status TEXT NOT NULL)`.
- `src/main.py:459` downloads the file from S3 at start; `:494` re-uploads it
  at the end (`readable_utils.s3_tools`).
- `backup_database_as_csv()` (`:239`) writes `data/tasks_backup_most_recent.csv`
  plus a dated copy under `data/archive/`.

Gaps: **I1** (no schema in the shared cluster), **I2** (no PostgREST), **I5**
(no RLS), **I6** (no version-gated bootstrap), **I8** (SQLite).

The real defect is not SQLite — it is that **whole-file sync is the concurrency
control**. Two machines in the same day means one silently overwrites the
other's tasks, with no conflict and no error. That is the thing this migration
fixes.

Clone list note: `personal_repos.yaml` gives this repo
`hosts: [MacBookProM5, Envy, UltraPocket, RyzenWhite]` — so "several machines"
is literal, and the overwrite hazard is live.

## 2. Target

Schema `terminal_to_do` in database `apps`, role `terminal_to_do_user`
(`NOLOGIN`, **I3**), served by the shared PostgREST at
`https://pgrest.tinkernet.me` (off-LAN machines already reach it; that is what
makes this viable for a CLI).

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

- **`INTEGER AUTOINCREMENT` → `uuid`.** RLS and the JWT `user_id` claim are
  uuid-based across every other app (**I5**), and a sequence is exactly the
  thing that collides when two machines write. `legacy_id` preserves the old
  number so a task can still be traced back to the CSV backups.
- **`NULL`-able TEXT → `NOT NULL DEFAULT ''`.** SQLite let `category` and
  `description` be null; every other app in the fleet uses empty-string
  defaults. Normalize during the import (§4), not with a later `ALTER`.

`created_at`/`updated_at` do not exist in the source data. Backfill them to the
import timestamp and say so in the import output — do not fabricate plausible
per-task dates.

### 2.2 `deploy/03_secure_users.sql` / `deploy/04_rls.sql`

Standard. Copy Solitaire's, rename to `terminal_to_do`, apply the policy to
`terminal_to_do.tasks`. Both `USING` and `WITH CHECK`.

## 3. Code changes

`src/main.py` is one long module holding config, storage, and UI together.
Split it — the storage seam is the whole point (**I2**):

| File | Change |
|---|---|
| `src/store.py` (new) | Copy `Solitaire_Associations/app/store.py`. `add_task`/`edit_task`/`delete_task`/list-and-filter become PostgREST calls with `Accept-Profile`/`Content-Profile` pinned (**I9**). |
| `src/bootstrap.py` (new) | Copy `Solitaire_Associations/app/bootstrap.py`. `SCHEMA_VERSION = 1`. Runs at CLI start; the version gate makes it a cheap no-op after the first run (**I6**). |
| `src/auth.py`, `src/users.py`, `src/users_cli.py` (new) | Copy Solitaire's. Token cached to a mode-`0600` file under the user config dir so the CLI does not prompt every invocation; the cache holds only the JWT, never the password. |
| `src/config.py` (new) | `APP_SCHEMA`, `POSTGREST_URL` (default `https://pgrest.tinkernet.me`), `AUTH_URL` if applicable, `POSTGRES_*` for bootstrap only. No fallback store (**I8**). |
| `src/main.py` | Keeps the UI and the command loop. Every `sqlite3` import, `conn` argument and `get_sqlite_connection` call goes. |
| `pyproject.toml` | Drop the `readable_utils.s3_tools` dependency if nothing else in the repo uses it — check before removing, `readable_utils` is shared. |
| `.gitignore` / `data/` | `data/tasks.db` stops being written. Leave the existing file and the CSV archive on disk (§4). |

The S3 download/upload block (`main.py:459`, `:494`) is deleted outright. Do not
keep it as a "backup" — a second write path to a second store is how the two
diverge.

## 4. Data migration

Write `scripts/import_sqlite.py`, run once per source database:

1. Take `--sqlite-path` (default `data/tasks.db`) and `--username`.
2. **Reconcile the copies first.** The S3 file and each machine's local file may
   all differ, precisely because of the overwrite bug. Before importing,
   download the S3 copy and diff it against every local `data/tasks.db` you can
   reach. Print the differences and **stop for Jason to resolve them.** Do not
   auto-merge and do not pick a winner by mtime — an mtime heuristic here is how
   tasks get silently deleted.
3. Insert the agreed task set, mapping `id` → `legacy_id`, coalescing null
   `category`/`description` to `''`, stamping `created_at`/`updated_at` to the
   import time.
4. Print a before/after row count and exit non-zero on mismatch.
5. Leave `data/tasks.db` and everything under `data/archive/` **in place**.
   Per Jason's rule on generated output files, those CSVs are not disposable,
   and they are the only record of the pre-migration state.

## 5. Registration (**I11**)

- `Docker/docker_compose_projects.yaml` → append `terminal_to_do` to
  `PGRST_DB_SCHEMAS`; PostgREST must be recreated.
- No compose include, no `REPO_SERVICES` entry, no SWAG conf, no DNS. This app
  is not deployed as a container — it is a CLI that talks to the shared
  PostgREST from wherever it runs. That is a legitimate shape, not an omission.

## 6. Auth — no existing users to protect, but still standard

Unlike Sync_Plex and Cash_Flow_Commander, this app has **no accounts today**,
so the no-password-reset constraint does not bind here. Follow the conventions
anyway (§2.1 `users` table, standard login, standard token) so the fleet stays
uniform and this app is not a special case when the auth decision lands.

Do not implement, change, or unify auth beyond copying what
`Solitaire_Associations` does today. The unification decision is pending.

## 7. Explicitly out of scope

- No new features. Recurring tasks, due dates, tags and sub-tasks are all
  tempting while the schema is open; none are in scope.
- `terminal_to_do_config_defaults.json` and the user config file stay as they
  are. Local preferences are not application data and do not belong in Postgres.
- No offline mode. If PostgREST is unreachable, the app fails loudly (**I8**).
  If offline use turns out to matter, that is a separate design conversation —
  a local cache is not something to bolt on during a storage migration.

## 8. Open questions for Jason (do not guess)

1. **Which copy of `tasks.db` is authoritative?** §4 step 2 needs an answer,
   and it is the only step that can lose data.
2. **Does the app need to work without network access?** Answer decides whether
   §7's "no offline mode" holds.
3. **Is anything else importing `readable_utils.s3_tools`?** Affects whether the
   dependency can be dropped.

## 9. Definition of done

- [ ] `terminal_to_do` in `PGRST_DB_SCHEMAS`; PostgREST recreated
- [ ] Bootstrap version-gated, runs at CLI start, no-op on second run
- [ ] All copies of `tasks.db` reconciled with Jason before import; nothing auto-merged
- [ ] Row counts match; `legacy_id` populated for every imported task
- [ ] `data/tasks.db` and `data/archive/*.csv` still on disk, untouched
- [ ] Zero `sqlite3` and zero `s3_tools` references remain in `src/`
- [ ] Two machines can add tasks in the same session without either losing rows — test this explicitly, it is the bug being fixed
- [ ] A hand-made token for a different `user_id` cannot read the tasks, verified against PostgREST directly
- [ ] Real-DB and real-PostgREST tests green from the dev machine (**I10**) — no skips
