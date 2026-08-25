# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class LocalPyRecibo(models.Model):
    _name = 'local_py.recibo'
    _description = 'Recibo'
    _order = 'id desc'

    name = fields.Char(string='Recibo', default='Nuevo', copy=False, readonly=True)
    serie_id = fields.Many2one(
        'local_py.recibo.serie', string='Serie', required=True, readonly="state != 'borrador'",
        domain="[('user_id', '=', uid), ('company_id', '=', company_id)]",
        help='Solo aparecen las Series asignadas a su Usuario, para la Compañía activa.',
    )
    numero = fields.Integer(string='Número', readonly=True, copy=False)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company,
    )
    partner_id = fields.Many2one(
        'res.partner', string='Cliente', required=True, readonly="state != 'borrador'",
        domain="[('customer_rank', '>', 0)]",
    )
    fecha = fields.Date(string='Fecha', required=True, default=fields.Date.context_today, readonly="state != 'borrador'")
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', required=True, readonly="state != 'borrador'",
        default=lambda self: self.env.company.currency_id,
    )
    comentario = fields.Char(string='Comentario')

    factura_ids = fields.One2many('local_py.recibo.factura', 'recibo_id', string='Facturas')
    medio_ids = fields.One2many('local_py.recibo.medio', 'recibo_id', string='Medios de Cobro')

    state = fields.Selection(
        [
            ('borrador', 'Borrador'),
            ('en_proceso', 'En Proceso'),
            ('confirmado', 'Confirmado'),
            ('anulado', 'Anulado'),
        ],
        string='Estado', default='borrador', required=True, copy=False, tracking=True,
    )
    fecha_en_proceso = fields.Datetime(string='Fecha En Proceso', readonly=True, copy=False)
    fecha_confirmacion = fields.Datetime(string='Fecha de Confirmación', readonly=True, copy=False)
    fecha_anulacion = fields.Datetime(string='Fecha de Anulación', readonly=True, copy=False)
    permite_saldo_a_favor = fields.Boolean(
        string='Permite Saldo a Favor', copy=False,
        help='Se tilda solo desde el wizard que aparece al detectar un sobrante entre '
             'Medios de Cobro y Facturas — habilita que ese excedente quede sin '
             'conciliar (Saldo a Favor del Cliente) en vez de bloquear el Recibo.',
    )

    total_facturas = fields.Monetary(string='Total a Cobrar (Facturas)', compute='_compute_totales', currency_field='currency_id')
    total_medios = fields.Monetary(string='Total Medios de Cobro', compute='_compute_totales', currency_field='currency_id')
    diferencia = fields.Monetary(
        string='Diferencia', compute='_compute_totales', currency_field='currency_id',
        help='Total a Cobrar (Facturas) menos Total Medios de Cobro. No puede quedar '
             'en negativo (faltaría plata) para poder pasar a "En Proceso" — si queda '
             'en positivo (sobra), el sistema pregunta si corregir los importes o '
             'dejarlo como Saldo a Favor del Cliente.',
    )
    hay_monedas_distintas = fields.Boolean(compute='_compute_totales')

    @api.depends('factura_ids.valor_convertido', 'factura_ids.currency_id', 'medio_ids.importe', 'currency_id')
    def _compute_totales(self):
        for recibo in self:
            recibo.total_facturas = sum(recibo.factura_ids.mapped('valor_convertido'))
            recibo.total_medios = sum(recibo.medio_ids.mapped('importe'))
            recibo.hay_monedas_distintas = bool(
                recibo.factura_ids.filtered(lambda f: f.currency_id != recibo.currency_id)
            )
            recibo.diferencia = recibo.total_facturas - recibo.total_medios

    def _fmt(self, valor):
        self.ensure_one()
        decimales = self.currency_id.decimal_places if self.currency_id else 0
        texto = '{:,.{prec}f}'.format(valor or 0.0, prec=decimales)
        entero, sep, decimal = texto.partition('.')
        entero = entero.replace(',', '.')
        return entero + (',' + decimal if sep else '')

    def _verificar_cotizaciones_cargadas(self, monedas):
        self.ensure_one()
        monedas_a_convertir = monedas - self.currency_id - self.company_id.currency_id
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
                'Contabilidad > Monedas antes de continuar.'
                % (self.fecha.strftime('%d/%m/%Y'), ', '.join(monedas_sin_cotizacion.mapped('name')))
            )

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.factura_ids:
            self.factura_ids = [(5, 0, 0)]

    def action_cargar_facturas_pendientes(self):
        """Trae todas las facturas/cuotas pendientes de cobro del Cliente
        seleccionado, en CUALQUIER moneda. No duplica las que ya estén
        cargadas."""
        self.ensure_one()
        if self.state != 'borrador':
            raise UserError('Solo se pueden cargar facturas mientras el Recibo está en Borrador.')
        if not self.partner_id:
            raise UserError('Seleccione primero un Cliente.')

        ya_cargadas = self.factura_ids.mapped('move_line_id')
        lineas = self.env['account.move.line'].search([
            ('company_id', '=', self.company_id.id),
            ('partner_id', '=', self.partner_id.id),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('move_id.state', '=', 'posted'),
            ('move_id.move_type', 'in', ('out_invoice', 'out_refund')),
            ('reconciled', '=', False),
            ('id', 'not in', ya_cargadas.ids),
        ])
        self._verificar_cotizaciones_cargadas(lineas.mapped('currency_id'))

        nuevas = self.env['local_py.recibo.factura']
        for linea in lineas:
            importe = abs(linea.amount_residual_currency) if linea.currency_id else abs(linea.amount_residual)
            nuevas |= self.env['local_py.recibo.factura'].create({
                'recibo_id': self.id,
                'move_line_id': linea.id,
                'importe_a_cobrar': importe,
            })
        nuevas._set_cotizacion_default(self.fecha)

    def action_marcar_en_proceso(self):
        self.ensure_one()
        if self.state != 'borrador':
            raise UserError('Solo se puede marcar "En Proceso" un Recibo en Borrador.')
        if not self.factura_ids:
            raise UserError('Agregue al menos una factura/cuota a cobrar antes de continuar.')
        if not self.medio_ids:
            raise UserError('Agregue al menos un Medio de Cobro antes de continuar.')
        a_refrescar = self.factura_ids.filtered(lambda f: not f.cotizacion_manual)
        if a_refrescar:
            a_refrescar._set_cotizacion_default(self.fecha)
        diferencia = self.currency_id.round(self.diferencia)
        if diferencia > 0:
            raise UserError(
                'El total de Medios de Cobro (%s) no alcanza para cubrir el total a '
                'cobrar de las Facturas seleccionadas (%s) — falta %s.'
                % (self._fmt(self.total_medios), self._fmt(self.total_facturas), self._fmt(diferencia))
            )
        if diferencia < 0 and not self.permite_saldo_a_favor:
            return {
                'name': 'Sobra plata entre Medios y Facturas',
                'type': 'ir.actions.act_window',
                'res_model': 'local_py.recibo.saldo_favor_wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_recibo_id': self.id},
            }
        self.write({'state': 'en_proceso', 'fecha_en_proceso': fields.Datetime.now()})

    def action_volver_borrador(self):
        for recibo in self:
            if recibo.state != 'en_proceso':
                raise UserError('Solo se puede volver a Borrador desde el estado "En Proceso".')
        self.write({'state': 'borrador', 'fecha_en_proceso': False, 'permite_saldo_a_favor': False})

    def action_confirmar(self):
        for recibo in self:
            if recibo.state != 'en_proceso':
                raise UserError('Solo se puede Confirmar un Recibo que esté "En Proceso".')
            a_refrescar = recibo.factura_ids.filtered(lambda f: not f.cotizacion_manual)
            recibo._verificar_cotizaciones_cargadas(a_refrescar.mapped('currency_id'))
            a_refrescar._set_cotizacion_default(recibo.fecha)
            diferencia_final = recibo.currency_id.round(recibo.total_facturas - recibo.total_medios)
            if diferencia_final > 0:
                raise UserError(
                    'La cotización cambió y el total de Medios de Cobro ya no alcanza para '
                    'cubrir las Facturas seleccionadas — falta %s. Revise los importes antes '
                    'de volver a Confirmar.' % recibo._fmt(diferencia_final)
                )
            if diferencia_final < 0 and not recibo.permite_saldo_a_favor:
                raise UserError(
                    'La cotización cambió y ahora sobran %s entre los Medios de Cobro y las '
                    'Facturas seleccionadas. Vuelva a "En Proceso" para que el sistema le '
                    'pregunte de nuevo qué hacer con el sobrante.' % recibo._fmt(-diferencia_final)
                )
            numero = recibo.serie_id._asignar_siguiente_numero()
            recibo.numero = numero
            recibo.name = '%s-%s' % (recibo.serie_id.name, str(numero).zfill(7))
            recibo._generar_cobros()
        self.write({'state': 'confirmado', 'fecha_confirmacion': fields.Datetime.now()})

    def _generar_cobros(self):
        """Genera los Cobros y los concilia contra las Facturas/Cuotas
        seleccionadas — mismo motor de reparto ya probado en Orden de
        Pago (waterfall exacto, prioridad por tipo de Medio), adaptado
        al sentido Cliente (Cobro entrante, Cuenta Por Cobrar)."""
        self.ensure_one()
        AccountPayment = self.env['account.payment'].with_context(l10n_py_allow_orden_pago_write=True)
        currency = self.currency_id

        medios_retencion = self.medio_ids.filtered(lambda m: m.tipo == 'retencion')
        medios_normales = self.medio_ids - medios_retencion

        def _prioridad_medio(medio):
            # 0 = Saldo a Favor, 1 = Cheque, 2 = Transferencia, 3 = Efectivo.
            return {'saldo_favor': 0, 'cheque': 1, 'transferencia': 2, 'efectivo': 3}.get(medio.tipo, 9)

        medios_normales = medios_normales.sorted(key=_prioridad_medio)

        facturas_pend = []
        for f in self.factura_ids:
            retenido = sum(medios_retencion.filtered(lambda m: m.recibo_factura_id == f).mapped('importe'))
            facturas_pend.append([f, f.valor_convertido - retenido])

        for medio in medios_retencion:
            factura = medio.recibo_factura_id
            if not factura:
                raise UserError('La fila de Retención tiene que indicar a qué Factura corresponde.')
            move = self._crear_movimiento_retencion_recibida(medio, factura, medio.importe)
            medio.retencion_move_id = move.id
            linea_receivable = move.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
            )
            (factura.move_line_id + linea_receivable).reconcile()

        medios_pend = [[m, m.importe] for m in medios_normales]

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

        sobrante_por_medio = []
        if j < len(medios_pend):
            medio_j, monto_restante_j = medios_pend[j]
            if currency.compare_amounts(monto_restante_j, 0) > 0:
                sobrante_por_medio.append((medio_j, monto_restante_j))
            for medio_k, monto_k in medios_pend[j + 1:]:
                if currency.compare_amounts(monto_k, 0) > 0:
                    sobrante_por_medio.append((medio_k, monto_k))

        if i < len(facturas_pend):
            raise UserError(
                'No se pudo repartir exactamente el importe de los Medios de Cobro contra '
                'las Facturas/Cuotas seleccionadas — falta cobertura. Revise los importes '
                'antes de continuar.'
            )
        if sobrante_por_medio and not self.permite_saldo_a_favor:
            raise UserError(
                'Sobra importe entre los Medios de Cobro y las Facturas/Cuotas '
                'seleccionadas, y este Recibo no tiene aprobado dejarlo como Saldo a '
                'Favor. Vuelva a "En Proceso" para que el sistema le pregunte qué hacer '
                'con el sobrante.'
            )

        for factura, medio, monto in asignaciones:
            if medio.tipo == 'saldo_favor':
                linea_origen = medio.saldo_favor_payment_id.move_id.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
                )
                (factura.move_line_id + linea_origen).reconcile()
                continue

            payment = self._crear_cobro_medio(AccountPayment, medio, monto)
            linea_receivable = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'asset_receivable' and not l.reconciled
            )
            (factura.move_line_id + linea_receivable).reconcile()

        for medio, monto in sobrante_por_medio:
            if medio.tipo == 'saldo_favor':
                continue
            self._crear_cobro_medio(AccountPayment, medio, monto, es_sobrante=True)

    def _crear_cobro_medio(self, AccountPayment, medio, monto, es_sobrante=False):
        """Crea el Cobro real de una fila de Medios (Efectivo, Transferencia
        o Cheque) — para Cheque, también genera el registro de
        local_py.cheque_cliente en estado "En Cartera" la primera vez."""
        self.ensure_one()
        config = self._get_config_recibo()
        if medio.tipo == 'cheque':
            if not config or not config.l10n_py_diario_cheque_cliente_id:
                raise UserError(
                    'Falta configurar el "Diario de Cheques de Clientes" en Configuraciones '
                    'Localización Py.'
                )
            journal = config.l10n_py_diario_cheque_cliente_id
        else:
            journal = medio.journal_id
            if not journal:
                raise UserError('Falta el Diario en una fila de Medios.')

        comentario = 'Cobro Recibo %s' % self.name
        if es_sobrante:
            comentario += ' (Saldo a Favor)'
        payment = AccountPayment.create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner_id.id,
            'journal_id': journal.id,
            'amount': monto,
            'currency_id': self.currency_id.id,
            'date': self.fecha,
            'company_id': self.company_id.id,
            'memo': comentario,
            'l10n_py_recibo_id': self.id,
            'l10n_py_recibo_medio_id': medio.id,
            'l10n_py_es_saldo_favor': es_sobrante,
        })
        payment.action_post()
        if payment.move_id:
            payment.move_id.l10n_py_comentario = comentario

        if medio.tipo == 'cheque' and not medio.cheque_cliente_id:
            cheque = self.env['local_py.cheque_cliente'].create({
                'name': medio.cheque_numero,
                'bank_id': medio.cheque_banco_id.id,
                'tipo': medio.cheque_tipo,
                'fecha_emision': medio.cheque_fecha_emision or self.fecha,
                'fecha_vencimiento': medio.cheque_fecha_vencimiento or medio.cheque_fecha_emision or self.fecha,
                'company_id': self.company_id.id,
                'currency_id': self.currency_id.id,
                'importe': medio.importe,
                'partner_id': self.partner_id.id,
                'recibo_medio_id': medio.id,
                'estado': 'en_cartera',
            })
            medio.cheque_cliente_id = cheque.id
        return payment

    def _get_config_recibo(self):
        self.ensure_one()
        return self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', self.company_id.id)], limit=1,
        )

    def _crear_movimiento_retencion_recibida(self, medio, factura, monto_header):
        """Asiento de la porción retenida por el Cliente: Débito a la
        Cuenta "Retenido a Confirmar" (Activo), Crédito a la Cuenta Por
        Cobrar del Cliente — la línea de Crédito se concilia contra la
        Factura, igual que un Cobro más."""
        self.ensure_one()
        config = self._get_config_recibo()
        if not config or not config.l10n_py_diario_retencion_recibida_id or not config.l10n_py_cuenta_retencion_a_confirmar_id:
            raise UserError(
                'Falta configurar el "Diario de Retención Recibida" y/o la Cuenta '
                '"Retenido a Confirmar" en Configuraciones Localización Py.'
            )
        journal = config.l10n_py_diario_retencion_recibida_id
        cuenta_a_confirmar = config.l10n_py_cuenta_retencion_a_confirmar_id
        cuenta_receivable = factura.move_line_id.account_id

        company = self.company_id
        es_moneda_extranjera = self.currency_id != company.currency_id
        if es_moneda_extranjera:
            monto_company = self.currency_id._convert(monto_header, company.currency_id, company, self.fecha)
        else:
            monto_company = monto_header

        concepto = 'Retención Recibida - %s - %s' % (self.name, factura.move_id.name)
        move = self.env['account.move'].create({
            'journal_id': journal.id,
            'date': self.fecha,
            'ref': concepto,
            'line_ids': [
                (0, 0, {
                    'name': concepto,
                    'account_id': cuenta_a_confirmar.id,
                    'partner_id': self.partner_id.id,
                    'debit': monto_company,
                    'credit': 0.0,
                    'currency_id': self.currency_id.id,
                    'amount_currency': monto_header if es_moneda_extranjera else monto_company,
                }),
                (0, 0, {
                    'name': concepto,
                    'account_id': cuenta_receivable.id,
                    'partner_id': self.partner_id.id,
                    'debit': 0.0,
                    'credit': monto_company,
                    'currency_id': company.currency_id.id,
                    'amount_currency': -monto_company,
                }),
            ],
        })
        move.action_post()
        return move

    def action_anular(self):
        """Anula un Recibo Confirmado — revierte todo lo generado (Cobros,
        conciliaciones, asiento de Retención) y queda bloqueado para
        siempre (no vuelve a Borrador): si fue un error, hay que cargar
        un Recibo nuevo."""
        for recibo in self:
            if recibo.state != 'confirmado':
                raise UserError('Solo se puede Anular un Recibo que esté Confirmado.')

            cheques = recibo.medio_ids.filtered(lambda m: m.tipo == 'cheque').mapped('cheque_cliente_id')
            cheques_no_cartera = cheques.filtered(lambda c: c.estado not in ('en_cartera', 'anulado'))
            if cheques_no_cartera:
                raise UserError(
                    'No se puede Anular este Recibo: los Cheques %s ya no están "En Cartera" '
                    '(revise su estado, ej. "Deshacer Rechazo" primero, cheque por cheque).'
                    % ', '.join(cheques_no_cartera.mapped('name'))
                )

            pagos = recibo.medio_ids.mapped('payment_ids')
            pagos_saldo_favor = pagos.filtered('l10n_py_es_saldo_favor')
            if pagos_saldo_favor:
                medios_que_lo_usan = pagos_saldo_favor.mapped('l10n_py_recibo_medios_saldo_favor_ids')
                recibos_dependientes = medios_que_lo_usan.mapped('recibo_id') - recibo
                if recibos_dependientes:
                    raise UserError(
                        'Este Recibo generó un Saldo a Favor que ya fue usado en otro(s) '
                        'Recibo(s) más reciente(s): %s. Hay que Anular ese(os) Recibo(s) '
                        'primero, antes de poder anular este.'
                        % ', '.join(recibos_dependientes.mapped('name'))
                    )

            for pago in pagos:
                pago.move_id.line_ids.remove_move_reconcile()
                pago.with_context(l10n_py_allow_orden_pago_write=True).action_draft()
                pago.with_context(l10n_py_allow_orden_pago_write=True).unlink()

            medios_saldo_favor = recibo.medio_ids.filtered('saldo_favor_payment_id')
            if medios_saldo_favor:
                lineas_origen = medios_saldo_favor.mapped('saldo_favor_payment_id.move_id.line_ids').filtered(
                    lambda l: l.account_id.account_type == 'asset_receivable'
                )
                lineas_facturas = recibo.factura_ids.mapped('move_line_id')
                partial_reconciles = self.env['account.partial.reconcile'].search([
                    '|',
                    '&', ('debit_move_id', 'in', lineas_origen.ids), ('credit_move_id', 'in', lineas_facturas.ids),
                    '&', ('credit_move_id', 'in', lineas_origen.ids), ('debit_move_id', 'in', lineas_facturas.ids),
                ])
                partial_reconciles.unlink()

            for medio in recibo.medio_ids.filtered(lambda m: m.tipo == 'retencion'):
                if medio.retencion_move_id:
                    medio.retencion_move_id.line_ids.remove_move_reconcile()
                    medio.retencion_move_id.button_draft()
                    medio.retencion_move_id.unlink()

            cheques.filtered(lambda c: c.estado == 'en_cartera').write({'estado': 'anulado'})

        self.write({'state': 'anulado', 'fecha_anulacion': fields.Datetime.now()})
