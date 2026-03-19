from django.conf import settings
from django.db import models


class Category(models.Model):
    """Catégorie de transaction (dépense ou revenu)."""

    CATEGORY_TYPES = [
        ("expense", "Expense"),
        ("income", "Income"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    name = models.CharField(max_length=100)
    category_type = models.CharField(max_length=10, choices=CATEGORY_TYPES)
    color = models.CharField(max_length=7, default="#000000")
    icon = models.CharField(max_length=50, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "categories_category"
        ordering = ["category_type", "name"]
        verbose_name_plural = "Categories"

    def __str__(self):
        return f"{self.name} ({self.get_category_type_display()})"
