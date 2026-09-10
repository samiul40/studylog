# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## How to work on this repo

Plan first, then build in reviewable chunks:

1. **Write a plan and get it approved before writing code.** Research the existing conventions, then present the plan for review. Flag any deviation from an established pattern explicitly, along with the reason.
2. **Implement in chunks, not all at once.** Split the work along natural seams (model → migration → form → view → page → tests) and stop after each one.
3. **Show the diff for each chunk and wait for review before committing it.** Don't chain several chunks together and present them at the end.
4. **Commit each reviewed chunk separately**, so the history matches the review steps. Commit messages are one line, no `Co-Authored-By` trailer.
5. Ask before squashing — squashing discards the step-by-step history, it doesn't preserve it.

Verify before calling a chunk done: `pytest`, `ruff check web/`, and for UI work `npm run build:css` plus the page in a browser in both themes. Say so explicitly if something couldn't be verified.

## Commands

All commands run from `web/`.

**Run the dev server:**
```bash
cd web && python manage.py runserver
```

**Run tests:**
```bash
cd web && pytest
```

`pytest.ini` sets `addopts = -n 4`, so this is already parallel across 4 xdist workers. Pass `-n 0` to force a serial run — required for `--pdb`, and for reading `print()` output.

**Run a single test file:**
```bash
cd web && pytest learning/tests/test_learning_resource_views.py
```

**Run tests with coverage:**
```bash
cd web && pytest --cov
```

**Lint:**
```bash
ruff check web/
```

**Format/fix lint:**
```bash
ruff check --fix web/
```

**Watch SCSS (dev):**
```bash
cd web && npm run watch:css
```

**Build CSS (production):**
```bash
cd web && npm run build:css
```

**Database migrations:**
```bash
cd web && python manage.py makemigrations
cd web && python manage.py migrate
```

## Architecture

This is a Django 5.2 + PostgreSQL application. The Django project root is `web/`, with the Django settings package at `web/studyflow/`.

**Django apps:**
- `learning` — core domain; the bulk of the app lives here
- `accounts` — login/logout/profile using Django's built-in `auth`
- `pages` — static/landing pages

**`learning` app structure:**

- `models/` — normally one file per model (`learning_resource.py`, `study_session.py`, `feature_request.py`, …) plus `querysets.py`; every model is re-exported from `models/__init__.py`. Tightly-coupled models that only make sense together (a `Book`/`Author` pair, say) may share a file — **ask before grouping them**, don't decide it unilaterally
- `views/` — one file per feature area (`dashboard.py`, `learning_resource.py`, `study_session.py`, `feature_request.py`, …), re-exported from `views/__init__.py`
- `services/` — business logic separated from views: `dashboard/` (stats aggregation), `progress.py` (per-resource progress), `sessions.py`, `youtube.py`, `utils.py`
- `forms.py` — a single module holding every form in the app (not split per model)
- `mixins.py` — `UserPermissionMixin`
- `src/sass/` — one SCSS partial per page/component, each with its own class prefix

There is no REST API layer: no DRF, no `api/` package, no serializers. Everything is server-rendered. Don't add DRF for a single endpoint — see the AJAX note under *Adding a feature*.

**Data model:**

`ResourceType` → `LearningResource` (user-owned) → `LearningUnit` (ordered within a resource)

- `ResourceType` has a `content_kind` (`video` or `reading`) that drives the unit label ("Unit" vs "Chapter") and is either system-seeded (`is_system=True`) or user-created.
- `LearningUnit.status` auto-updates from `video_progress_minutes` on every `save()` — do not set status directly when `video_progress_minutes` is present.
- `LearningResourceQuerySet.with_progress()` annotates querysets with `total_units`, `completed_units`, and `percentage` — use this instead of computing in Python.

**Permission pattern:**

Views use `UserPermissionMixin` (combines `LoginRequiredMixin` + `PermissionRequiredMixin`) and redirect to `index` instead of raising 403. All resource views filter to `request.user` via `BaseUserResourceView.get_queryset()`.

Permissions reach real users through the **"Learning User" group**, which `accounts/signals.py` attaches on signup. The group's permissions are populated by hand-written data migrations (`learning/migrations/0022_study_session_group_permissions.py` is the template). Django's default `add_*`/`view_*` permissions existing is not enough — if a new model's permissions aren't added to that group, every non-superuser gets silently redirected to `index` while the superuser test fixture still passes.

**Dashboard stats:**

`get_dashboard_stats()` (defined in `learning/services/dashboard/_orchestrator.py`, exported from the `dashboard` package) is the single source of truth for both the user dashboard (`/learning/dashboard/`) and the staff admin dashboard. It accepts optional `user` and `resource_type` filters; passing `user=None` returns site-wide data (used by the admin view).

**CSS:**

SCSS source lives in `web/studyflow/src/sass/` (shared: tokens, base, components) and `web/learning/src/sass/` (per-page partials). `main.scss` is the single entry point and `@use`s every partial. Compiled output goes to `web/studyflow/static/css/main.css`, which is **gitignored** — commit the SCSS source only, never the build artefact.

