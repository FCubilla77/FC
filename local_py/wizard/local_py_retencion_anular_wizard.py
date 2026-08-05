# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class LocalPyRetencionAnularWizard(models.TransientModel):
    _name = 'local_py.retencion_anular.wizard'
    _description = 'Retención Anulada — Reprocesar o Anular Orden de Pago'

    retencion_ids = fields.Many2many('local_py.retencion_emitida', string='Retenciones a resolver')
    orden_pago_ids = fields.Many2many(
        'local_py.orden_pago', string='Órdenes de Pago afectadas', compute='_compute_orden_pago_ids',
    )
    accion = fields.Selection(
        [
            ('reprocesar', 'Reprocesar (volver a Pendiente, se incluye de nuevo en el próximo archivo JSON)'),
            ('anular_op', 'Anular la Orden de Pago completa'),
        ],
        string='¿Qué hacemos?', required=True, default='reprocesar',
    )

    @api.depends('retencion_ids')
    def _compute_orden_pago_ids(self):
        for wiz in self:
            wiz.orden_pago_ids = wiz.retencion_ids.mapped('orden_pago_id')

    def action_confirmar(self):
        self.ensure_one()
        if not self.retencion_ids:
            raise UserError('No hay ninguna Retención para resolver.')

        if self.accion == 'reprocesar':
            for retencion in self.retencion_ids:
                if retencion.estado not in ('levantada', 'anulada'):
                    raise UserError(
                        'Solo se puede Reprocesar una Retención que esté Levantada o Anulada.'
                    )
                retencion.write({
                    'estado': 'pendiente',
                    'numero_comprobante': False,
                    'fecha_anulacion': False,
                    'control': False,
                })
        else:
            for orden in self.orden_pago_ids:
                retenciones_op = self.env['local_py.retencion_emitida'].search([
                    ('orden_pago_id', '=', orden.id), ('tipo_retencion', '=', 'iva'),
                ])
                retenciones_op.filtered(lambda r: r.estado == 'levantada').write({
                    'estado': 'anulada',
                    'fecha_anulacion': fields.Date.context_today(self),
                })
                orden.with_context(l10n_py_forzar_anulacion_retenciones=True).action_deshacer_confirmacion()
        return {'type': 'ir.actions.act_window_close'}
