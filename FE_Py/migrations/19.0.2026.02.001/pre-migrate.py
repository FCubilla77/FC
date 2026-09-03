# -*- coding: utf-8 -*-
"""Corrección de datos existentes: los Tipos Fiscales electrónicos que
FE_Py agregó/marcó en versiones anteriores quedaron con
`local_py_es_fisico = True` (el valor por defecto de local_py), porque
FE_Py no sabía que ese campo existía.

A partir de 2026.02.001 ambos campos deben ser siempre opuestos
(ver models/local_py_tipo_fiscal.py). Esta corrección se hace por SQL
directo porque:
  - post_init_hook solo corre en instalación nueva, no en upgrade.
  - El XML de datos tiene noupdate="1", así que tampoco se reaplica.

Efecto colateral importante que esto resuelve: el asistente "Documentos
Anulados" de local_py filtra por `local_py_es_fisico`, así que hasta
ahora estaba ofreciendo diarios electrónicos que no debía ofrecer.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Coherencia en ambos sentidos, por nombre de Tipo Fiscal:
    # electrónicos -> es_fisico = False
    cr.execute("""
        UPDATE local_py_tipo_fiscal
           SET local_py_es_fisico = FALSE
         WHERE fe_py_es_electronico = TRUE
           AND local_py_es_fisico IS DISTINCT FROM FALSE
    """)
    corregidos_electronicos = cr.rowcount

    # y los que no son electrónicos -> es_fisico = True (por si alguno
    # quedó en NULL/False sin ser electrónico, lo que también violaría
    # el constraint nuevo).
    cr.execute("""
        UPDATE local_py_tipo_fiscal
           SET local_py_es_fisico = TRUE
         WHERE (fe_py_es_electronico IS NULL OR fe_py_es_electronico = FALSE)
           AND local_py_es_fisico IS DISTINCT FROM TRUE
    """)
    corregidos_fisicos = cr.rowcount

    _logger.info(
        "FE_Py 2026.02.001: coherencia Es Electrónico / Es Físico — "
        "%s tipo(s) electrónico(s) y %s tipo(s) físico(s) corregidos.",
        corregidos_electronicos, corregidos_fisicos,
    )
