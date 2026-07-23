from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import GrantAudit


@admin.register(GrantAudit)
class GrantAuditAdmin(ModelAdmin):
    list_display = ("created_at", "action", "subject", "relation", "object", "performed_by")
    list_filter = ("action", "relation")
    search_fields = ("subject", "object", "relation")
    readonly_fields = (
        "action",
        "subject",
        "relation",
        "object",
        "performed_by",
        "reason",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
