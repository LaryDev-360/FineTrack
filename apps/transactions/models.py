from django.conf import settings
from django.db import models

from apps.core.models import Account
from apps.categories.models import Category


class Transaction(models.Model):
    """Transaction : dépense, revenu ou transfert entre comptes."""

    TRANSACTION_TYPES = [
        ("expense", "Expense"),
        ("income", "Income"),
        ("transfer", "Transfer"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    to_account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="transfers_received",
    )
    date = models.DateTimeField()
    note = models.TextField(blank=True)
    is_synced = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "transactions_transaction"
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.get_transaction_type_display()} {self.amount} - {self.account.name}"
