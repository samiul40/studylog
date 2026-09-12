"""Unfold renders the filter panel as a bare <div> unless a ModelAdmin sets
list_filter_submit. Link-style filters survive that — every option is its own
<a href> — but a dropdown is a form input with nothing to submit to, so it
renders, opens, and then silently does nothing when you pick a value.

Nothing in Django's checks catches the mismatch, so these tests do.
"""

import re

import pytest
from django.contrib import admin
from django.urls import reverse

pytestmark = pytest.mark.django_db

SELECT_NAME = re.compile(r'<select[^>]*name="([^"]+)"')


def changelist_url(label):
    app_label, model_name = label.split(".")
    return reverse(f"admin:{app_label}_{model_name}_changelist")


def select_names(html):
    """The names of every <select> inside the filter panel's form."""
    _, _, form = html.partition('id="filter-form"')
    return sorted(set(SELECT_NAME.findall(form)))


def filter_classes(model_admin):
    """The filter classes on one admin, however list_filter spells them."""
    for entry in model_admin.list_filter:
        # Either a bare filter class, or ("field", FilterClass).
        candidate = entry[1] if isinstance(entry, (list, tuple)) else entry
        if isinstance(candidate, type):
            yield candidate


def needs_a_form(model_admin):
    """True if any of this admin's filters renders a form input.

    Unfold's form-backed filters all carry a form_class; Django's own
    link-based ones do not.
    """
    return any(hasattr(cls, "form_class") for cls in filter_classes(model_admin))


ADMINS_WITH_FORM_FILTERS = sorted(
    (
        f"{model._meta.app_label}.{model._meta.model_name}"
        for model, model_admin in admin.site._registry.items()
        if needs_a_form(model_admin)
    ),
)


def test_the_project_actually_uses_form_filters():
    """Guards the tests below from passing because they found nothing."""
    assert ADMINS_WITH_FORM_FILTERS


@pytest.mark.parametrize("label", ADMINS_WITH_FORM_FILTERS)
def test_form_filters_come_with_a_submit(label):
    model = admin.site._registry
    model_admin = next(
        ma
        for m, ma in model.items()
        if f"{m._meta.app_label}.{m._meta.model_name}" == label
    )

    assert model_admin.list_filter_submit, (
        f"{label} has a dropdown filter but list_filter_submit is off, "
        "so choosing a value would do nothing"
    )


@pytest.mark.parametrize("label", ADMINS_WITH_FORM_FILTERS)
def test_the_filter_panel_renders_a_form(client_logged_in, label):
    content = client_logged_in.get(changelist_url(label)).content.decode()

    assert 'id="filter-form"' in content, f"{label} has no filter form to submit to"
    assert "Apply Filters" in content


@pytest.mark.parametrize("label", ADMINS_WITH_FORM_FILTERS)
def test_applying_an_untouched_filter_form_changes_nothing(client_logged_in, label):
    """Apply submits every select on the panel, set or not.

    An unset one posts an empty value, and a filter that reads that as a real
    value quietly empties the page — or redirects to ?e=1, which looks like
    the filter "did nothing" from the outside.
    """
    url = changelist_url(label)
    before = client_logged_in.get(url)
    empty = {name: "" for name in select_names(before.content.decode())}

    assert empty, f"{label} rendered no selects inside its filter form"

    after = client_logged_in.get(url, empty)

    assert after.status_code == 200, f"{label} redirected on {empty}"
    assert after.context["cl"].queryset.count() == before.context["cl"].queryset.count()
