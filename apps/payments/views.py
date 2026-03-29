from django.utils import timezone
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import UserProfile
from apps.categories.models import Category
from apps.core.models import Account
from apps.transactions.models import Transaction

from .models import PaymentIntent
from .serializers import (
    MerchantMeResponseSerializer,
    PaymentConfirmResponseSerializer,
    PaymentConfirmSerializer,
    PaymentIntentCreateSerializer,
    PaymentIntentDetailSerializer,
    PaymentMerchantRecordSaleResponseSerializer,
    PaymentMerchantRecordSaleSerializer,
)


def is_professional(user):
    return hasattr(user, "profile") and user.profile.user_type == UserProfile.USER_TYPE_PROFESSIONAL


def get_or_create_payment_category(user, category_type):
    """
    Assure qu'une catégorie existe pour les opérations de paiement QR
    afin de toujours lier Transaction.category.
    """
    if category_type == "expense":
        name = "Paiements QR"
    else:
        name = "Ventes QR"

    category, _ = Category.objects.get_or_create(
        user=user,
        name=name,
        category_type=category_type,
        defaults={"color": "#4F46E5", "icon": "qr_code", "is_default": True},
    )
    return category


class MerchantMeView(APIView):
    """GET /api/merchant/me/ — Infos marchand (merchant_id, nom) pour le professionnel connecté."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=["Paiements QR"],
        summary="Profil marchand (QR statique)",
        responses={200: MerchantMeResponseSerializer},
    )
    def get(self, request):
        if not is_professional(request.user):
            return Response(
                {"detail": "Réservé aux comptes professionnels."},
                status=status.HTTP_403_FORBIDDEN,
            )
        profile = request.user.profile
        profile.ensure_merchant_id()
        payload_static = f"finetrack://pay/m/{profile.merchant_id}"
        return Response({
            "merchant_id": str(profile.merchant_id),
            "merchant_display_name": profile.merchant_display_name or request.user.email,
            "payload_for_qr_static": payload_static,
        })


class PaymentIntentCreateView(APIView):
    """POST /api/payments/intents/ — Créer un intent (montant, compte à créditer) pour afficher un QR dynamique."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=["Paiements QR"],
        summary="Créer un intent (QR dynamique)",
        request=PaymentIntentCreateSerializer,
        responses={201: PaymentIntentDetailSerializer},
    )
    def post(self, request):
        if not is_professional(request.user):
            return Response(
                {"detail": "Réservé aux comptes professionnels."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = PaymentIntentCreateSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        merchant_account = serializer.validated_data["_credited_account"]
        from datetime import timedelta
        expires_at = timezone.now() + timedelta(minutes=15)
        intent = PaymentIntent.objects.create(
            merchant=request.user,
            merchant_account=merchant_account,
            amount=serializer.validated_data["amount"],
            currency=serializer.validated_data.get("currency", "XOF"),
            reference=serializer.validated_data.get("reference", ""),
            expires_at=expires_at,
        )
        detail = PaymentIntentDetailSerializer(intent)
        return Response(detail.data, status=status.HTTP_201_CREATED)


class PaymentIntentDetailView(APIView):
    """GET /api/payments/intents/<uuid>/ — Détail d'un intent (pour le client qui a scanné le QR)."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=["Paiements QR"],
        summary="Détail intent (après scan)",
        responses={200: PaymentIntentDetailSerializer},
    )
    def get(self, request, intent_id):
        try:
            intent = PaymentIntent.objects.get(id=intent_id)
        except PaymentIntent.DoesNotExist:
            return Response({"detail": "Intent introuvable."}, status=status.HTTP_404_NOT_FOUND)
        if not intent.is_payable:
            if intent.is_expired:
                intent.status = PaymentIntent.STATUS_EXPIRED
                intent.save(update_fields=["status", "updated_at"])
            return Response(
                {"detail": "Ce paiement n'est plus disponible (expiré ou déjà traité)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = PaymentIntentDetailSerializer(intent)
        return Response(serializer.data)


class PaymentConfirmView(APIView):
    """POST /api/payments/confirm/ — Confirmer le paiement (débit client, crédit marchand)."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=["Paiements QR"],
        summary="Confirmer le paiement",
        request=PaymentConfirmSerializer,
        responses={200: PaymentConfirmResponseSerializer},
    )
    def post(self, request):
        serializer = PaymentConfirmSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        intent = serializer.validated_data["_intent"]
        payer_account = serializer.validated_data["_payer_account"]
        amount = intent.amount
        now = timezone.now()

        with transaction.atomic():
            intent.status = PaymentIntent.STATUS_COMPLETED
            intent.completed_at = now
            intent.save(update_fields=["status", "completed_at", "updated_at"])

            payer_account.current_balance -= amount
            payer_account.save(update_fields=["current_balance", "updated_at"])
            intent.merchant_account.current_balance += amount
            intent.merchant_account.save(update_fields=["current_balance", "updated_at"])

            payer_category = get_or_create_payment_category(request.user, "expense")
            merchant_category = get_or_create_payment_category(intent.merchant, "income")

            merchant_name = intent.merchant.profile.merchant_display_name or intent.merchant.email
            Transaction.objects.create(
                user=request.user,
                transaction_type=Transaction.TRANSACTION_TYPES[0][0],  # expense
                amount=amount,
                account=payer_account,
                category=payer_category,
                date=now,
                note=f"Paiement QR vers {merchant_name}" + (f" — {intent.reference}" if intent.reference else ""),
            )
            payer_name = request.user.email
            Transaction.objects.create(
                user=intent.merchant,
                transaction_type=Transaction.TRANSACTION_TYPES[1][0],  # income
                amount=amount,
                account=intent.merchant_account,
                category=merchant_category,
                date=now,
                note=f"Paiement QR reçu de {payer_name}" + (f" — {intent.reference}" if intent.reference else ""),
            )

        return Response({
            "detail": "Paiement effectué.",
            "payment_intent_id": str(intent.id),
            "amount": str(amount),
            "merchant_display_name": intent.merchant.profile.merchant_display_name or intent.merchant.email,
        }, status=status.HTTP_200_OK)


class MerchantRecordSaleView(APIView):
    """POST /api/payments/merchant/record-sale/ — Enregistrer une vente côté marchand (income uniquement)."""

    permission_classes = (IsAuthenticated,)

    @extend_schema(
        tags=["Paiements QR"],
        summary="Enregistrer une vente (marchand) - income only",
        request=PaymentMerchantRecordSaleSerializer,
        responses={200: PaymentMerchantRecordSaleResponseSerializer},
    )
    def post(self, request):
        serializer = PaymentMerchantRecordSaleSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        credited_account = serializer.validated_data["_credited_account"]
        amount = serializer.validated_data["amount"]
        currency = serializer.validated_data.get("currency", "XOF")
        reference = serializer.validated_data.get("reference", "")
        payment_method = serializer.validated_data["payment_method"]

        now = timezone.now()
        with transaction.atomic():
            credited_account.current_balance += amount
            credited_account.save(update_fields=["current_balance", "updated_at"])
            income_category = get_or_create_payment_category(request.user, "income")

            Transaction.objects.create(
                user=request.user,
                transaction_type=Transaction.TRANSACTION_TYPES[1][0],  # income
                amount=amount,
                account=credited_account,
                category=income_category,
                date=now,
                note=f"Vente ({payment_method})" + (f" — {reference}" if reference else ""),
            )

        return Response(
            {
                "detail": "Vente enregistrée.",
                "credited_account_id": credited_account.id,
                "amount": str(amount),
                "currency": currency,
                "payment_method": payment_method,
                "provider": serializer.validated_data.get("_wallet_provider"),
                "phone_number": serializer.validated_data.get("_wallet_phone_number"),
                "reference": reference,
            },
            status=status.HTTP_200_OK,
        )