Design tokens are CSS custom properties (`--ink`, `--paper`, `--card`, `--field`, `--line`, `--emerald`, `--emerald-deep`, `--emerald-bright`, `--rose`, `--r-lg`) defined in `abstracts/_variables.scss`, with dark values in `base/_themes.scss`. Only the three font stacks are SCSS variables (`$font-display`, `$font-sans`, `$font-mono`). A few extra tokens (`--ease`, `--focus`, `--shadow-card`, `--rf-hint`, `--rf-placeholder`) are declared in `_resource_form.scss` and reused by later partials — use them, but don't redeclare them at `:root` in a new partial, since the last file loaded wins globally.

Tint colours with `color-mix(in srgb, var(--emerald) 16%, transparent)` rather than SCSS `rgba()`/`darken()`.

**Environment:**

Copy `web/.env.example` to `web/.env` and fill in Postgres credentials. Tests use SQLite in-memory when `CI=true` is set; locally they require a running Postgres instance.

**Test fixtures:**

`web/conftest.py` provides `user` (superuser) and `client_logged_in` fixtures via `model_bakery`. Use `baker.make(...)` for test object creation.

It also has an autouse `fast_password_hashing` fixture that swaps `PASSWORD_HASHERS` to MD5 for the test run — PBKDF2 costs ~0.6s per test and nearly every test builds a user. Keep that override in `conftest.py`; putting it in `settings.py` would hash real users' passwords with MD5.

Tests are function-based with `pytestmark = pytest.mark.django_db` at module level. Migrations **do** run for the test database, so data migrations are exercised. Because the `user` fixture is a superuser it bypasses permission checks — cover real-user access separately by adding the `"Learning User"` group to a plain `baker.make("auth.User", is_superuser=False)`.

Anything cached (notably `django_ratelimit` counters) leaks between tests: the cache is process-wide while the DB rolls back, and row IDs get reused, so one test's requests can consume another's allowance. Clear it with an autouse fixture calling `cache.clear()` — see `learning/tests/test_feature_request_views.py`.

## Adding a feature

The `FeatureRequest` feature (model → form → view → page) is the most recent end-to-end example; follow its shape. Order matters because each step depends on the last.

**1. Model** — new file in `learning/models/`, exported from `models/__init__.py` (alphabetical, mirrored in `__all__`). If the feature adds several models that are meaningless apart, propose putting them in one file and ask before doing it. Conventions: `settings.AUTH_USER_MODEL` FK with an explicit `related_name`; inner `class XChoices(models.TextChoices)` for enums (never plain tuples); `created_at = auto_now_add` / `updated_at = auto_now`; `Meta.db_table` as explicit snake_case, `Meta.ordering`, and named entries in `Meta.indexes` (`"lr_user_archived_idx"` style). Prefer `CharField(max_length=...)` over `TextField()` for user-supplied prose so the cap is enforced by the column, not just the form. Use `on_delete=SET_NULL` + `null=True` when a record should outlive its owner.

**2. Migrations** — `makemigrations` for the schema, then a hand-written data migration adding the model's permissions to the `"Learning User"` group (see *Permission pattern*). Never edit an existing migration.

**3. Form** — append a `ModelForm` to `learning/forms.py`. Declare fields explicitly on the class when you need validation beyond the model's (`min_length`, custom `required`); `forms.CharField` already strips whitespace. Widget `attrs={"class": ...}` carry the page's own control class. Field-level rules go in `clean_<field>()`, cross-field rules in `clean()` with `add_error()`.

**4. View** — new file in `learning/views/`, exported from `views/__init__.py`. Use Django's generic CBVs + `UserPermissionMixin` with `permission_required = "learning.<action><modelname>"`. Scope ownership in `form_valid` (`form.instance.user = self.request.user`) and confirm success with `messages.success`. Submissions are **POST → redirect (PRG)**, never fetch/JSON — the only `fetch()` calls in the app are auxiliary lookups like `learning/views/youtube.py`. To rate-limit, copy that file's pattern: `@method_decorator(ratelimit(key="user", rate="5/h", method="POST", block=False), name="dispatch")` plus a manual `request.limited` check.

**5. URL** — add to `learning/urls.py` (namespaced `learning:<noun>_<action>`). Only register a route directly in `studyflow/urls.py` when the path must sit at the root without the `learning/` prefix, as `/feature-request/` does.

**6. Page** — each full-page form gets its **own SCSS partial with its own class prefix** (`rf-` resource form, `ss-` session form, `fr-` feature request); there are no shared generic `.card`/`.btn`/`.control` classes, so don't reach for them. Add the partial to `main.scss`'s `// Apps` group. The template extends `base.html` and overrides `{% block main_class %}` (to replace Bootstrap's container with the page's own `*-bg`) plus empty `{% block breadcrumbs %}` / `{% block alerts %}` when the card handles its own. Write field markup by hand with `name="..."` and `value="{{ form.x.value|default:'' }}"` rather than `{{ form.x }}`, and render errors as an always-present `*-field__err` div revealed by a `*-field--invalid` modifier on the wrapper. Mirror validation in HTML attributes for instant feedback, but the server stays authoritative. Page column is 750px (`max-width` on `*-page`), padding via `clamp()`.

**7. Tests** — `learning/tests/test_<feature>_model.py` and `test_<feature>_views.py`. Cover the happy path (object created and owned by the right user), each rejected input, unauthenticated access, and real-user permission via the group.

Verify with: `pytest`, `ruff check web/`, `npm run build:css`, then the page in a browser in both light and dark themes.
