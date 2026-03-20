# Migration: contrainte d'unicité sur l'email du modèle User (auth_user).
# Garantit qu'aucun doublon d'email ne peut exister en base.
# En cas de doublons existants, la migration échouera ; résoudre les doublons avant de l'appliquer.

from django.db import migrations


def add_email_unique_index(apps, schema_editor):
    User = apps.get_model("auth", "User")
    table = User._meta.db_table
    index_name = f"{table}_email_unique"
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS %s ON %s (email)"
            % (schema_editor.connection.ops.quote_name(index_name), schema_editor.connection.ops.quote_name(table))
        )


def remove_email_unique_index(apps, schema_editor):
    User = apps.get_model("auth", "User")
    table = User._meta.db_table
    index_name = f"{table}_email_unique"
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "DROP INDEX IF EXISTS %s" % schema_editor.connection.ops.quote_name(index_name)
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_add_merchant_fields"),
    ]

    operations = [
        migrations.RunPython(add_email_unique_index, remove_email_unique_index),
    ]
