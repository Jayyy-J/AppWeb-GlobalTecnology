#!/usr/bin/env python
"""Utilidad de línea de comandos de Django para GlobalTecnology."""
import os
import sys


def main():
    # En Railway se usa producción por defecto; en local, desarrollo.
    default = "config.settings.prod" if os.environ.get("RAILWAY_ENVIRONMENT") else "config.settings.dev"
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", default)
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
