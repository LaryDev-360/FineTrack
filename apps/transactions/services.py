"""Effets sur les soldes des comptes lors des opérations sur Transaction."""

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.core.models import Account


def _lock_account(account_id):
    return Account.objects.select_for_update().get(pk=account_id)


@transaction.atomic
def apply_transaction_effect(tx):
    """
    Applique l'effet d'une transaction déjà enregistrée sur les soldes.
    À appeler dans un bloc transaction.atomic().
    """
    if tx.transaction_type == "expense":
        acc = _lock_account(tx.account_id)
        if acc.current_balance < tx.amount:
            raise serializers.ValidationError(
                {"amount": f"Solde insuffisant sur le compte (solde actuel : {acc.current_balance})."}
            )
        acc.current_balance -= tx.amount
        acc.save(update_fields=["current_balance", "updated_at"])
    elif tx.transaction_type == "income":
        acc = _lock_account(tx.account_id)
        acc.current_balance += tx.amount
        acc.save(update_fields=["current_balance", "updated_at"])
    elif tx.transaction_type == "transfer":
        if not tx.to_account_id:
            raise serializers.ValidationError({"to_account": "Le compte destination est obligatoire pour un transfert."})
        if tx.account_id == tx.to_account_id:
            raise serializers.ValidationError({"to_account": "Les comptes source et destination doivent être différents."})
        acc = _lock_account(tx.account_id)
        to_acc = _lock_account(tx.to_account_id)
        if acc.currency != to_acc.currency:
            raise serializers.ValidationError(
                {"to_account": "Les comptes doivent avoir la même devise pour un transfert."}
            )
        if acc.current_balance < tx.amount:
            raise serializers.ValidationError(
                {"amount": f"Solde insuffisant sur le compte source (solde actuel : {acc.current_balance})."}
            )
        acc.current_balance -= tx.amount
        to_acc.current_balance += tx.amount
        acc.save(update_fields=["current_balance", "updated_at"])
        to_acc.save(update_fields=["current_balance", "updated_at"])
    else:
        raise serializers.ValidationError({"transaction_type": "Type de transaction invalide."})


@transaction.atomic
def reverse_transaction_effect(tx):
    """Annule l'effet d'une transaction sur les soldes (avant suppression ou mise à jour)."""
    if tx.transaction_type == "expense":
        acc = _lock_account(tx.account_id)
        acc.current_balance += tx.amount
        acc.save(update_fields=["current_balance", "updated_at"])
    elif tx.transaction_type == "income":
        acc = _lock_account(tx.account_id)
        new_balance = acc.current_balance - tx.amount
        if new_balance < Decimal("0"):
            raise serializers.ValidationError(
                {"amount": "Impossible d'annuler cette transaction : le solde du compte deviendrait négatif."}
            )
        acc.current_balance = new_balance
        acc.save(update_fields=["current_balance", "updated_at"])
    elif tx.transaction_type == "transfer":
        acc = _lock_account(tx.account_id)
        to_acc = _lock_account(tx.to_account_id)
        if to_acc.current_balance < tx.amount:
            raise serializers.ValidationError(
                {"amount": "Impossible d'annuler ce transfert : solde insuffisant sur le compte destination."}
            )
        acc.current_balance += tx.amount
        to_acc.current_balance -= tx.amount
        acc.save(update_fields=["current_balance", "updated_at"])
        to_acc.save(update_fields=["current_balance", "updated_at"])
