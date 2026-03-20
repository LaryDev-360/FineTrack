from decimal import Decimal
from rest_framework import serializers

from apps.accounts.models import UserProfile
from apps.core.models import Account, MobileMoneyWallet
from .models import PaymentIntent


class PaymentIntentCreateSerializer(serializers.Serializer):
    """Création d'un intent par le marchand (pour afficher le QR dynamique)."""

    amount = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal("0.01"))
    currency = serializers.CharField(max_length=3, required=False, default="XOF")
    # Ancien mode : le marchand choisit directement l'Account à créditer.
    merchant_account_id = serializers.IntegerField(required=False, allow_null=True)
    # Nouveau mode : le marchand choisit provider + numéro, on mappe vers MobileMoneyWallet -> Account.
    provider = serializers.CharField(max_length=30, required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=30, required=False, allow_blank=True)
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")

    def validate_merchant_account_id(self, value):
        user = self.context["request"].user
        try:
            account = Account.objects.get(id=value, user=user)
        except Account.DoesNotExist:
            raise serializers.ValidationError("Compte introuvable ou non autorisé.")
        if not account.is_active:
            raise serializers.ValidationError("Ce compte n'est pas actif.")
        return value

    def validate(self, attrs):
        if not hasattr(self.context["request"].user, "profile"):
            raise serializers.ValidationError("Profil utilisateur introuvable.")
        profile = self.context["request"].user.profile
        if profile.user_type != UserProfile.USER_TYPE_PROFESSIONAL:
            raise serializers.ValidationError("Seuls les comptes professionnels peuvent créer un intent de paiement.")

        merchant_account_id = attrs.get("merchant_account_id")
        provider = (attrs.get("provider") or "").strip().upper()
        phone_number = (attrs.get("phone_number") or "").strip()

        if merchant_account_id:
            # Mode “ancien”, validation inchangée : account appartient au marchand + actif.
            account = self.validate_merchant_account_id(merchant_account_id)
            attrs["_credited_account"] = account
            return attrs

        if provider and phone_number:
            wallet = MobileMoneyWallet.objects.filter(
                user=self.context["request"].user,
                provider=provider,
                phone_number=phone_number,
            ).select_related("account").first()
            if not wallet:
                raise serializers.ValidationError(
                    {
                        "mobile_money_wallet": "Wallet introuvable pour provider+numéro. Créez-la d'abord via /api/accounts/mobile-money-wallets/ ou utilisez merchant_account_id."
                    }
                )
            attrs["_credited_account"] = wallet.account
            attrs["_wallet_provider"] = provider
            attrs["_wallet_phone_number"] = phone_number
            return attrs

        raise serializers.ValidationError(
            {"detail": "Fournissez soit merchant_account_id, soit (provider + phone_number)."}
        )


class PaymentIntentDetailSerializer(serializers.ModelSerializer):
    """Détail d'un intent (pour le client qui a scanné le QR)."""

    merchant_display_name = serializers.SerializerMethodField()
    payload_for_qr = serializers.SerializerMethodField()

    class Meta:
        model = PaymentIntent
        fields = (
            "id",
            "amount",
            "currency",
            "reference",
            "status",
            "expires_at",
            "merchant_display_name",
            "payload_for_qr",
        )

    def get_merchant_display_name(self, obj):
        if hasattr(obj.merchant, "profile") and obj.merchant.profile.merchant_display_name:
            return obj.merchant.profile.merchant_display_name
        return obj.merchant.email

    def get_payload_for_qr(self, obj):
        return f"finetrack://pay/d/{obj.id}"


