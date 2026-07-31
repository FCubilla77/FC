# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class LocalPyOrdenPago(models.Model):
    _name = 'local_py.orden_pago'
    _description = 'Orden de Pago'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc, id desc'

    name = fields.Char(string='Número', default='Nuevo', copy=False, readonly=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company,
    )
    fecha = fields.Date(
        string='Fecha', required=True, default=fields.Date.context_today, tracking=True,
        readonly=True, states={'borrador': [('readonly', False)]},
    )
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', required=True,
        default=lambda self: self.env.company.currency_id,
        readonly=True, states={'borrador': [('readonly', False)]},
    )
    comentario = fields.Char(
        string='Comentario', readonly=True, states={'borrador': [('readonly', False)]},
    )
    partner_id = fields.Many2one(
        'res.partner', string='Proveedor', required=True, tracking=True,
        readonly=True, states={'borrador': [('readonly', False)]},
    )
    state = fields.Selection(
        [('borrador', 'Borrador'), ('en_proceso', 'En Proceso'), ('confirmado', 'Confirmado')],
        string='Estado', default='borrador', required=True, copy=False, tracking=True,
    )

    factura_ids = fields.One2many(
        'local_py.orden_pago.factura', 'orden_pago_id', string='Facturas',
        readonly=True, states={'borrador': [('readonly', False)]},
    )
    medio_ids = fields.One2many(
        'local_py.orden_pago.medio', 'orden_pago_id', string='Medios de Pago',
        readonly=True, states={'borrador': [('readonly', False)]},
    )

    total_facturas = fields.Monetary(
        string='Total a Pagar (Facturas)', compute='_compute_totales', currency_field='currency_id',
    )
    total_medios = fields.Monetary(
        string='Total Medios de Pago', compute='_compute_totales', currency_field='currency_id',
    )

    @api.depends('factura_ids.importe_a_pagar', 'medio_ids.importe')
    def _compute_totales(self):
        for orden in self:
            orden.total_facturas = sum(orden.factura_ids.mapped('importe_a_pagar'))
            orden.total_medios = sum(orden.medio_ids.mapped('importe'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('local_py.orden_pago') or 'Nuevo'
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Flujo de estados
    # ------------------------------------------------------------------
    def action_cargar_facturas_pendientes(self):
        """Trae todas las facturas/cuotas pendientes de pago del proveedor
        seleccionado, en la misma moneda de la cabecera (por ahora, el
        pago en varias monedas queda para una versión futura). No
        duplica las que ya estén cargadas."""
        self.ensure_one()
        if self.state != 'borrador':
            raise UserError('Solo se pueden cargar facturas mientras la Orden de Pago está en Borrador.')
        if not self.partner_id:
            raise UserError('Seleccione primero un Proveedor.')

        ya_cargadas = self.factura_ids.mapped('move_line_id')
        lineas = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id),
            ('partner_id', '=', self.partner_id.id),
            ('account_id.account_type', '=', 'liability_payable'),
            ('move_id.state', '=', 'posted'),
            ('reconciled', '=', False),
            ('currency_id', '=', self.currency_id.id),
            ('id', 'not in', ya_cargadas.ids),
        ])
        for linea in lineas:
            self.env['local_py.orden_pago.factura'].create({
                'orden_pago_id': self.id,
                'move_line_id': linea.id,
                'importe_a_pagar': abs(linea.amount_residual),
            })

    def action_marcar_en_proceso(self):
        for orden in self:
            if orden.state != 'borrador':
                raise UserError('Solo se puede marcar "En Proceso" una Orden de Pago en Borrador.')
            if not orden.factura_ids:
                raise UserError('Agregue al menos una factura/cuota a pagar antes de continuar.')
            if not orden.medio_ids:
                raise UserError('Agregue al menos un Medio de Pago antes de continuar.')
            if orden.currency_id.round(orden.total_facturas - orden.total_medios) != 0:
                raise UserError(
                    'El total de Medios de Pago (%s) debe coincidir exactamente con el total a '
                    'pagar de las Facturas seleccionadas (%s).'
                    % (orden.total_medios, orden.total_facturas)
                )
        self.write({'state': 'en_proceso'})

    def action_volver_borrador(self):
        for orden in self:
            if orden.state != 'en_proceso':
                raise UserError('Solo se puede volver a Borrador desde el estado "En Proceso".')
        self.write({'state': 'borrador'})

    def action_confirmar(self):
        for orden in self:
            if orden.state != 'en_proceso':
                raise UserError('Solo se puede Confirmar una Orden de Pago que esté "En Proceso".')
            orden._generar_pagos()
        self.write({'state': 'confirmado'})

    def action_deshacer_confirmacion(self):
        """Vuelve una Orden de Pago Confirmada a "En Proceso": deshace la
        conciliación contra las facturas y cancela/elimina los pagos
        generados. Se bloquea si algún pago ya fue conciliado con el
        extracto bancario (hay que deshacer esa conciliación a mano,
        primero, desde Contabilidad > Banco)."""
        for orden in self:
            if orden.state != 'confirmado':
                raise UserError('Solo se puede deshacer la confirmación de una Orden de Pago Confirmada.')
            pagos = orden.medio_ids.mapped('payment_id')
            lineas_pago = pagos.mapped('move_id.line_ids')
            if any(lineas_pago.mapped('statement_line_id')):
                raise UserError(
                    'Uno o más pagos de esta Orden de Pago ya están conciliados con el extracto '
                    'bancario. Deshaga esa conciliación manualmente en Contabilidad > Banco antes '
                    'de continuar.'
                )
            for pago in pagos:
                pago.move_id.line_ids.remove_move_reconcile()
                pago.with_context(l10n_py_allow_orden_pago_write=True).action_draft()
                pago.with_context(l10n_py_allow_orden_pago_write=True).unlink()
            orden.medio_ids.write({'payment_id': False})
        self.write({'state': 'en_proceso'})

    # ------------------------------------------------------------------
    # Generación de pagos
    # ------------------------------------------------------------------
    def _generar_pagos(self):
        self.ensure_one()
        AccountPayment = self.env['account.payment'].with_context(l10n_py_allow_orden_pago_write=True)
        lineas_a_conciliar = self.factura_ids.mapped('move_line_id')
        lineas_pagos_payable = self.env['account.move.line']

        for medio in self.medio_ids:
            comentario = 'Pago Orden de Pago %s' % self.name
            payment = AccountPayment.create({
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'partner_id': self.partner_id.id,
                'journal_id': medio.journal_id.id,
                'amount': medio.importe,
                'currency_id': self.currency_id.id,
                'date': self.fecha,
                'company_id': self.company_id.id,
                'memo': comentario,
                'l10n_py_orden_pago_id': self.id,
            })
            payment.action_post()
            if payment.move_id:
                payment.move_id.l10n_py_comentario = comentario
            medio.payment_id = payment.id

            lineas_pagos_payable |= payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable' and not l.reconciled
            )

        (lineas_a_conciliar + lineas_pagos_payable).reconcile()
