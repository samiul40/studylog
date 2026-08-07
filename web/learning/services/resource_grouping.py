SYSTEM_CATEGORY_ORDER = ["science", "technology", "mathematics", "humanities"]
OTHER_LABEL = "Other"


def group_resources_by_category(resources):
    """
    Group an iterable of (already-annotated) LearningResource instances into
    ordered category buckets for display on the resources list page.

    Order: system categories in SYSTEM_CATEGORY_ORDER, then any custom
    (user-created) categories alphabetically, then "Other" last for
    resources with no category set. Buckets with zero resources are omitted
    — "Other" is a display-time fallback, never written to the database.
    """
    buckets = {}
    other = []

    for resource in resources:
        category = resource.category
        if category is None:
            other.append(resource)
        else:
            buckets.setdefault(category, []).append(resource)

    def sort_key(pair):
        category, _items = pair
        if category.is_system and category.slug in SYSTEM_CATEGORY_ORDER:
            return (0, SYSTEM_CATEGORY_ORDER.index(category.slug))
        return (1, category.name.lower())

    groups = [
        {
            "name": category.name,
            "slug": category.slug,
            "resources": items,
            "count": len(items),
        }
        for category, items in sorted(buckets.items(), key=sort_key)
    ]

    if other:
        groups.append(
            {
                "name": OTHER_LABEL,
                "slug": "other",
                "resources": other,
                "count": len(other),
            }
        )

    return groups
