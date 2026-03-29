"""Utilitaires partagés pour les endpoints bulk-sync (offline → serveur)."""

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import serializers


def split_bulk_item(raw: dict, payload_fields: set):
    """
    Extrait id serveur, identifiants client, horodatage anti-conflit et payload métier.
    Seuls les champs présents dans `payload_fields` sont conservés dans le payload.
    """
    data = dict(raw)
    client_id = str(data.pop("client_id", "") or "")
    local_id = str(data.pop("local_id", "") or "")
    client_updated_at_raw = data.pop("client_updated_at", None)
    pk_raw = data.pop("id", None)
    pk = None
    if pk_raw is not None and pk_raw != "":
        try:
            pk = int(pk_raw)
        except (TypeError, ValueError):
            raise serializers.ValidationError({"id": "Identifiant serveur invalide."})
    payload = {k: v for k, v in data.items() if k in payload_fields}
    return pk, client_id, local_id, client_updated_at_raw, payload


def parse_client_updated_at(raw):
    """Parse `client_updated_at` (ISO 8601). Retourne un datetime aware ou lève ValidationError."""
    if raw is None or raw == "":
        return None
    dt = parse_datetime(str(raw))
    if dt is None:
        raise serializers.ValidationError(
            {
                "client_updated_at": "Format invalide. Utilisez une date/heure ISO 8601 (ex. 2026-03-29T14:00:00Z)."
            }
        )
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def validation_error_to_dict(exc: serializers.ValidationError):
    """Normalise une ValidationError DRF en dict { champ: [messages] }."""
    if hasattr(exc, "detail"):
        d = exc.detail
        if isinstance(d, list):
            return {"non_field_errors": [str(x) for x in d]}
        if isinstance(d, dict):
            out = {}
            for k, v in d.items():
                out[k] = [str(x) for x in v] if isinstance(v, list) else [str(v)]
            return out
    return {"detail": [str(exc)]}


def bulk_summary(results: list) -> dict:
    """Compte les statuts dans une liste de résultats bulk-sync."""
    counts = {"created": 0, "updated": 0, "error": 0, "conflict": 0}
    for r in results:
        s = r.get("status")
        if s in counts:
            counts[s] += 1
    return counts
