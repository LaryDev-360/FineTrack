from django.contrib import admin
from .models import PaymentIntent


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display = ("id", "merchant", "amount", "currency", "status", "expires_at", "created_at")
    list_filter = ("status", "currency")
