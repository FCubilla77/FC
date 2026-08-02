# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class LocalPyOrdenPago(models.Model):
    _name = 'local_py.orden_pago'
    _description = 'Orden de Pago'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc, id desc'

    name = fields.Char(string='Número', default='Nuevo', copy=False, readonly=True)
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company,
    )
    fecha = fields.Date(
        string='Fecha', required=True, default=fields.Date.context_today, tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', required=True,
        default=lambda self: self.env.company.currency_id,
    )
    comentario = fields.Char(
        string='Comentario',
    )
    partner_id = fields.Many2one(
        'res.partner', string='Proveedor', required=True, tracking=True,
    )
    fecha_en_proceso = fields.Datetime(string='Fecha En Proceso', readonly=True, copy=False)
    fecha_confirmacion = fields.Datetime(string='Fecha Confirmación', readonly=True, copy=False)
    state = fields.Selection(
        [('borrador', 'Borrador'), ('en_proceso', 'En Proceso'), ('confirmado', 'Confirmado')],
        string='Estado', default='borrador', required=True, copy=False, tracking=True,
    )

    factura_ids = fields.One2many(
        'local_py.orden_pago.factura', 'orden_pago_id', string='Facturas',
    )
    medio_ids = fields.One2many(
        'local_py.orden_pago.medio', 'orden_pago_id', string='Medios de Pago',
    )

    total_facturas = fields.Monetary(
        string='Total a Pagar (Facturas)', compute='_compute_totales', currency_field='currency_id',
    )
    total_medios = fields.Monetary(
        string='Total Medios de Pago', compute='_compute_totales', currency_field='currency_id',
    )
    diferencia = fields.Monetary(
        string='Diferencia', compute='_compute_totales', currency_field='currency_id',
        help='Total a Pagar (Facturas) menos Total Medios de Pago. Tiene que quedar en '
             'cero antes de poder pasar a "En Proceso".',
    )
    hay_monedas_distintas = fields.Boolean(compute='_compute_totales')

    @api.depends('factura_ids.valor_convertido', 'factura_ids.currency_id', 'medio_ids.importe', 'currency_id')
    def _compute_totales(self):
        for orden in self:
            orden.total_facturas = sum(orden.factura_ids.mapped('valor_convertido'))
            orden.total_medios = sum(orden.medio_ids.mapped('importe'))
            orden.diferencia = orden.total_facturas - orden.total_medios
            orden.hay_monedas_distintas = bool(
                orden.factura_ids.filtered(lambda f: f.currency_id != orden.currency_id)
            )

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.factura_ids:
            self.factura_ids = [(5, 0, 0)]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('local_py.orden_pago') or 'Nuevo'
        return super().create(vals_list)

    def unlink(self):
        raise UserError(
            'No se puede eliminar una Orden de Pago (para no dejar huecos en la '
            'numeración). Use "Archivar" en su lugar — el registro queda oculto de las '
            'vistas normales, pero el historial se conserva.'
        )

    # ------------------------------------------------------------------
    # Flujo de estados
    # ------------------------------------------------------------------
    def _verificar_cotizaciones_cargadas(self, monedas):
        """Bloquea si falta la cotización exacta del día para alguna
        moneda — para no usar en silencio la última cotización cargada,
        que puede no ser la del día."""
        self.ensure_one()
        monedas_a_convertir = monedas - self.currency_id
        monedas_sin_cotizacion = self.env['res.currency']
        for moneda in monedas_a_convertir:
            existe = self.env['res.currency.rate'].search_count([
                ('currency_id', '=', moneda.id),
                ('company_id', 'in', (self.company_id.id, False)),
                ('name', '=', self.fecha),
            ])
            if not existe:
                monedas_sin_cotizacion |= moneda
        if monedas_sin_cotizacion:
            raise UserError(
                'Falta cargar la cotización del %s para: %s. Cárguela en Ajustes > '
                'Contabilidad > Monedas antes de continuar — de lo contrario se usaría la '
                'última cotización cargada, que puede no ser la del día.'
                % (self.fecha.strftime('%d/%m/%Y'), ', '.join(monedas_sin_cotizacion.mapped('name')))
            )

    def action_cargar_facturas_pendientes(self):
        """Trae todas las facturas/cuotas pendientes de pago del proveedor
        seleccionado, en CUALQUIER moneda — cada una conserva su propia
        moneda y su propia Cotización contra la Moneda de la Cabecera. No
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
            ('id', 'not in', ya_cargadas.ids),
        ])

        self._verificar_cotizaciones_cargadas(lineas.mapped('currency_id'))

        nuevas = self.env['local_py.orden_pago.factura']
        for linea in lineas:
            importe = abs(linea.amount_residual_currency) if linea.currency_id else abs(linea.amount_residual)
            nuevas |= self.env['local_py.orden_pago.factura'].create({
                'orden_pago_id': self.id,
                'move_line_id': linea.id,
                'importe_a_pagar': importe,
            })
        nuevas._set_cotizacion_default(self.fecha)

    def action_marcar_en_proceso(self):
        for orden in self:
            if orden.state != 'borrador':
                raise UserError('Solo se puede marcar "En Proceso" una Orden de Pago en Borrador.')
            if not orden.factura_ids:
                raise UserError('Agregue al menos una factura/cuota a pagar antes de continuar.')
            if not orden.medio_ids:
                raise UserError('Agregue al menos un Medio de Pago antes de continuar.')
            orden.medio_ids._resolver_chequera()
            if orden.currency_id.round(orden.total_facturas - orden.total_medios) != 0:
                raise UserError(
                    'El total de Medios de Pago (%s) debe coincidir exactamente con el total a '
                    'pagar de las Facturas seleccionadas (%s).'
                    % (orden.total_medios, orden.total_facturas)
                )
        self.write({'state': 'en_proceso', 'fecha_en_proceso': fields.Datetime.now()})

    def action_volver_borrador(self):
        for orden in self:
            if orden.state != 'en_proceso':
                raise UserError('Solo se puede volver a Borrador desde el estado "En Proceso".')
        self.write({'state': 'borrador', 'fecha_en_proceso': False})

    def action_confirmar(self):
        for orden in self:
            if orden.state != 'en_proceso':
                raise UserError('Solo se puede Confirmar una Orden de Pago que esté "En Proceso".')
            orden.medio_ids._resolver_chequera()
            a_refrescar = orden.factura_ids.filtered(lambda f: not f.cotizacion_manual)
            orden._verificar_cotizaciones_cargadas(a_refrescar.mapped('currency_id'))
            a_refrescar._set_cotizacion_default(orden.fecha)
            if orden.currency_id.round(orden.total_facturas - orden.total_medios) != 0:
                raise UserError(
                    'La cotización cambió y el cuadre entre Facturas y Medios de Pago ya no '
                    'coincide (Facturas: %s, Medios: %s). Revise los importes antes de volver '
                    'a Confirmar.' % (orden.total_facturas, orden.total_medios)
                )
            orden._generar_pagos()
        self.write({'state': 'confirmado', 'fecha_confirmacion': fields.Datetime.now()})

    def action_deshacer_confirmacion(self):
        """Vuelve una Orden de Pago Confirmada a "En Proceso": deshace la
        conciliación contra las facturas y cancela/elimina los pagos
        generados. Se bloquea si algún pago ya fue conciliado con el
        extracto bancario (hay que deshacer esa conciliación a mano,
        primero, desde Contabilidad > Banco). Si alguno de los Medios ya
        tenía su cheque impreso, se pregunta primero si ese número se
        reutiliza (queda disponible para otra Orden de Pago) o se anula
        (se registra como cheque anulado)."""
        self.ensure_one()
        if self.state != 'confirmado':
            raise UserError('Solo se puede deshacer la confirmación de una Orden de Pago Confirmada.')
        pagos = self.medio_ids.mapped('payment_ids')
        lineas_pago = pagos.mapped('move_id.line_ids')
        if any(lineas_pago.mapped('statement_line_id')):
            raise UserError(
                'Uno o más pagos de esta Orden de Pago ya están conciliados con el extracto '
                'bancario. Deshaga esa conciliación manualmente en Contabilidad > Banco antes '
                'de continuar.'
            )
        cheques_emitidos = self.env['local_py.chequera.cheque'].search([
            ('payment_id', 'in', pagos.ids), ('estado', '=', 'emitido'),
        ])
        if cheques_emitidos:
            return {
                'name': 'Cheques ya impresos',
                'type': 'ir.actions.act_window',
                'res_model': 'local_py.orden_pago.deshacer_wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_orden_pago_id': self.id,
                    'default_cheque_ids': [(6, 0, cheques_emitidos.ids)],
                },
            }
        self._deshacer_confirmacion_efectivo()

    def _deshacer_confirmacion_efectivo(self):
        pagos = self.medio_ids.mapped('payment_ids')
        for pago in pagos:
            pago.move_id.line_ids.remove_move_reconcile()
            pago.with_context(l10n_py_allow_orden_pago_write=True).action_draft()
            pago.with_context(l10n_py_allow_orden_pago_write=True).unlink()
        self.write({'state': 'en_proceso', 'fecha_confirmacion': False})

    # ------------------------------------------------------------------
    # Generación de pagos
    # ------------------------------------------------------------------
    def _generar_pagos(self):
        """Genera los pagos y los concilia contra las Facturas/Cuotas
        seleccionadas.

        IMPORTANTE: no se hace un solo reconcile() masivo mezclando todas
        las Facturas con todos los Medios — Odoo no reparte ese cruce de
        forma proporcional, aplica el importe que puede a lo primero que
        encuentra y puede dejar facturas sin cobertura (bug detectado en
        pruebas reales). En cambio, se arma primero un plan de asignación
        exacto (qué porción de cada Medio le corresponde a cada Factura,
        en la moneda de la cabecera) y se genera un pago por cada porción,
        conciliado siempre 1 a 1 contra su factura específica — así el
        importe que Odoo aplica en cada conciliación es exactamente el
        que corresponde, sin ambigüedad, y el mecanismo nativo de
        diferencia de cambio se dispara igual de bien caso por caso."""
        self.ensure_one()
        AccountPayment = self.env['account.payment'].with_context(l10n_py_allow_orden_pago_write=True)
        currency = self.currency_id

        facturas_pend = [[f, f.valor_convertido] for f in self.factura_ids]
        medios_pend = [[m, m.importe] for m in self.medio_ids]
        asignaciones = []

        i = j = 0
        while i < len(facturas_pend) and j < len(medios_pend):
            factura, monto_f = facturas_pend[i]
            medio, monto_m = medios_pend[j]
            monto = min(monto_f, monto_m)
            if currency.compare_amounts(monto, 0) > 0:
                asignaciones.append((factura, medio, monto))
            facturas_pend[i][1] -= monto
            medios_pend[j][1] -= monto
            if currency.is_zero(facturas_pend[i][1]):
                i += 1
            if currency.is_zero(medios_pend[j][1]):
                j += 1

        if i < len(facturas_pend) or j < len(medios_pend):
            raise UserError(
                'No se pudo repartir exactamente el importe de los Medios de Pago contra '
                'las Facturas/Cuotas seleccionadas. Revise los importes antes de continuar.'
            )

        for factura, medio, monto in asignaciones:
            comentario = 'Pago Orden de Pago %s' % self.name
            payment = AccountPayment.create({
                'payment_type': 'outbound',
                'partner_type': 'supplier',
                'partner_id': self.partner_id.id,
                'journal_id': medio.journal_id.id,
                'amount': monto,
                'currency_id': self.currency_id.id,
                'date': self.fecha,
                'company_id': self.company_id.id,
                'memo': comentario,
                'l10n_py_orden_pago_id': self.id,
                'l10n_py_orden_pago_medio_id': medio.id,
            })
            payment.action_post()
            if payment.move_id:
                payment.move_id.l10n_py_comentario = comentario

            if medio.cheque_reutilizar_id:
                cheque = medio.cheque_reutilizar_id
                if cheque.estado != 'reutilizable':
                    raise UserError(
                        'El cheque N° %s ya no está en estado "Reutilizable" — revise la '
                        'fila de Medios.' % cheque.numero
                    )
                cheque.write({
                    'estado': 'emitido',
                    'fecha_emision': payment.date,
                    'payment_id': payment.id,
                    'orden_pago_medio_id': medio.id,
                    'motivo_anulacion': False,
                })
                medio.write({'cheque_reutilizar_id': False, 'nro_documento': str(cheque.numero)})

            linea_pago_payable = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable' and not l.reconciled
            )
            (factura.move_line_id + linea_pago_payable).reconcile()
