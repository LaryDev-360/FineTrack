import uuid
from decimal import Decimal
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import Account


class PaymentIntent(models.Model):
    """Intent de paiement QR : le marchand crée un intent (montant, compte à créditer), le client confirme."""

    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_EXPIRED = "expired"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "En attente"),
        (STATUS_COMPLETED, "Complété"),
        (STATUS_EXPIRED, "Expiré"),
        (STATUS_CANCELLED, "Annulé"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payment_intents_as_merchant",
    )
    merchant_account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="payment_intents_received",
    )
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, default="XOF")
    reference = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "payments_payment_intent"
        ordering = ["-created_at"]

    def __str__(self):
        return f"PaymentIntent {self.id} {self.amount} {self.currency} ({self.status})"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_payable(self):
        return self.status == self.STATUS_PENDING and not self.is_expired
