# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    fe_py_recepcion_ids = fields.One2many(
        'fe_py_recepcion.documento', 'move_id', string='Factura electrónica recibida', copy=False)
    fe_py_recepcion_count = fields.Integer(compute='_compute_fe_py_recepcion_count')

    @api.depends('fe_py_recepcion_ids')
    def _compute_fe_py_recepcion_count(self):
        for move in self:
            move.fe_py_recepcion_count = len(move.fe_py_recepcion_ids)

    def action_ver_fe_py_recepcion(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'fe_py_recepcion.documento',
            'res_id': self.fe_py_recepcion_ids[:1].id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _post(self, soft=True):
        """Al publicarse la factura generada de una recepción (desde el proceso automático o a
        mano), el registro pasa de Borrador a Confirmado."""
        posted = super()._post(soft=soft)
        recepciones = posted.sudo().mapped('fe_py_recepcion_ids').filtered(
            lambda d: d.state == 'borrador')
        if recepciones:
            recepciones._marcar_confirmado(
                self.env.context.get('fe_py_recepcion_origen_publicacion', 'factura'),
                self.env.context.get('fe_py_recepcion_criterios'))
        return posted

    def button_draft(self):
        resultado = super().button_draft()
        self.sudo().mapped('fe_py_recepcion_ids')._volver_a_borrador_por_factura()
        return resultado

    def button_cancel(self):
        resultado = super().button_cancel()
        self.sudo().mapped('fe_py_recepcion_ids')._volver_a_cargado_por_factura()
        return resultado

    def unlink(self):
        recepciones = self.sudo().mapped('fe_py_recepcion_ids')
        resultado = super().unlink()
        recepciones.exists()._volver_a_cargado_por_factura()
        return resultado
