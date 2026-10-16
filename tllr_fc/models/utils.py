# -*- coding: utf-8 -*-
"""Utilidades comunes de los modelos del taller."""


def escapar_ilike(valor):
    """Escapa los comodines de =ilike para comparar un texto exacto sin distinguir mayúsculas."""
    return (valor or '').replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
