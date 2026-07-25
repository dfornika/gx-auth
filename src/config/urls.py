from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from health_check.views import HealthCheckView
from ninja import NinjaAPI

from accounts.api import BearerTokenAuth
from accounts.api import router as auth_router
from authz.api import router as authz_router
from config import __version__

api = NinjaAPI(
    title="gx-auth",
    version=__version__,
    description="Shared authorization control plane (Django Ninja + OpenFGA).",
    auth=BearerTokenAuth(),
)

api.add_router("/auth", auth_router)
api.add_router("/authz", authz_router)

urlpatterns = [
    # Must precede the admin: AdminSite.get_urls() ends in a catch-all that
    # matches every unclaimed admin/* path, so anything mounted after it is
    # unreachable. These are staff+superuser-gated read-only inspector pages.
    path(f"{settings.ADMIN_URL.rstrip('/')}/fga/", include("authz.admin_urls")),
    path(settings.ADMIN_URL, admin.site.urls),
    path("api/", api.urls),
    path("health/", HealthCheckView.as_view(), name="health"),
]

if settings.OIDC_ENABLED:
    urlpatterns += [path("oidc/", include("mozilla_django_oidc.urls"))]
