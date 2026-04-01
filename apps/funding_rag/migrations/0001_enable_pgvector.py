from django.db import migrations


def create_pgvector_extension(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute("CREATE EXTENSION IF NOT EXISTS vector")


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.RunPython(
            create_pgvector_extension,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
