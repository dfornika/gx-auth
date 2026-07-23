from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import APIKey, User


@admin.register(User)
class UserAdmin(ModelAdmin):
    list_display = ("username", "email", "sub", "identity_provider", "is_staff")
    search_fields = ("username", "email", "sub")


@admin.register(APIKey)
class APIKeyAdmin(ModelAdmin):
    list_display = ("name", "user", "prefix", "created_at", "last_used_at", "revoked")
    list_filter = ("revoked",)
    search_fields = ("name", "prefix", "user__username")
    readonly_fields = ("prefix", "hashed_key", "created_at", "last_used_at")
