from django.contrib import admin

from .models import Budget


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "is_global", "category", "amount", "period_start", "period_end", "created_at")
    list_filter = ("is_global",)
    search_fields = ("user__email",)
    raw_id_fields = ("user", "category")
