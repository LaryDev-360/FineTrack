"""Schémas OpenAPI pour la comptabilité et les bilans."""

from rest_framework import serializers


class ActivityDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    nombre_transactions = serializers.IntegerField()


class AccountingPeriodDetailsSerializer(serializers.Serializer):
    """Champs optionnels selon la granularité (voir description de l’endpoint)."""

    volume_transactions = serializers.IntegerField(required=False)
    jours_forte_activite = ActivityDaySerializer(many=True, required=False)
    croissance_vs_periode_precedente_pct = serializers.FloatField(required=False, allow_null=True)
    chiffre_affaires_periode_precedente = serializers.DecimalField(
        max_digits=20, decimal_places=2, required=False
    )
    moyenne_mensuelle_chiffre_affaires = serializers.DecimalField(
        max_digits=20, decimal_places=2, required=False
    )
    evolution_vs_annee_precedente_pct = serializers.FloatField(required=False, allow_null=True)


class AccountingPeriodResponseSerializer(serializers.Serializer):
    granularity = serializers.CharField()
    reference_date = serializers.DateField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    chiffre_affaires = serializers.DecimalField(max_digits=20, decimal_places=2)
    depenses = serializers.DecimalField(max_digits=20, decimal_places=2)
    resultat_net = serializers.DecimalField(max_digits=20, decimal_places=2)
    nombre_transactions = serializers.IntegerField()
    details = AccountingPeriodDetailsSerializer(required=False)


class BilanRowSerializer(serializers.Serializer):
    label = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    chiffre_affaires = serializers.DecimalField(max_digits=20, decimal_places=2)
    depenses = serializers.DecimalField(max_digits=20, decimal_places=2)
    resultat_net = serializers.DecimalField(max_digits=20, decimal_places=2)
    nombre_transactions = serializers.IntegerField()


class AccountingBilansResponseSerializer(serializers.Serializer):
    granularity = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    periods = BilanRowSerializer(many=True)


class AccountingKPIsResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    nombre_transactions = serializers.IntegerField()
    ticket_moyen_revenus = serializers.DecimalField(
        max_digits=20, decimal_places=2, required=False, allow_null=True
    )
    taux_croissance_chiffre_affaires_pct = serializers.FloatField(allow_null=True)
    variabilite_revenus_coefficient = serializers.FloatField(allow_null=True)
    chiffre_affaires_total = serializers.DecimalField(max_digits=20, decimal_places=2)
    chiffre_affaires_periode_precedente = serializers.DecimalField(max_digits=20, decimal_places=2)
