"""Read-only OpenFGA inspector pages, hosted inside the admin.

These are plain Django views wrapped in `admin.site.admin_view()` (see
`admin_urls.py`) rather than ModelAdmin screens: none of what they show lives in
Django's database. They consume no django-unfold Python API — the templates
extend `admin/base_site.html`, which resolves to unfold's copy because "unfold"
precedes "django.contrib.admin" in INSTALLED_APPS.

Strictly read-only. Grants must keep going through `POST /api/authz/grants` so
the GrantAudit trail stays honest.
"""

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.views.generic import TemplateView

from .forms import ExpandForm, TupleFilterForm
from .services import inspector


class InspectorView(TemplateView):
    """Shared chrome: superuser gate, admin context, store status strip."""

    title = ""
    tab = ""

    def dispatch(self, request, *args, **kwargs):
        # admin_view() already requires an active staff user. These pages expose
        # the entire live authorization graph — every project, every grant,
        # including ones the viewer holds no rights over — so require more.
        if not request.user.is_superuser:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = {
            **admin.site.each_context(self.request),
            **super().get_context_data(**kwargs),
        }
        context.setdefault("status", inspector.store_status())
        context["title"] = self.title
        context["tab"] = self.tab
        return context


class TupleBrowserView(InspectorView):
    template_name = "admin/fga/tuples.html"
    title = "Live tuples"
    tab = "tuples"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = context["status"]
        if not status.configured or status.error:
            return context

        try:
            _model, object_types, relations = inspector.model_choices()
        except Exception as exc:
            context["error"] = inspector.describe_error(exc)
            return context

        # Bound to GET: filters stay linkable and bookmarkable, and there is no
        # CSRF token to carry because nothing here writes.
        has_query = any(k in self.request.GET for k in TupleFilterForm.base_fields)
        form = TupleFilterForm(
            self.request.GET if has_query else None,
            object_types=object_types,
            relations=relations,
        )
        context["form"] = form

        if has_query and not form.is_valid():
            return context

        filters = form.filters() if has_query else {}
        # The continuation token is a link-only parameter, never a form field,
        # so submitting the form naturally resets paging.
        token = self.request.GET.get("token", "")
        try:
            result = inspector.query_tuples(**filters, continuation_token=token)
        except Exception as exc:
            context["error"] = inspector.describe_error(exc)
            return context

        context["result"] = result
        context["page_number"] = self._page_number()
        if result.continuation_token:
            context["next_page_query"] = self._next_page_query(result.continuation_token)
        return context

    def _page_number(self) -> int:
        try:
            return max(1, int(self.request.GET.get("p", 1)))
        except (TypeError, ValueError):
            return 1

    def _next_page_query(self, token: str) -> str:
        params = self.request.GET.copy()
        params["token"] = token
        params["p"] = str(self._page_number() + 1)
        return params.urlencode()


class ExpandView(InspectorView):
    template_name = "admin/fga/expand.html"
    title = "Expand"
    tab = "expand"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = context["status"]
        if not status.configured or status.error:
            return context

        try:
            _model, _types, relations = inspector.model_choices()
            context["known_relations"] = relations
        except Exception:
            context["known_relations"] = ()

        submitted = "object" in self.request.GET
        form = ExpandForm(self.request.GET if submitted else None)
        context["form"] = form
        if not submitted or not form.is_valid():
            return context

        obj = form.cleaned_data["object"]
        relation = form.cleaned_data["relation"]
        depth = form.cleaned_data.get("depth") or inspector.MAX_DEPTH

        try:
            context["result"] = inspector.expand_recursive(obj, relation, max_depth=depth)
        except Exception as exc:
            context["error"] = inspector.describe_error(exc)
            return context

        # Independent of the tree on purpose: the engine's own answer to
        # "who holds this?", used as a cross-check rather than folding the tree.
        users, users_error = inspector.effective_users(obj, relation)
        context["effective_users"] = users
        context["effective_users_error"] = users_error
        context["expanded_object"] = obj
        context["expanded_relation"] = relation
        return context


class ProjectTreeView(InspectorView):
    template_name = "admin/fga/tree.html"
    title = "Project hierarchy"
    tab = "tree"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = context["status"]
        if not status.configured or status.error:
            return context
        try:
            context["tree"] = inspector.project_tree()
        except Exception as exc:
            context["error"] = inspector.describe_error(exc)
        return context
