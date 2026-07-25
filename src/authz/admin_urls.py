"""URLs for the admin-hosted OpenFGA inspector.

Included from `config/urls.py` *before* `admin.site.urls` — the admin's
`catch_all_view` matches every unclaimed `admin/*` path, so anything mounted
after it is unreachable.
"""

from django.contrib import admin
from django.urls import path

from . import admin_views

app_name = "fga_inspector"

urlpatterns = [
    path(
        "tuples/",
        admin.site.admin_view(admin_views.TupleBrowserView.as_view()),
        name="tuples",
    ),
    path(
        "expand/",
        admin.site.admin_view(admin_views.ExpandView.as_view()),
        name="expand",
    ),
    path(
        "tree/",
        admin.site.admin_view(admin_views.ProjectTreeView.as_view()),
        name="tree",
    ),
]
