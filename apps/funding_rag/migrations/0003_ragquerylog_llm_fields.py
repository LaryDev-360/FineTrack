from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("funding_rag", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="ragquerylog",
            name="completion_tokens",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="ragquerylog",
            name="detected_language",
            field=models.CharField(blank=True, max_length=8),
        ),
        migrations.AddField(
            model_name="ragquerylog",
            name="language_fallback_reason",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="ragquerylog",
            name="model_used",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="ragquerylog",
            name="prompt_tokens",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
