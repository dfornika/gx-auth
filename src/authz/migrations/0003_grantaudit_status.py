from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("authz", "0002_grantaudit_on_behalf_of"),
    ]

    operations = [
        # Every existing row was written after (or in the same transaction as)
        # its engine write, so it is `applied`. New rows start `pending`.
        migrations.AddField(
            model_name="grantaudit",
            name="status",
            field=models.CharField(
                choices=[("pending", "pending"), ("applied", "applied"), ("failed", "failed")],
                db_index=True,
                default="applied",
                max_length=8,
            ),
        ),
        migrations.AlterField(
            model_name="grantaudit",
            name="status",
            field=models.CharField(
                choices=[("pending", "pending"), ("applied", "applied"), ("failed", "failed")],
                db_index=True,
                default="pending",
                max_length=8,
            ),
        ),
    ]
