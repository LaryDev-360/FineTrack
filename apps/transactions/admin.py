from django.contrib import admin

from .models import Transaction


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "transaction_type", "amount", "account", "date", "created_at")
    list_filter = ("transaction_type",)
    search_fields = ("note", "user__email")
    raw_id_fields = ("user", "account", "category", "to_account")
