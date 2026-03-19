from django.conf import settings
from django.db import models


class Account(models.Model):
    """Compte / portefeuille (cash, banque, mobile money, épargne)."""

    ACCOUNT_TYPES = [
        ("cash", "Cash"),
        ("bank", "Bank Account"),
        ("mobile_money", "Mobile Money"),
        ("savings", "Savings"),
        ("other", "Other"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="accounts",
    )
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPES)
    initial_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    current_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default="XOF")
    color = models.CharField(max_length=7, default="#000000")
    icon = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "core_account"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_account_type_display()})"
