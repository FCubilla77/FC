# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    l10n_py_orden_pago_id = fields.Many2one(
        'local_py.orden_pago', string='Orden de Pago', readonly=True, copy=False,
        help='Si este pago fue generado por una Orden de Pago, no se puede modificar, '
             'restablecer a borrador ni eliminar directamente — solo a través de esa '
             'Orden de Pago, para no generar inconsistencias entre ambos.',
    )
    l10n_py_orden_pago_medio_id = fields.Many2one(
        'local_py.orden_pago.medio', string='Medio de Pago origen', readonly=True, copy=False,
        help='Fila de la pestaña Medios que generó este pago. Si esa fila tuvo que '
             'repartirse entre varias facturas, puede generar más de un pago (todos '
             'con el importe exacto que le corresponde a cada factura).',
    )

    def _l10n_py_check_orden_pago_lock(self):
        if self.env.context.get('l10n_py_allow_orden_pago_write'):
            return
        bloqueados = self.filtered('l10n_py_orden_pago_id')
        if bloqueados:
            raise UserError(
                'No se puede modificar, restablecer a borrador ni eliminar este pago '
                'directamente: proviene de la Orden de Pago %s. Hágalo desde esa Orden '
                'de Pago.' % ', '.join(bloqueados.mapped('l10n_py_orden_pago_id.name'))
            )

    def action_draft(self):
        self._l10n_py_check_orden_pago_lock()
        return super().action_draft()

    def write(self, vals):
        # Solo bloquea cambios "reales" hechos por un usuario común; nuestro propio
        # flujo de generación siempre usa el contexto de bypass o crea el registro
        # (no lo modifica después), así que este candado no le afecta.
        allowed_keys = {'l10n_py_orden_pago_id', 'l10n_py_orden_pago_medio_id'}
        if not self.env.context.get('l10n_py_allow_orden_pago_write') and set(vals.keys()) - allowed_keys:
            self._l10n_py_check_orden_pago_lock()
        return super().write(vals)

    def unlink(self):
        self._l10n_py_check_orden_pago_lock()
        return super().unlink()
