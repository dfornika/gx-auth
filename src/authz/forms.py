"""Forms for the read-only admin inspector.

Choices come from the store's *active* authorization model rather than from
`fga/model.fga` on disk — the two can drift, and the engine answers with the
former.
"""

from django import forms


class TupleFilterForm(forms.Form):
    """Filters for the tuple browser.

    Every combination is accepted. Where the engine refuses to filter (relation
    alone, or an object type with neither an id nor a user) the view falls back
    to scanning — see `inspector.query_tuples`.
    """

    # Free text rather than dropdowns, with the active model's values offered as
    # suggestions. A store outlives its models: this one holds `group:lab-x` and
    # `access_level_ok` tuples written under an earlier model that no longer
    # defines either. A closed choice list would make those unfindable.
    object_type = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"list": "fga-object-types", "autocomplete": "off"}),
        help_text="e.g. “project”. Suggestions come from the active model.",
    )
    object_id = forms.CharField(required=False, help_text="Id only, e.g. “demo”.")
    relation = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"list": "fga-relations", "autocomplete": "off"}),
        help_text=(
            "Suggestions list only relations that can be stored. Permissions like "
            "can_view are computed and are never rows in the store — expand one instead."
        ),
    )
    user = forms.CharField(
        required=False,
        help_text="Fully qualified subject, e.g. “user:alice” or “group:lab-x#member”.",
    )
    page_size = forms.TypedChoiceField(
        required=False,
        coerce=int,
        empty_value=50,
        choices=[(10, "10"), (25, "25"), (50, "50"), (100, "100")],
        initial=50,
    )

    def __init__(self, *args, object_types=(), relations=(), **kwargs):
        super().__init__(*args, **kwargs)
        #: Rendered as <datalist> options by the template.
        self.object_types = tuple(object_types)
        self.relations = tuple(relations)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("object_id") and not cleaned.get("object_type"):
            self.add_error(
                "object_type",
                "Choose an object type to go with the object id — the engine "
                "identifies objects as “type:id”.",
            )
        return cleaned

    def filters(self) -> dict:
        """The cleaned filter set, as kwargs for `inspector.query_tuples`."""
        c = self.cleaned_data
        return {
            "object_type": c.get("object_type", "").strip(),
            "object_id": c.get("object_id", "").strip(),
            "relation": c.get("relation", "").strip(),
            "user": c.get("user", "").strip(),
            "page_size": c.get("page_size") or 50,
        }

    @property
    def has_filters(self) -> bool:
        """Whether any filter was actually supplied (ignoring page size)."""
        if not self.is_valid():
            return False
        f = self.filters()
        return any(f[k] for k in ("object_type", "object_id", "relation", "user"))


class ExpandForm(forms.Form):
    """Which `object#relation` to resolve."""

    object = forms.CharField(
        label="Object",
        help_text="Fully qualified, e.g. “project:demo-sub” or “sample:demo-s2”.",
    )
    relation = forms.CharField(
        label="Relation",
        help_text="Storable or computed, e.g. “admin” or “can_view”.",
    )
    depth = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=8,
        initial=6,
        help_text="How many engine calls deep to follow inherited access.",
    )

    def clean_object(self):
        obj = self.cleaned_data["object"].strip()
        if ":" not in obj:
            raise forms.ValidationError("Objects are written “type:id”, e.g. “project:demo”.")
        return obj

    def clean_relation(self):
        return self.cleaned_data["relation"].strip()
