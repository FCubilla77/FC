# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    tllr_fc_ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT de taller", copy=False, readonly=True,
        index='btree_not_null', ondelete='restrict',
        help="Orden de trabajo de taller que originó este comprobante.")
    tllr_fc_tipo_asiento = fields.Selection([
        ('factura', "Costo de la OT al facturar"),
        ('entrega', "Costo de la OT al entregar"),
        ('cancelacion', "Pérdida por OT cancelada"),
        ('ajuste', "Ajuste de costo de la OT"),
    ], string="Asiento del taller", copy=False, readonly=True, index='btree_not_null')
    tllr_fc_origen_id = fields.Many2one(
        'account.move', string="Factura de origen (taller)", copy=False, readonly=True,
        ondelete='set null', help="Factura que originó este asiento del taller.")

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        for factura in posted.filtered(
                lambda m: m.move_type == 'out_invoice' and m.tllr_fc_ot_id):
            factura.tllr_fc_ot_id.sudo()._tllr_fc_asiento_factura(factura)
        return posted

    def button_draft(self):
        self._tllr_fc_revertir_asientos_de_factura()
        return super().button_draft()

    def button_cancel(self):
        self._tllr_fc_revertir_asientos_de_factura()
        return super().button_cancel()

    def _tllr_fc_revertir_asientos_de_factura(self):
        """Si una factura de OT confirmada vuelve a borrador o se cancela, se revierte su asiento."""
        for factura in self.filtered(
                lambda m: m.move_type == 'out_invoice' and m.tllr_fc_ot_id and m.state == 'posted'):
            factura.tllr_fc_ot_id.sudo()._tllr_fc_revertir_asientos(origen=factura)
