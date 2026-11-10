# -*- coding: utf-8 -*-
"""2026.19.008: se quita de la ficha del proveedor el check «Confirmar Facturas Electrónicas
Recibidas sin Cotización». Se elimina su vista antes de que Odoo quite el campo, para que la
actualización no falle por una vista que referencia un campo que ya no existe."""
import logging

_logger = logging.getLogger(__name__)

XMLID = 'view_partner_form_fe_py_recepcion_purchase'
MODULO = 'fe_py_recepcion_purchase'


def migrate(cr, version):
    cr.execute(
        "SELECT res_id FROM ir_model_data WHERE module = %s AND name = %s AND model = 'ir.ui.view'",
        (MODULO, XMLID))
    fila = cr.fetchone()
    if not fila:
        return
    cr.execute("DELETE FROM ir_ui_view WHERE id = %s", (fila[0],))
    cr.execute("DELETE FROM ir_model_data WHERE module = %s AND name = %s", (MODULO, XMLID))
    _logger.info("FE_Py Recepción Compras: vista del check «sin cotización» eliminada.")
