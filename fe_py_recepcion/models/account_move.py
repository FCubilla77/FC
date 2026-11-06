# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    fe_py_recepcion_ids = fields.One2many(
        'fe_py_recepcion.documento', 'move_id', string='Factura electrónica recibida', copy=False)
    fe_py_recepcion_count = fields.Integer(compute='_compute_fe_py_recepcion_count')
    fe_py_recepcion_cdc = fields.Char(
        string='CDC del documento', size=44, copy=False, index=True,
        help='CDC (44 dígitos) que el proveedor informó en su documento electrónico. Se completa '
             'solo al generar la factura desde una recepción; en una factura cargada a mano se '
             'puede escribir. Solo se guarda: no se valida contra SIFEN.')
    fe_py_recepcion_cdc_asociado = fields.Char(
        string='CDC del documento asociado', size=44, copy=False, index=True,
        help='CDC de la factura que afecta esta nota de crédito, según el XML del proveedor.')

    @api.constrains('fe_py_recepcion_cdc', 'fe_py_recepcion_cdc_asociado')
    def _check_fe_py_recepcion_cdc(self):
        for move in self:
            for campo in ('fe_py_recepcion_cdc', 'fe_py_recepcion_cdc_asociado'):
                valor = move[campo]
                if valor and not (len(valor) == 44 and valor.isdigit()):
                    raise ValidationError(_(
                        '%s debe tener exactamente 44 dígitos.', move._fields[campo].string))

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

    def button_cancel(self):
        resultado = super().button_cancel()
        self.sudo().mapped('fe_py_recepcion_ids')._volver_a_cargado_por_factura()
        return resultado

    def unlink(self):
        recepciones = self.sudo().mapped('fe_py_recepcion_ids')
        resultado = super().unlink()
        recepciones.exists()._volver_a_cargado_por_factura()
        return resultado
