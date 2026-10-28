"""Extensiones e índices de búsqueda (solo PostgreSQL; en SQLite no hace nada)."""
from django.contrib.postgres.operations import TrigramExtension, UnaccentExtension
from django.db import migrations

SQL_CREAR = [
    "CREATE INDEX IF NOT EXISTS catalog_product_search_vector_gin ON catalog_product USING gin (search_vector)",
    "CREATE INDEX IF NOT EXISTS catalog_product_nombre_trgm ON catalog_product USING gin (nombre gin_trgm_ops)",
    "CREATE INDEX IF NOT EXISTS catalog_product_search_text_trgm ON catalog_product USING gin (search_text gin_trgm_ops)",
]
SQL_BORRAR = [
    "DROP INDEX IF EXISTS catalog_product_search_vector_gin",
    "DROP INDEX IF EXISTS catalog_product_nombre_trgm",
    "DROP INDEX IF EXISTS catalog_product_search_text_trgm",
]


def crear(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for sql in SQL_CREAR:
        schema_editor.execute(sql)


def borrar(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for sql in SQL_BORRAR:
        schema_editor.execute(sql)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial")]
    operations = [
        TrigramExtension(),
        UnaccentExtension(),
        migrations.RunPython(crear, borrar),
    ]
