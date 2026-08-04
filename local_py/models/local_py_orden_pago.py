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
        help='Total a Pagar (Facturas) menos Total Medios de Pago menos Retención IVA '
             '(estimada) — es lo que falta cargar en Medios reales (Efectivo, '
             'Transferencia, Cheque, etc.). Tiene que quedar en cero antes de poder '
             'pasar a "En Proceso".',
    )
    hay_monedas_distintas = fields.Boolean(compute='_compute_totales')
    total_retencion_iva_estimada = fields.Monetary(
        string='Retención IVA (estimada)', compute='_compute_totales',
        currency_field='currency_id',
        help='Lo que el sistema va a agregar solo en Medios al Confirmar, según la '
             'situación actual del Proveedor — ya está descontado de "Diferencia", así '
             'que no hace falta restarlo a mano al cargar sus otros Medios de Pago '
             '(Efectivo, Transferencia, Cheque, etc.). Es una estimación: después de '
             'editar las Facturas, presione "Actualizar Retención Estimada" para '
             'refrescarla.',
    )

    @api.depends('factura_ids.valor_convertido', 'factura_ids.currency_id', 'medio_ids.importe', 'currency_id',
                 'factura_ids.importe_a_pagar', 'factura_ids.cotizacion', 'partner_id', 'fecha', 'state')
    def _compute_totales(self):
        for orden in self:
            orden.total_facturas = sum(orden.factura_ids.mapped('valor_convertido'))
            orden.total_medios = sum(orden.medio_ids.mapped('importe'))
            orden.hay_monedas_distintas = bool(
                orden.factura_ids.filtered(lambda f: f.currency_id != orden.currency_id)
            )
            if orden.state == 'confirmado':
                # Ya está generada de verdad — la fila de Retención ya es un Medio
                # real más, incluido en total_medios. No hay que restarla aparte
                # (si no, se descontaría dos veces).
                orden.total_retencion_iva_estimada = sum(
                    orden.medio_ids.filtered('es_retencion').mapped('importe')
                )
                orden.diferencia = orden.total_facturas - orden.total_medios
            else:
                evaluacion = orden._evaluar_retencion_iva()
                orden.total_retencion_iva_estimada = sum(m[1] for m in evaluacion.values())
                orden.diferencia = orden.total_facturas - orden.total_medios - orden.total_retencion_iva_estimada

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.factura_ids:
            self.factura_ids = [(5, 0, 0)]

    def action_actualizar_retencion_estimada(self):
        """Recalcula la vista previa de Retención IVA de todas las
        Facturas de la Orden de Pago. Al ser un botón (no un onchange),
        Odoo guarda el formulario automáticamente antes de ejecutarlo —
        así el cálculo trabaja siempre sobre datos ya guardados, sin la
        ambigüedad de registros todavía "virtuales" que hacía fallar el
        cálculo en vivo mientras se escribía (confirmado con varias
        pruebas en video)."""
        self.ensure_one()
        evaluacion = self._evaluar_retencion_iva()
        for factura in self.factura_ids:
            datos = evaluacion.get(factura)
            factura.retencion_iva_estimada = datos[1] if datos else 0.0
        return True

    @api.onchange('currency_id', 'fecha')
    def _onchange_currency_id_cotizacion(self):
        a_refrescar = self.factura_ids.filtered(lambda f: not f.cotizacion_manual)
        if a_refrescar:
            a_refrescar._set_cotizacion_default(self.fecha)

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

    def write(self, vals):
        if vals.get('active') is False:
            confirmadas = self.filtered(lambda o: o.state == 'confirmado')
            if confirmadas:
                raise UserError(
                    'No se puede archivar una Orden de Pago Confirmada (Archivar es solo '
                    'para operaciones que nunca se ejecutaron). Si de verdad hace falta '
                    'anularla, use primero "Deshacer Confirmación".'
                )
        return super().write(vals)

    # ------------------------------------------------------------------
    # Flujo de estados
    # ------------------------------------------------------------------
    def _verificar_cotizaciones_cargadas(self, monedas):
        """Bloquea si falta la cotización exacta del día para alguna
        moneda — para no usar en silencio la última cotización cargada,
        que puede no ser la del día."""
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
            a_refrescar = orden.factura_ids.filtered(lambda f: not f.cotizacion_manual)
            if a_refrescar:
                a_refrescar._set_cotizacion_default(orden.fecha)
            if orden.currency_id.round(orden.diferencia) != 0:
                raise UserError(
                    'El total de Medios de Pago (%s) más la Retención IVA estimada (%s) debe '
                    'coincidir exactamente con el total a pagar de las Facturas seleccionadas '
                    '(%s).' % (orden.total_medios, orden.total_retencion_iva_estimada, orden.total_facturas)
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
            orden._calcular_retenciones_iva()
            if orden.currency_id.round(orden.total_facturas - orden.total_medios) != 0:
                raise UserError(
                    'La cotización cambió y el cuadre entre Facturas y Medios de Pago ya no '
                    'coincide (Facturas: %s, Medios: %s). Revise los importes antes de volver '
                    'a Confirmar.' % (orden.total_facturas, orden.total_medios)
                )
            orden._generar_pagos()
        self.write({'state': 'confirmado', 'fecha_confirmacion': fields.Datetime.now()})
        for orden in self:
            orden.medio_ids.filtered('es_retencion').write({
                'fecha_emision': orden.fecha_confirmacion.date(),
            })

    def _get_acumulado_mensual_iva_previo(self, partner, fecha):
        """Suma el Valor Imponible (proporcional a lo pagado, en Gs.) de
        todas las Facturas pagadas en Órdenes de Pago Confirmadas de este
        Proveedor durante el mes de 'fecha' — sin incluir la Orden de
        Pago actual (se suma aparte, en _calcular_retenciones_iva)."""
        primer_dia = fecha.replace(day=1)
        if fecha.month == 12:
            ultimo_dia = fecha.replace(year=fecha.year + 1, month=1, day=1)
        else:
            ultimo_dia = fecha.replace(month=fecha.month + 1, day=1)
        ordenes = self.search([
            ('partner_id', '=', partner.id),
            ('state', '=', 'confirmado'),
            ('fecha', '>=', primer_dia),
            ('fecha', '<', ultimo_dia),
            ('id', '!=', self.id),
        ])
        return sum(
            factura._imponible_proporcional_gs()
            for orden in ordenes for factura in orden.factura_ids
        )

    def _evaluar_retencion_iva(self):
        """Evalúa si corresponde Retención IVA para esta Orden de Pago,
        SIN generar ningún registro — se puede llamar en cualquier
        momento (Borrador, En Proceso) para mostrar una vista previa.
        Devuelve un diccionario {factura: (base_header, monto_header,
        monto_gs)} con lo que correspondería retener por cada Factura si
        se Confirmara ahora mismo."""
        self.ensure_one()
        resultado = {}
        partner = self.partner_id
        if not partner or not partner.l10n_py_retencion_iva or not self.fecha:
            return resultado
        config = self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', self.company_id.id)], limit=1,
        )
        if not config or not config.l10n_py_retencion_iva or not config.l10n_py_diario_retencion_iva_id:
            return resultado

        no_retencion = self.env['local_py.no_retencion'].search([
            ('partner_id', '=', partner.id),
            ('tipo_retencion', '=', 'iva'),
            ('fecha_desde', '<=', self.fecha),
            ('fecha_hasta', '>=', self.fecha),
        ], limit=1)
        if no_retencion:
            return resultado

        acumulado_previo = self._get_acumulado_mensual_iva_previo(partner, self.fecha)
        contribucion_esta_op = sum(f._imponible_proporcional_gs() for f in self.factura_ids)
        if self.company_id.currency_id.compare_amounts(
            acumulado_previo + contribucion_esta_op, config.l10n_py_retencion_iva_minimo
        ) < 0:
            return resultado

        porcentaje = partner.l10n_py_retencion_iva_porcentaje
        if not porcentaje:
            return resultado

        for factura in self.factura_ids:
            base_header, monto_header, monto_gs = factura._retencion_iva_calcular(porcentaje)
            if not self.currency_id.is_zero(monto_header):
                resultado[factura] = (base_header, monto_header, monto_gs)
        return resultado

    def _calcular_retenciones_iva(self):
        """Genera de verdad los registros de Retención IVA (y la fila en
        Medios) a partir de _evaluar_retencion_iva(). Se ejecuta al
        Confirmar. Si ya existía una fila de un intento anterior (por
        ejemplo, si la Confirmación anterior falló por descuadre), se
        limpia primero para recalcular de cero."""
        self.ensure_one()
        self.medio_ids.filtered('es_retencion').unlink()
        self.env['local_py.retencion_emitida'].search([
            ('orden_pago_id', '=', self.id), ('tipo_retencion', '=', 'iva'),
        ]).unlink()

        evaluacion = self._evaluar_retencion_iva()
        if not evaluacion:
            return

        config = self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', self.company_id.id)], limit=1,
        )
        Retencion = self.env['local_py.retencion_emitida']
        for factura, (base_header, monto_header, monto_gs) in evaluacion.items():
            Retencion.create({
                'orden_pago_id': self.id,
                'orden_pago_factura_id': factura.id,
                'fecha': self.fecha,
                'tipo_retencion': 'iva',
                'base_imponible': base_header,
                'porcentaje': factura.orden_pago_id.partner_id.l10n_py_retencion_iva_porcentaje,
                'monto': monto_header,
                'monto_gs': monto_gs,
            })
            if self.currency_id.compare_amounts(monto_header, 0) > 0:
                # Un Medio de Retención POR FACTURA, no uno combinado — así la
                # conciliación va siempre directo a la factura que corresponde,
                # sin pasar por el reparto genérico entre Facturas y Medios (que
                # no distingue "de dónde viene" cada porción de la Retención).
                self.env['local_py.orden_pago.medio'].create({
                    'orden_pago_id': self.id,
                    'journal_id': config.l10n_py_diario_retencion_iva_id.id,
                    'importe': monto_header,
                    'es_retencion': True,
                    'retencion_factura_id': factura.id,
                })

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
        retenciones_levantadas = self.env['local_py.retencion_emitida'].search([
            ('orden_pago_id', '=', self.id), ('estado', '=', 'levantada'),
        ])
        if retenciones_levantadas:
            raise UserError(
                'Esta Orden de Pago tiene Retenciones ya Levantadas ante la DNIT — no se '
                'puede deshacer la Confirmación directamente. Primero hay que Anularlas en '
                'Localización Paraguay > Retenciones Emitidas (una vez resuelta la anulación '
                'ante la DNIT), y recién ahí se puede continuar.'
            )
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
        medios_retencion = self.medio_ids.filtered('es_retencion')
        for asiento in medios_retencion.mapped('retencion_move_id'):
            asiento.line_ids.remove_move_reconcile()
            asiento.button_draft()
            asiento.unlink()
        self.env['local_py.retencion_emitida'].search([
            ('orden_pago_id', '=', self.id), ('estado', '=', 'pendiente'),
        ]).unlink()
        medios_retencion.unlink()
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
        diferencia de cambio se dispara igual de bien caso por caso.

        Los Medios de Retención se procesan APARTE, antes que nada:
        cada uno ya tiene una Factura específica asignada
        (retencion_factura_id, un Medio por Factura) — no son
        intercambiables como el Efectivo, así que se concilian siempre
        1 a 1 contra esa Factura exacta, nunca a través del reparto
        genérico (que no distingue "de dónde viene" cada porción).
        Recién con el resto (Facturas ya descontada su propia Retención,
        y los Medios que no son de Retención) se arma el reparto
        genérico, como siempre."""
        self.ensure_one()
        AccountPayment = self.env['account.payment'].with_context(l10n_py_allow_orden_pago_write=True)
        currency = self.currency_id

        medios_retencion = self.medio_ids.filtered('es_retencion')
        medios_normales = self.medio_ids - medios_retencion

        for medio in medios_retencion:
            factura = medio.retencion_factura_id
            move = self._crear_movimiento_retencion(medio, factura, medio.importe)
            linea_payable = move.line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable' and not l.reconciled
            )
            (factura.move_line_id + linea_payable).reconcile()

        facturas_pend = []
        for f in self.factura_ids:
            retenido = sum(medios_retencion.filtered(lambda m: m.retencion_factura_id == f).mapped('importe'))
            facturas_pend.append([f, f.valor_convertido - retenido])
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

    def _crear_movimiento_retencion(self, medio, factura, monto_header):
        """Genera el asiento contable de la Retención IVA (débito a la
        cuenta por pagar del Proveedor, crédito a la cuenta del Diario de
        Retención) y lo deja listo para conciliar contra la factura. No
        se usa account.payment porque Odoo no permite generar Pagos sobre
        Diarios de tipo Misceláneo."""
        self.ensure_one()
        company = self.company_id
        journal = medio.journal_id
        cuenta_retencion = journal.default_account_id
        if not cuenta_retencion:
            raise UserError(
                'El Diario de Retención "%s" no tiene una Cuenta configurada '
                '(Contabilidad > Diarios > esa Cuenta contable).' % journal.name
            )
        cuenta_proveedor = factura.move_line_id.account_id
        factura_currency = factura.move_line_id.currency_id or company.currency_id
        es_moneda_extranjera = factura_currency != company.currency_id

        if self.currency_id == company.currency_id:
            monto_company = monto_header
        else:
            monto_company = self.currency_id._convert(monto_header, company.currency_id, company, self.fecha)

        if es_moneda_extranjera:
            monto_moneda_factura = monto_header / (factura.cotizacion or 1.0)
        else:
            monto_moneda_factura = monto_company

        concepto = 'Retención IVA - %s' % self.name
        move = self.env['account.move'].create({
            'journal_id': journal.id,
            'date': self.fecha,
            'ref': concepto,
            'line_ids': [
                (0, 0, {
                    'name': concepto,
                    'account_id': cuenta_proveedor.id,
                    'partner_id': self.partner_id.id,
                    'debit': monto_company,
                    'credit': 0.0,
                    'currency_id': factura_currency.id,
                    'amount_currency': monto_moneda_factura if es_moneda_extranjera else monto_company,
                }),
                (0, 0, {
                    'name': concepto,
                    'account_id': cuenta_retencion.id,
                    'partner_id': self.partner_id.id,
                    'debit': 0.0,
                    'credit': monto_company,
                    'currency_id': company.currency_id.id,
                    'amount_currency': -monto_company,
                }),
            ],
        })
        move.action_post()
        medio.retencion_move_id = move.id
        return move
