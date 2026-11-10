# -*- coding: utf-8 -*-
"""2026.19.011: el CDC pasa a los campos que declara local_py (>= 2026.19.017).

Si local_py todavía no está actualizado se corta con un mensaje claro, antes de que este
módulo quite sus propios campos y quede el CDC sin dónde guardarse."""
from odoo.exceptions import UserError


def migrate(cr, version):
    cr.execute("""
        SELECT count(*) FROM ir_model_fields
         WHERE model = 'account.move' AND name IN ('l10n_py_cdc', 'l10n_py_cdc_asociado')
    """)
    if cr.fetchone()[0] < 2:
        raise UserError(
            'FE_Py Recepción 2026.19.011 requiere local_py 2026.19.017 o posterior. '
            'Actualice local_py primero (o los dos módulos en la misma corrida).')
