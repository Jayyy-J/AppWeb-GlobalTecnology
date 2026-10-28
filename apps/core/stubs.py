"""Vistas provisionales (Fase 1). Se reemplazan en las fases siguientes."""
from django.shortcuts import render


def proximamente(request, *args, **kwargs):
    return render(request, "proximamente.html")
