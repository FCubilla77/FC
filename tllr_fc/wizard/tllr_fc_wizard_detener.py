# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError


class TllrFcWizardDetener(models.TransientModel):
    """Marca la OT como detenida, con motivo y fecha estimada de reanudación."""
    _name = 'tllr_fc.wizard.detener'
    _description = "Detener la orden de trabajo"

    ot_id = fields.Many2one('tllr_fc.ot', string="OT", required=True, ondelete='cascade')
    motivo_id = fields.Many2one(
        'tllr_fc.motivo', string="Motivo", required=True,
        domain="[('tipo', '=', 'detencion')]")
    fecha_estimada = fields.Date(string="Reanudación estimada")

    def action_detener(self):
        self.ensure_one()
        if self.fecha_estimada and self.fecha_estimada < fields.Date.context_today(self):
            raise UserError("La fecha estimada de reanudación no puede ser anterior a hoy.")
        self.ot_id._tllr_fc_detener(self.motivo_id, self.fecha_estimada)
        return {'type': 'ir.actions.act_window_close'}
