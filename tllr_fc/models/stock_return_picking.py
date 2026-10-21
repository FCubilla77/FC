# -*- coding: utf-8 -*-
from odoo import models
from odoo.exceptions import UserError


class StockReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    def _tllr_fc_verificar_no_es_de_ot(self):
        for asistente in self.sudo():
            if asistente.picking_id.tllr_fc_ot_id:
                raise UserError(
                    "El traslado %s pertenece a la OT %s: la devolución se genera desde el "
                    "módulo de Taller (al terminar el puesto o con «Devolver consumo»)." % (
                        asistente.picking_id.name, asistente.picking_id.tllr_fc_ot_id.name))

    def action_create_returns(self):
        self._tllr_fc_verificar_no_es_de_ot()
        return super().action_create_returns()

    def action_create_returns_all(self):
        self._tllr_fc_verificar_no_es_de_ot()
        return super().action_create_returns_all()
