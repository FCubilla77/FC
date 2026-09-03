# -*- coding: utf-8 -*-

from odoo import api, fields, models


class FePyCuota(models.Model):
    _name = 'fe_py.cuota'
    _description = 'Cuota de Venta a Crédito (SIFEN)'
    _order = 'fecha_vencimiento, id'

    move_id = fields.Many2one(
        'account.move', string='Comprobante', required=True,
        ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(related='move_id.company_id', store=True)
    currency_id = fields.Many2one(
        related='move_id.currency_id', string='Moneda', store=True, readonly=True,
    )
    monto = fields.Monetary(string='Monto de la Cuota', required=True)
    fecha_vencimiento = fields.Date(string='Vencimiento')

    @api.depends('monto', 'fecha_vencimiento')
    def _compute_display_name(self):
        for cuota in self:
            if cuota.fecha_vencimiento:
                cuota.display_name = '%s - %s' % (cuota.fecha_vencimiento, cuota.monto)
            else:
                cuota.display_name = str(cuota.monto)
