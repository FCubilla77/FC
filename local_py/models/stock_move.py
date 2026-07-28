# -*- coding: utf-8 -*-

from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    l10n_py_asiento_ajuste_id = fields.Many2one(
        'account.move', string='Asiento Ajuste Inventario', readonly=True, copy=False,
        help='Asiento contable generado automáticamente por el Ajuste de Inventario '
             'Físico que originó este movimiento (mismo asiento que figura en el '
             'registro de Inventario Físico correspondiente).',
    )


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    l10n_py_asiento_ajuste_id = fields.Many2one(
        related='move_id.l10n_py_asiento_ajuste_id',
        string='Asiento Ajuste Inventario', store=False,
    )
