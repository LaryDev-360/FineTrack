import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import pgvector.django.vector


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("funding_rag", "0001_enable_pgvector"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FundingDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=255)),
                ("source_url", models.URLField(blank=True)),
                ("source_type", models.CharField(choices=[("grant", "Subvention"), ("loan", "Pret"), ("program", "Programme"), ("other", "Autre")], default="other", max_length=20)),
                ("language", models.CharField(db_index=True, default="fr", max_length=8)),
                ("country", models.CharField(db_index=True, default="BJ", max_length=50)),
                ("status", models.CharField(choices=[("draft", "Brouillon"), ("published", "Publie"), ("archived", "Archive")], db_index=True, default="draft", max_length=20)),
                ("version", models.PositiveIntegerField(default=1)),
                ("published_at", models.DateField(blank=True, db_index=True, null=True)),
                ("raw_content", models.TextField()),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "funding_rag_document",
                "ordering": ["-updated_at"],
            },
        ),
        migrations.CreateModel(
            name="IngestionJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_label", models.CharField(blank=True, max_length=255)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("running", "Running"), ("success", "Success"), ("failed", "Failed")], db_index=True, default="pending", max_length=20)),
                ("total_documents", models.PositiveIntegerField(default=0)),
                ("total_chunks", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="funding_ingestion_jobs", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "funding_rag_ingestion_job",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="RagQueryLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("question", models.TextField()),
                ("normalized_question", models.TextField(blank=True)),
                ("response_text", models.TextField(blank=True)),
                ("selected_chunks", models.JSONField(blank=True, default=list)),
                ("provider", models.CharField(default="local-hash", max_length=50)),
                ("latency_ms", models.PositiveIntegerField(default=0)),
                ("estimated_cost_usd", models.DecimalField(decimal_places=6, default=0, max_digits=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="funding_rag_queries", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "funding_rag_query_log",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="FundingChunk",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("chunk_index", models.PositiveIntegerField()),
                ("content", models.TextField()),
                ("embedding", pgvector.django.vector.VectorField(dimensions=128)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("document", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="chunks", to="funding_rag.fundingdocument")),
            ],
            options={
                "db_table": "funding_rag_chunk",
                "ordering": ["document_id", "chunk_index"],
                "constraints": [models.UniqueConstraint(fields=("document", "chunk_index"), name="uniq_funding_chunk_doc_index")],
            },
        ),
    ]