class PaymentConfirmSerializer(serializers.Serializer):
    """Confirmation de paiement par le client (débit de son compte, crédit du marchand)."""

    payment_intent_id = serializers.UUIDField()
    payer_account_id = serializers.IntegerField()

    def validate_payer_account_id(self, value):
        user = self.context["request"].user
        try:
            account = Account.objects.get(id=value, user=user)
        except Account.DoesNotExist:
            raise serializers.ValidationError("Compte introuvable ou non autorisé.")
        if not account.is_active:
            raise serializers.ValidationError("Ce compte n'est pas actif.")
        return value

    def validate(self, attrs):
        from django.utils import timezone
        try:
            intent = PaymentIntent.objects.get(id=attrs["payment_intent_id"])
        except PaymentIntent.DoesNotExist:
            raise serializers.ValidationError({"payment_intent_id": "Intent introuvable."})
        if intent.status != PaymentIntent.STATUS_PENDING:
            raise serializers.ValidationError({"payment_intent_id": "Ce paiement a déjà été traité ou annulé."})
        if timezone.now() >= intent.expires_at:
            intent.status = PaymentIntent.STATUS_EXPIRED
            intent.save(update_fields=["status", "updated_at"])
            raise serializers.ValidationError({"payment_intent_id": "Ce paiement a expiré."})
        payer_account = Account.objects.get(id=attrs["payer_account_id"], user=self.context["request"].user)
        if payer_account.current_balance < intent.amount:
            raise serializers.ValidationError(
                {"payer_account_id": f"Solde insuffisant (solde actuel : {payer_account.current_balance})."}
            )
        if intent.merchant.id == self.context["request"].user.id:
            raise serializers.ValidationError({"payment_intent_id": "Vous ne pouvez pas vous payer vous-même."})
        attrs["_intent"] = intent
        attrs["_payer_account"] = payer_account
        return attrs


class PaymentMerchantRecordSaleSerializer(serializers.Serializer):
    """
    Enregistrement d'une vente côté marchand (client non nécessaire).
    MVP : on ne fait que l'income (crédit du compte marchand).
    """

    PAYMENT_METHOD_CASH = "cash"
    PAYMENT_METHOD_MOBILE_MONEY = "mobile_money"
    PAYMENT_METHOD_CHOICES = [
        (PAYMENT_METHOD_CASH, "Cash"),
        (PAYMENT_METHOD_MOBILE_MONEY, "Mobile Money"),
    ]

    payment_method = serializers.ChoiceField(choices=PAYMENT_METHOD_CHOICES)
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal("0.01"))
    currency = serializers.CharField(max_length=3, required=False, default="XOF")
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")

    # Cash
    merchant_account_id = serializers.IntegerField(required=False, allow_null=True)
    # Mobile Money
    provider = serializers.CharField(max_length=30, required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=30, required=False, allow_blank=True)

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user

        if not hasattr(user, "profile") or user.profile.user_type != UserProfile.USER_TYPE_PROFESSIONAL:
            raise serializers.ValidationError("Réservé aux comptes professionnels.")

        payment_method = attrs["payment_method"]

        if payment_method == self.PAYMENT_METHOD_CASH:
            merchant_account_id = attrs.get("merchant_account_id")
            if not merchant_account_id:
                raise serializers.ValidationError({"merchant_account_id": "Ce champ est obligatoire pour cash."})
            try:
                account = Account.objects.get(id=merchant_account_id, user=user, is_active=True)
            except Account.DoesNotExist:
                raise serializers.ValidationError({"merchant_account_id": "Compte introuvable ou non autorisé."})
            attrs["_credited_account"] = account
            return attrs

        if payment_method == self.PAYMENT_METHOD_MOBILE_MONEY:
            provider = (attrs.get("provider") or "").strip().upper()
            phone_number = (attrs.get("phone_number") or "").strip()
            if not provider:
                raise serializers.ValidationError({"provider": "Ce champ est obligatoire pour mobile_money."})
            if not phone_number:
                raise serializers.ValidationError({"phone_number": "Ce champ est obligatoire pour mobile_money."})

            wallet = MobileMoneyWallet.objects.filter(user=user, provider=provider, phone_number=phone_number).first()
            if not wallet:
                raise serializers.ValidationError({"mobile_money_wallet": "Wallet mobile money introuvable pour provider+numéro."})
            attrs["_credited_account"] = wallet.account
            attrs["_wallet_provider"] = provider
            attrs["_wallet_phone_number"] = phone_number
            return attrs

        # Sécurité : choix couvert par ChoiceField normalement
        raise serializers.ValidationError("payment_method invalide.")


class PaymentMerchantRecordSaleResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()
    credited_account_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    currency = serializers.CharField(max_length=3)
    payment_method = serializers.CharField()
    provider = serializers.CharField(required=False, allow_null=True)
    phone_number = serializers.CharField(required=False, allow_null=True)
    reference = serializers.CharField(required=False, allow_blank=True)
