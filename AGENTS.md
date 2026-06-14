# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

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

- `models/` — split into separate files: `learning_resource.py`, `learning_unit.py`, `resource_type.py`, `querysets.py`
- `views/` — split: `dashboard.py`, `learning_resource.py`, `learning_unit.py`
- `services/` — business logic separated from views: `dashboard.py` (stats aggregation), `progress.py` (per-resource progress), `utils.py`
- `api/` — DRF viewsets + serializers for `LearningResource` and `LearningUnit`

**Data model:**

`ResourceType` → `LearningResource` (user-owned) → `LearningUnit` (ordered within a resource)

- `ResourceType` has a `content_kind` (`video` or `reading`) that drives the unit label ("Unit" vs "Chapter") and is either system-seeded (`is_system=True`) or user-created.
- `LearningUnit.status` auto-updates from `video_progress_minutes` on every `save()` — do not set status directly when `video_progress_minutes` is present.
- `LearningResourceQuerySet.with_progress()` annotates querysets with `total_units`, `completed_units`, and `percentage` — use this instead of computing in Python.

**Permission pattern:**

Views use `UserPermissionMixin` (combines `LoginRequiredMixin` + `PermissionRequiredMixin`) and redirect to `index` instead of raising 403. All resource views filter to `request.user` via `BaseUserResourceView.get_queryset()`.

**Dashboard stats:**

`learning/services/dashboard.py::get_dashboard_stats()` is the single source of truth for both the user dashboard (`/learning/dashboard/`) and the staff admin dashboard. It accepts optional `user` and `resource_type` filters; passing `user=None` returns site-wide data (used by the admin view).

**CSS:**

SCSS source lives in `web/studyflow/src/sass/`. Compiled output goes to `web/studyflow/static/css/main.css`. Bootstrap is vendored in `web/static_files/`.

**Environment:**

Copy `web/.env.example` to `web/.env` and fill in Postgres credentials. Tests use SQLite in-memory when `CI=true` is set; locally they require a running Postgres instance.

**Test fixtures:**

`web/conftest.py` provides `user` (superuser) and `client_logged_in` fixtures via `model_bakery`. Use `baker.make(...)` for test object creation.
