from django.conf import settings
from django.db import models

from apps.categories.models import Category


class Budget(models.Model):
    """Budget : global ou par catégorie, sur une période."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="budgets",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="budgets",
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    period_start = models.DateField()
    period_end = models.DateField()
    is_global = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "budgets_budget"
        ordering = ["-period_start"]

    def __str__(self):
        if self.is_global:
            return f"Budget global {self.amount} ({self.period_start} → {self.period_end})"
        return f"Budget {self.category.name} {self.amount} ({self.period_start} → {self.period_end})"
