from django.contrib import admin, messages
from unfold.admin import ModelAdmin

from .models import APIKey, User


@admin.register(User)
class UserAdmin(ModelAdmin):
    list_display = ("username", "email", "sub", "identity_provider", "is_staff")
    search_fields = ("username", "email", "sub")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not obj.sub:
            self.message_user(
                request,
                f"User “{obj.username}” has no IdP subject claim (sub). "
                "This account cannot be represented in OpenFGA and grants cannot "
                "be written for it. If this is a break-glass superuser, that is "
                "expected (ADR 0003). Otherwise, use ‘manage provision_user’ "
                "to set the sub from the IdP.",
                messages.WARNING,
            )


@admin.register(APIKey)
class APIKeyAdmin(ModelAdmin):
    list_display = ("name", "user", "prefix", "created_at", "last_used_at", "revoked")
    list_filter = ("revoked",)
    search_fields = ("name", "prefix", "user__username")
    readonly_fields = ("prefix", "hashed_key", "created_at", "last_used_at")
