# -*- coding: utf-8 -*-
"""2026.19.011: copia el CDC guardado con los campos viejos de este módulo a los de local_py.

Es un resguardo: solo copia donde el campo nuevo está vacío y solo si las columnas viejas
existen. Las instalaciones son de prueba, así que normalmente no hay nada que copiar."""


def _existe_columna(cr, tabla, columna):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
         WHERE table_name = %s AND column_name = %s
    """, (tabla, columna))
    return bool(cr.fetchone())


def migrate(cr, version):
    for viejo, nuevo in (('fe_py_recepcion_cdc', 'l10n_py_cdc'),
                         ('fe_py_recepcion_cdc_asociado', 'l10n_py_cdc_asociado')):
        if _existe_columna(cr, 'account_move', viejo) and _existe_columna(cr, 'account_move', nuevo):
            cr.execute(
                'UPDATE account_move SET {nuevo} = {viejo} '
                'WHERE {viejo} IS NOT NULL AND {nuevo} IS NULL'.format(nuevo=nuevo, viejo=viejo))
