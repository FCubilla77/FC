# -*- coding: utf-8 -*-
from odoo import fields, models


class FePyRecepcionDocumentoCuota(models.Model):
    """Cuota informada en el XML. Es solo de referencia: las cuotas y
    vencimientos de la factura los calcula Odoo con el término de pago."""
    _name = 'fe_py_recepcion.documento.cuota'
    _description = 'Cuota de Factura Electrónica Recibida'
    _order = 'documento_id, numero'

    documento_id = fields.Many2one('fe_py_recepcion.documento', string='Recepción', required=True,
                                   ondelete='cascade', index=True)
    currency_id = fields.Many2one(related='documento_id.currency_id')
    numero = fields.Integer(string='Cuota', readonly=True)
    monto = fields.Monetary(string='Monto', currency_field='currency_id', readonly=True)
    vencimiento = fields.Date(string='Vencimiento', readonly=True)
