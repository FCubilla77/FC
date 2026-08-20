# -*- coding: utf-8 -*-

from odoo import api, fields, models
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
    l10n_py_medio_importe = fields.Monetary(
        related='l10n_py_orden_pago_medio_id.importe', string='Importe del Medio',
        currency_field='currency_id',
        help='Importe real de la fila de Medios de origen (por ejemplo, el valor real '
             'del cheque) — puede ser mayor al de este Pago puntual si esa fila tuvo que '
             'repartirse entre varias facturas.',
    )
    l10n_py_es_saldo_favor = fields.Boolean(
        string='Es Saldo a Favor', default=False, copy=False,
        help='Se tilda solo en la porción de un Pago que quedó sin conciliar por sobrar '
             'entre Medios de Pago y Facturas (Orden de Pago con Saldo a Favor aprobado) '
             '— es lo que puede reutilizarse después en una Orden de Pago futura, como '
             'un Medio más.',
    )
    l10n_py_medios_saldo_favor_ids = fields.One2many(
        'local_py.orden_pago.medio', 'saldo_favor_payment_id', string='Usado como Saldo a Favor en',
        help='Filas de Medios (de otras Órdenes de Pago) que usaron este Pago como '
             'Saldo a Favor — si hay alguna, esta Orden no se puede Deshacer sin antes '
             'deshacer esas Órdenes más recientes primero.',
    )
    l10n_py_saldo_favor_disponible = fields.Monetary(
        string='Saldo a Favor Disponible', compute='_compute_l10n_py_saldo_favor_disponible', store=True,
        currency_field='currency_id',
        help='Importe de este Pago que todavía no fue aplicado a ninguna Factura ni '
             'usado en otra Orden de Pago — lo que realmente queda disponible para '
             'reutilizar como Saldo a Favor.',
    )

    @api.depends('move_id.line_ids.amount_residual', 'move_id.line_ids.account_id.account_type')
    def _compute_l10n_py_saldo_favor_disponible(self):
        for payment in self:
            linea = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable'
            )[:1]
            payment.l10n_py_saldo_favor_disponible = abs(linea.amount_residual) if linea else 0.0

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

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('l10n_py_allow_orden_pago_write'):
            config = self.env['local_py.configuracion_localizacion'].search(
                [('company_id', '=', self.env.company.id)], limit=1,
            )
            if config:
                for vals in vals_list:
                    if vals.get('l10n_py_orden_pago_id'):
                        # Viene de nuestra propia Orden de Pago — nunca se bloquea.
                        continue
                    partner_type = vals.get('partner_type')
                    if partner_type == 'supplier' and not config.l10n_py_pagos_proveedores_activo:
                        raise UserError(
                            'Los Pagos a Proveedores están desactivados (Configuraciones '
                            'Localización Py > Orden de Pago / Recibos) — hay que usar '
                            '"Orden de Pago" (Localización Paraguay) para que las Retenciones '
                            'no se omitan por error.'
                        )
                    if partner_type == 'customer' and not config.l10n_py_pagos_clientes_activo:
                        raise UserError(
                            'Los Pagos de Clientes están desactivados (Configuraciones '
                            'Localización Py > Orden de Pago / Recibos) — hay que usar '
                            '"Recibo Cliente" para que las Retenciones no se omitan por error.'
                        )
        return super().create(vals_list)

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
