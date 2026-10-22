# -*- coding: utf-8 -*-
from odoo import fields, models


class TllrFcSaleWizardVencido(models.TransientModel):
    _name = 'tllr_fc_sale.wizard.vencido'
    _description = "Confirmar presupuesto vencido"

    order_id = fields.Many2one('sale.order', string="Presupuesto", required=True)
    mensaje = fields.Text(string="Aviso", readonly=True)

    def action_continuar(self):
        self.ensure_one()
        return self.order_id.with_context(tllr_fc_vencido_ok=True).action_confirm()
