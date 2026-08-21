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
        'res.partner', string='Proveedor', tracking=True,
        help='Obligatorio, salvo que la Orden sea de tipo "Pago a Cuenta" — ese tipo de '
             'pago no necesita ir a nombre de ningún Contacto (ej. pago de impuestos, '
             'retiro de fondos para caja).',
    )
    es_pago_a_cuenta = fields.Boolean(
        string='Pago a Cuenta', tracking=True,
        help='Para pagos que no corresponden a Facturas de un Proveedor puntual — por '
             'ejemplo, pago de impuestos al fisco, o fondos para una Caja. Oculta la '
             'pestaña Facturas y no calcula Retenciones; el Proveedor deja de ser '
             'obligatorio, y en su lugar se carga una Cuenta contable, un Importe y una '
             'Referencia (a mano, no hay Factura externa contra la cual cuadrar).\n\n'
             'AVISO: esta es una función nueva y menos probada que el resto del módulo '
             '— revisar con atención los primeros asientos que genere.',
    )
    es_orden_retencion = fields.Boolean(
        string='Orden de Pago Retención', tracking=True,
        help='Para declarar la Retención de una Factura/Cuota antes de pagarla de '
             'verdad (por ejemplo, cuando la cuota vence sin haberse pagado, pero la '
             'obligación fiscal de retener igual corresponde). Calcula la Retención '
             'IVA/Renta como si se estuviera pagando el 100% de cada Factura/Cuota '
             'elegida, sin control de Mínimo Imponible, y sin exigir ningún otro Medio '
             'de Pago — cuando la Factura se termine pagando de verdad más adelante, el '
             'sistema recuerda lo ya retenido y no vuelve a retener sobre lo mismo. No '
             'compatible con "Pago a Cuenta".',
    )
    cuenta_pago_id = fields.Many2one(
        'account.account', string='Cuenta',
        domain="[('l10n_py_pagos_a_cuenta', '=', True), ('company_ids', 'in', company_id)]",
        help='Solo aparecen las Cuentas marcadas con "Pagos a Cuenta" tildado (en su '
             'propia ficha, Contabilidad > Plan de Cuentas) — así se evita elegir por '
             'error una Cuenta de Ingresos, Gastos, Activo Fijo, o cualquier otra que '
             'no debería verse afectada por este circuito.',
    )
    importe_pago_cuenta = fields.Monetary(
        string='Importe', currency_field='currency_id',
        help='Carga manual — no hay ninguna Factura externa contra la cual cuadrar '
             'automáticamente, así que este es el valor contra el que se compara el '
             'total de Medios de Pago.',
    )
    referencia_pago_cuenta = fields.Char(
        string='Referencia',
        help='Nombre del beneficiario del cheque, o una referencia corta del motivo del '
             'pago para los demás Medios — reemplaza al dato de "Proveedor" para poder '
             'identificar de qué se trata este Pago a Cuenta.',
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
    retencion_absorcion_ids = fields.One2many(
        'local_py.retencion_emitida', 'orden_pago_id', string='Retenciones por Absorción al Exterior',
        domain=['|', ('es_absorcion_iva', '=', True), ('es_absorcion_renta', '=', True)],
        help='Retenciones (IVA y/o Renta) con Absorción generadas para Proveedores del '
             'exterior — de solo lectura: la porción absorbida no participa del cuadre '
             'de Medios, ya que no se le descuenta nada al Proveedor por ella. Puede '
             'haber más de una si la Orden de Pago incluye varias Facturas del exterior.',
    )

    total_facturas = fields.Monetary(
        string='Total a Pagar (Facturas)', compute='_compute_totales', currency_field='currency_id',
    )
    total_medios = fields.Monetary(
        string='Total Medios de Pago', compute='_compute_totales', currency_field='currency_id',
    )
    diferencia = fields.Monetary(
        string='Diferencia', compute='_compute_totales', currency_field='currency_id',
        help='Total a Pagar (Facturas) menos Total Medios de Pago menos Retención IVA/Renta '
             '(estimada) — es lo que falta cargar en Medios reales (Efectivo, '
             'Transferencia, Cheque, etc.). No puede quedar en negativo (faltaría plata) '
             'para poder pasar a "En Proceso" — si queda en positivo (sobra), el sistema '
             'pregunta si corregir los importes o dejarlo como Saldo a Favor del Proveedor.',
    )
    permite_saldo_a_favor = fields.Boolean(
        string='Permite Saldo a Favor', copy=False,
        help='Se tilda solo desde el wizard que aparece al detectar un sobrante entre '
             'Medios de Pago y Facturas — habilita que ese excedente quede sin conciliar '
             '(Saldo a Favor del Proveedor) en vez de bloquear la Orden de Pago.',
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
    total_retencion_renta_estimada = fields.Monetary(
        string='Retención Renta (estimada)', compute='_compute_totales',
        currency_field='currency_id',
        help='Igual que "Retención IVA (estimada)", pero para la Retención Renta No '
             'Residente — solo suma la porción que se descuenta del Proveedor; la '
             'porción que se absorbe (si corresponde) no afecta este total ni la '
             'Diferencia, ya que no sale de los Medios de Pago.',
    )
    total_saldo_favor_proveedor = fields.Monetary(
        string='Saldo a Favor del Proveedor', compute='_compute_total_saldo_favor_proveedor',
        currency_field='currency_id',
        help='Total disponible del Proveedor, en la misma Moneda de esta Orden — es lo '
             'que se puede elegir como Medio "Saldo a Favor" acá. Si el Proveedor '
             'también tiene saldo en alguna otra Moneda, no se incluye acá (no se puede '
             'usar en esta Orden, al no coincidir la Moneda).',
    )

    @api.depends('partner_id', 'currency_id')
    def _compute_total_saldo_favor_proveedor(self):
        for orden in self:
            if not orden.partner_id:
                orden.total_saldo_favor_proveedor = 0.0
                continue
            pagos = self.env['account.payment'].search([
                ('partner_id', '=', orden.partner_id.id),
                ('l10n_py_es_saldo_favor', '=', True),
                ('currency_id', '=', orden.currency_id.id),
                ('l10n_py_saldo_favor_disponible', '>', 0),
            ])
            orden.total_saldo_favor_proveedor = sum(pagos.mapped('l10n_py_saldo_favor_disponible'))

    @api.constrains('es_pago_a_cuenta', 'es_orden_retencion')
    def _check_pago_a_cuenta_vs_orden_retencion(self):
        for orden in self:
            if orden.es_pago_a_cuenta and orden.es_orden_retencion:
                raise UserError(
                    '"Pago a Cuenta" y "Orden de Pago Retención" no se pueden usar juntas '
                    'en la misma Orden — elija una de las dos.'
                )

    @api.constrains('es_pago_a_cuenta', 'partner_id', 'cuenta_pago_id', 'importe_pago_cuenta', 'referencia_pago_cuenta')
    def _check_pago_a_cuenta_datos(self):
        for orden in self:
            if orden.es_pago_a_cuenta:
                faltantes = []
                if not orden.cuenta_pago_id:
                    faltantes.append('Cuenta')
                if not orden.importe_pago_cuenta:
                    faltantes.append('Importe')
                if not orden.referencia_pago_cuenta:
                    faltantes.append('Referencia')
                if faltantes:
                    raise UserError(
                        'Para una Orden de Pago "Pago a Cuenta", hace falta completar: %s.'
                        % ', '.join(faltantes)
                    )
            elif not orden.partner_id:
                raise UserError('Elija un Proveedor, o tilde "Pago a Cuenta" si esta Orden no corresponde a uno.')

    @api.depends('factura_ids.valor_convertido', 'factura_ids.currency_id', 'medio_ids.importe', 'currency_id',
                 'factura_ids.importe_a_pagar', 'factura_ids.cotizacion', 'partner_id', 'fecha', 'state')
    def _compute_totales(self):
        for orden in self:
            orden.total_facturas = sum(orden.factura_ids.mapped('valor_convertido'))
            orden.total_medios = sum(orden.medio_ids.mapped('importe'))
            orden.hay_monedas_distintas = bool(
                orden.factura_ids.filtered(lambda f: f.currency_id != orden.currency_id)
            )
            if orden.es_pago_a_cuenta:
                # No hay Facturas externas contra las cuales cuadrar — el Importe
                # cargado a mano es el valor de referencia, y no corresponden
                # Retenciones (no hay una operación gravada específica detrás).
                orden.total_retencion_iva_estimada = 0.0
                orden.total_retencion_renta_estimada = 0.0
                orden.diferencia = orden.importe_pago_cuenta - orden.total_medios
            elif orden.state == 'confirmado':
                # Ya está generada de verdad — las filas de Retención ya son Medios
                # reales, incluidos en total_medios. No hay que restarlas aparte (si
                # no, se descontarían dos veces). Se separan por Diario para que cada
                # total (IVA / Renta) muestre lo que realmente le corresponde.
                config = orden._get_config_retencion()
                diario_iva = config.l10n_py_diario_retencion_iva_id if config else False
                diario_renta = config.l10n_py_diario_retencion_renta_id if config else False
                medios_retencion = orden.medio_ids.filtered('es_retencion')
                orden.total_retencion_iva_estimada = sum(
                    medios_retencion.filtered(lambda m: m.journal_id == diario_iva).mapped('importe')
                )
                orden.total_retencion_renta_estimada = sum(
                    medios_retencion.filtered(lambda m: m.journal_id == diario_renta).mapped('importe')
                )
                if orden.es_orden_retencion:
                    # En este modo, "Total a Pagar" no es el total de la Factura —
                    # es lo que efectivamente se retuvo (0 si todo se absorbió, ya
                    # que ahí no hay ningún Medio de por medio). Así no se ve una
                    # Diferencia grande y confusa comparando contra el total real
                    # de la Factura, que acá nunca se paga.
                    orden.total_facturas = (
                        orden.total_retencion_iva_estimada + orden.total_retencion_renta_estimada
                    )
                orden.diferencia = orden.total_facturas - orden.total_medios
            else:
                evaluacion_iva = orden._evaluar_retencion_iva()
                total_iva = sum(m['monto_total'] for m in evaluacion_iva.values())
                evaluacion_exterior = orden._evaluar_retencion_exterior()
                for datos in evaluacion_exterior.values():
                    iva_datos = datos.get('iva')
                    if iva_datos and not iva_datos['se_absorbe']:
                        total_iva += iva_datos['monto']
                total_renta = sum(
                    datos['renta']['monto']
                    for datos in evaluacion_exterior.values()
                    if datos.get('renta') and not datos['renta']['se_absorbe']
                )
                orden.total_retencion_iva_estimada = total_iva
                orden.total_retencion_renta_estimada = total_renta
                if orden.es_orden_retencion:
                    # Mismo criterio que en Confirmado, pero acá con los importes
                    # todavía en estimación (los mismos que se van a generar de
                    # verdad al Confirmar).
                    orden.total_facturas = total_iva + total_renta
                orden.diferencia = (
                    orden.total_facturas - orden.total_medios
                    - orden.total_retencion_iva_estimada - orden.total_retencion_renta_estimada
                    if not orden.es_orden_retencion else orden.total_facturas - orden.total_medios
                )

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.factura_ids:
            self.factura_ids = [(5, 0, 0)]

    @api.onchange('es_pago_a_cuenta')
    def _onchange_es_pago_a_cuenta(self):
        if self.es_pago_a_cuenta and self.es_orden_retencion:
            self.es_orden_retencion = False

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
            factura.retencion_iva_estimada = datos['monto_total'] if datos else 0.0
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
            ('move_id.move_type', 'in', ('in_invoice', 'in_refund')),
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
        self.ensure_one()
        if self.state != 'borrador':
            raise UserError('Solo se puede marcar "En Proceso" una Orden de Pago en Borrador.')
        if self.es_pago_a_cuenta:
            if not self.medio_ids:
                raise UserError('Agregue al menos un Medio de Pago antes de continuar.')
            self.medio_ids._resolver_chequera()
            if self.currency_id.round(self.diferencia) != 0:
                raise UserError(
                    'El total de Medios de Pago (%s) debe coincidir exactamente con el '
                    'Importe cargado (%s).' % (self._fmt(self.total_medios), self._fmt(self.importe_pago_cuenta))
                )
            self.write({'state': 'en_proceso', 'fecha_en_proceso': fields.Datetime.now()})
            return
        if not self.factura_ids:
            raise UserError('Agregue al menos una factura/cuota a pagar antes de continuar.')
        if self.es_orden_retencion:
            # No hay Medios de Efectivo/Cheque/Transferencia en este modo — no
            # corresponde exigirlos, ni que el cuadre dé exacto (nunca se está
            # pagando el 100%, solo declarando la Retención).
            self.write({'state': 'en_proceso', 'fecha_en_proceso': fields.Datetime.now()})
            return
        if not self.medio_ids:
            raise UserError('Agregue al menos un Medio de Pago antes de continuar.')
        self.medio_ids._resolver_chequera()
        a_refrescar = self.factura_ids.filtered(lambda f: not f.cotizacion_manual)
        if a_refrescar:
            a_refrescar._set_cotizacion_default(self.fecha)
        diferencia = self.currency_id.round(self.diferencia)
        if diferencia > 0:
            raise UserError(
                'El total de Medios de Pago (%s) más la Retención IVA estimada (%s) y la '
                'Retención Renta estimada (%s) no alcanza para cubrir el total a pagar de '
                'las Facturas seleccionadas (%s) — falta %s.'
                % (
                    self._fmt(self.total_medios), self._fmt(self.total_retencion_iva_estimada),
                    self._fmt(self.total_retencion_renta_estimada), self._fmt(self.total_facturas),
                    self._fmt(diferencia),
                )
            )
        if diferencia < 0 and not self.permite_saldo_a_favor:
            return {
                'name': 'Sobra plata entre Medios y Facturas',
                'type': 'ir.actions.act_window',
                'res_model': 'local_py.orden_pago.saldo_favor_wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_orden_pago_id': self.id},
            }
        self.write({'state': 'en_proceso', 'fecha_en_proceso': fields.Datetime.now()})

    def action_volver_borrador(self):
        for orden in self:
            if orden.state != 'en_proceso':
                raise UserError('Solo se puede volver a Borrador desde el estado "En Proceso".')
        self.write({'state': 'borrador', 'fecha_en_proceso': False, 'permite_saldo_a_favor': False})

    def action_confirmar(self):
        for orden in self:
            if orden.state != 'en_proceso':
                raise UserError('Solo se puede Confirmar una Orden de Pago que esté "En Proceso".')
            if orden.es_pago_a_cuenta:
                orden.medio_ids._resolver_chequera()
                if orden.currency_id.round(orden.importe_pago_cuenta - orden.total_medios) != 0:
                    raise UserError(
                        'El cuadre entre el Importe (%s) y los Medios de Pago (%s) ya no '
                        'coincide. Revise los importes antes de volver a Confirmar.'
                        % (orden._fmt(orden.importe_pago_cuenta), orden._fmt(orden.total_medios))
                    )
                orden._generar_pagos_a_cuenta()
                continue
            orden._validar_configuracion_retencion()
            orden.medio_ids._resolver_chequera()
            a_refrescar = orden.factura_ids.filtered(lambda f: not f.cotizacion_manual)
            orden._verificar_cotizaciones_cargadas(a_refrescar.mapped('currency_id'))
            a_refrescar._set_cotizacion_default(orden.fecha)
            if orden.es_orden_retencion:
                antes = orden.env['local_py.retencion_emitida'].search_count([('orden_pago_id', '=', orden.id)])
                orden._calcular_retenciones_iva()
                orden._calcular_retenciones_exterior()
                despues = orden.env['local_py.retencion_emitida'].search_count([('orden_pago_id', '=', orden.id)])
                if despues == antes:
                    raise UserError(
                        'Las Facturas / Cuotas seleccionadas ya fueron retenidas al 100% de '
                        'lo que corresponde.'
                    )
                orden._generar_pagos()
                continue
            orden._calcular_retenciones_iva()
            orden._calcular_retenciones_exterior()
            diferencia_final = orden.currency_id.round(orden.total_facturas - orden.total_medios)
            if diferencia_final > 0:
                raise UserError(
                    'La cotización cambió y el total de Medios de Pago ya no alcanza para cubrir '
                    'las Facturas seleccionadas (Facturas: %s, Medios: %s) — falta %s. Revise los '
                    'importes antes de volver a Confirmar.'
                    % (orden._fmt(orden.total_facturas), orden._fmt(orden.total_medios), orden._fmt(diferencia_final))
                )
            if diferencia_final < 0 and not orden.permite_saldo_a_favor:
                raise UserError(
                    'La cotización cambió y ahora sobran %s entre los Medios de Pago y las '
                    'Facturas seleccionadas (Facturas: %s, Medios: %s). Vuelva a "En Proceso" '
                    'para que el sistema le pregunte de nuevo qué hacer con el sobrante.'
                    % (orden._fmt(-diferencia_final), orden._fmt(orden.total_facturas), orden._fmt(orden.total_medios))
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
            factura._total_gravado_proporcional_gs()
            for orden in ordenes for factura in orden.factura_ids
        )

    def _fmt(self, valor):
        """Formatea un número con separador de miles (punto) — y decimal
        con coma, si la Moneda usa decimales — para que los mensajes de
        error muestren importes legibles, en vez de un float crudo."""
        self.ensure_one()
        decimales = self.currency_id.decimal_places if self.currency_id else 0
        texto = '{:,.{prec}f}'.format(valor or 0.0, prec=decimales)
        entero, sep, decimal = texto.partition('.')
        entero = entero.replace(',', '.')
        return entero + (',' + decimal if sep else '')

    def _get_config_retencion(self):
        self.ensure_one()
        return self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', self.company_id.id)], limit=1,
        )

    def _validar_configuracion_retencion(self):
        """Si el Proveedor de esta Orden de Pago tiene Retención IVA y/o
        Retención Renta activadas, exige que toda la configuración
        necesaria esté completa antes de Confirmar — si algo falta,
        bloquea con un mensaje claro en vez de omitir la Retención en
        silencio (eso dejaría la Orden de Pago Confirmada sin ese
        asiento, sin una forma simple de completarlo después)."""
        self.ensure_one()
        partner = self.partner_id
        if not partner:
            return
        config = self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', self.company_id.id)], limit=1,
        )
        es_exterior = bool(partner.l10n_py_concepto_iva_id and partner.l10n_py_concepto_iva_id.codigo == 'IVA.2')
        faltantes = []

        if (partner.l10n_py_retencion_iva or partner.l10n_py_retencion_renta) and not partner.l10n_py_localizacion_validada:
            faltantes.append(
                'Tildar "Localización Validada" en la ficha del Proveedor (pestaña Localización) — '
                'confirma que alguien revisó sus datos de Retención antes de usarlo en un pago'
            )

        if partner.l10n_py_retencion_iva:
            if not config or not config.l10n_py_retencion_iva:
                faltantes.append('Activar "Retención IVA" en Configuraciones Localización Py')
            if config:
                if not config.l10n_py_diario_retencion_iva_id:
                    faltantes.append('Elegir el "Diario de Retención IVA" en Configuraciones Localización Py')
                elif not config.l10n_py_diario_retencion_iva_id.default_account_id:
                    faltantes.append(
                        'Configurar la Cuenta contable del Diario "%s" (Contabilidad > Diarios)'
                        % config.l10n_py_diario_retencion_iva_id.name
                    )
                if not config.l10n_py_concepto_iva_id:
                    faltantes.append('Elegir el "Concepto IVA" en Configuraciones Localización Py')

            if es_exterior and partner.l10n_py_se_absorbe_iva:
                if config and not config.l10n_py_cuenta_gasto_absorcion_id:
                    faltantes.append(
                        'Elegir la "Cuenta de Gasto por Absorción (IVA)" en Configuraciones Localización Py'
                    )
            elif not es_exterior:
                if not partner.l10n_py_retencion_iva_porcentaje:
                    faltantes.append(
                        'Cargar el "Porcentaje Retención IVA" en la ficha del Proveedor "%s"' % partner.display_name
                    )

        necesita_renta = bool(es_exterior and partner.l10n_py_retencion_renta)
        if necesita_renta:
            facturas_sin_concepto = self.factura_ids.filtered(
                lambda f: not f.move_id.l10n_py_concepto_renta_no_residente_id
            )
            if facturas_sin_concepto:
                faltantes.append(
                    'Completar el "Concepto Renta No Residente" en la Factura de: %s'
                    % ', '.join(facturas_sin_concepto.mapped('move_id.name'))
                )
            if not config or not config.l10n_py_retencion_renta:
                faltantes.append('Activar "Retención Renta" en Configuraciones Localización Py')
            if config:
                if not config.l10n_py_diario_retencion_renta_id:
                    faltantes.append('Elegir el "Diario de Retención Renta" en Configuraciones Localización Py')
                elif not config.l10n_py_diario_retencion_renta_id.default_account_id:
                    faltantes.append(
                        'Configurar la Cuenta contable del Diario "%s" (Contabilidad > Diarios)'
                        % config.l10n_py_diario_retencion_renta_id.name
                    )
                if partner.l10n_py_se_absorbe_renta and not config.l10n_py_cuenta_gasto_absorcion_renta_id:
                    faltantes.append(
                        'Elegir la "Cuenta de Gasto por Absorción (Renta)" en Configuraciones Localización Py'
                    )

        if faltantes:
            raise UserError(
                'El Proveedor "%s" tiene Retenciones activadas, pero falta completar esta '
                'configuración antes de Confirmar (para no dejar la Orden de Pago a medio generar '
                'sin ese asiento):\n\n- %s' % (partner.display_name, '\n- '.join(faltantes))
            )

    def _evaluar_retencion_iva(self):
        """Evalúa si corresponde Retención IVA para esta Orden de Pago,
        SIN generar ningún registro — se puede llamar en cualquier
        momento (Borrador, En Proceso) para mostrar una vista previa.
        Devuelve un diccionario {factura: datos}, donde 'datos' trae el
        desglose por tasa (5% y 10%, cada una con su Base y Monto) más
        el total combinado — lo que correspondería retener por cada
        Factura si se Confirmara ahora mismo."""
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
        contribucion_esta_op = sum(f._total_gravado_proporcional_gs() for f in self.factura_ids)
        if not self.es_orden_retencion and self.company_id.currency_id.compare_amounts(
            acumulado_previo + contribucion_esta_op, config.l10n_py_retencion_iva_minimo
        ) < 0:
            return resultado

        porcentaje = partner.l10n_py_retencion_iva_porcentaje
        if not porcentaje:
            return resultado

        for factura in self.factura_ids:
            por_tasa = factura._retencion_iva_calcular(porcentaje)
            monto_total = por_tasa['5']['monto'] + por_tasa['10']['monto']
            if not self.currency_id.is_zero(monto_total):
                resultado[factura] = {
                    'por_tasa': por_tasa,
                    'monto_total': monto_total,
                    'monto_gs_total': por_tasa['5']['monto_gs'] + por_tasa['10']['monto_gs'],
                }
        return resultado

    def _calcular_retenciones_iva(self):
        """Genera de verdad los registros de Retención IVA (y la fila en
        Medios) a partir de _evaluar_retencion_iva(). Se ejecuta al
        Confirmar. Si ya existía una fila de un intento anterior (por
        ejemplo, si la Confirmación anterior falló por descuadre), se
        limpia primero para recalcular de cero."""
        self.ensure_one()
        self.medio_ids.filtered('es_retencion').unlink()
        retenciones_a_limpiar = self.env['local_py.retencion_emitida'].search([
            ('orden_pago_id', '=', self.id), ('tipo_retencion', '=', 'iva'), ('estado', '=', 'pendiente'),
        ]).filtered(
            lambda r: not r.es_absorcion_iva and not r.es_absorcion_renta and not r.concepto_renta_id
        )
        for retencion in retenciones_a_limpiar:
            linea = retencion.orden_pago_factura_id.move_line_id
            if linea:
                linea.l10n_py_iva_5_cubierto -= retencion.iva_5_cubierto_aporte
                linea.l10n_py_iva_10_cubierto -= retencion.iva_10_cubierto_aporte
        retenciones_a_limpiar.unlink()

        evaluacion = self._evaluar_retencion_iva()
        if not evaluacion:
            return

        config = self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', self.company_id.id)], limit=1,
        )
        Retencion = self.env['local_py.retencion_emitida']
        for factura, datos in evaluacion.items():
            por_tasa = datos['por_tasa']
            Retencion.create({
                'orden_pago_id': self.id,
                'orden_pago_factura_id': factura.id,
                'fecha': self.fecha,
                'tipo_retencion': 'iva',
                'base_5': por_tasa['5']['base'],
                'monto_5': por_tasa['5']['monto'],
                'base_10': por_tasa['10']['base'],
                'monto_10': por_tasa['10']['monto'],
                'porcentaje': factura.orden_pago_id.partner_id.l10n_py_retencion_iva_porcentaje,
                'monto_gs': datos['monto_gs_total'],
                'concepto_iva_id': (self.partner_id.l10n_py_concepto_iva_id or config.l10n_py_concepto_iva_id).id,
                'iva_5_cubierto_aporte': por_tasa['5']['iva_pendiente_factura'],
                'iva_10_cubierto_aporte': por_tasa['10']['iva_pendiente_factura'],
            })
            if self.currency_id.compare_amounts(datos['monto_total'], 0) > 0:
                # Un Medio de Retención POR FACTURA, no uno combinado — así la
                # conciliación va siempre directo a la factura que corresponde,
                # sin pasar por el reparto genérico entre Facturas y Medios (que
                # no distingue "de dónde viene" cada porción de la Retención).
                self.env['local_py.orden_pago.medio'].create({
                    'orden_pago_id': self.id,
                    'journal_id': config.l10n_py_diario_retencion_iva_id.id,
                    'importe': datos['monto_total'],
                    'es_retencion': True,
                    'retencion_factura_id': factura.id,
                })
            linea = factura.move_line_id
            linea.l10n_py_iva_5_cubierto += por_tasa['5']['iva_pendiente_factura']
            linea.l10n_py_iva_10_cubierto += por_tasa['10']['iva_pendiente_factura']

    def _evaluar_retencion_exterior(self):
        """Evalúa la Retención IVA (a Proveedores del exterior, Concepto
        IVA = IVA.2) y la Retención Renta No Residente (INR) — SIN
        generar nada, para vista previa. Cada una se calcula de forma
        independiente sobre el importe bruto que se está pagando, sin
        acumulado mensual ni Mínimo Imponible (son "Pago Único y
        Definitivo", no un "pago a cuenta"). Devuelve {factura: {'iva':
        {...}|None, 'renta': {...}|None}} — cada bloque ya indica si
        corresponde Absorción o Descuento, según la ficha del
        Proveedor."""
        self.ensure_one()
        resultado = {}
        partner = self.partner_id
        if not partner or not self.fecha:
            return resultado
        es_exterior = bool(partner.l10n_py_concepto_iva_id and partner.l10n_py_concepto_iva_id.codigo == 'IVA.2')
        if not es_exterior:
            return resultado
        config = self._get_config_retencion()
        if not config:
            return resultado

        calcular_iva = bool(
            partner.l10n_py_retencion_iva and config.l10n_py_retencion_iva
            and config.l10n_py_cuenta_gasto_absorcion_id
        )
        calcular_renta = bool(partner.l10n_py_retencion_renta and config.l10n_py_retencion_renta)

        for factura in self.factura_ids:
            datos_factura = {}
            if calcular_iva:
                iva_nocional, monto_header, monto_gs = factura._retencion_absorcion_calcular()
                if not self.currency_id.is_zero(monto_header):
                    datos_factura['iva'] = {
                        'base': iva_nocional, 'monto': monto_header, 'monto_gs': monto_gs,
                        'se_absorbe': partner.l10n_py_se_absorbe_iva,
                    }
            if calcular_renta:
                concepto = factura.move_id.l10n_py_concepto_renta_no_residente_id
                if concepto:
                    calc = factura._retencion_renta_no_residente_calcular(concepto)
                    se_absorbe_renta = partner.l10n_py_se_absorbe_renta
                    monto_usar = calc['monto_absorcion'] if se_absorbe_renta else calc['monto']
                    monto_gs_usar = calc['monto_absorcion_gs'] if se_absorbe_renta else calc['monto_gs']
                    if not self.currency_id.is_zero(monto_usar):
                        datos_factura['renta'] = {
                            'concepto_id': concepto.id, 'base': calc['base'],
                            'monto': monto_usar, 'monto_gs': monto_gs_usar,
                            'se_absorbe': se_absorbe_renta,
                            'importe_pendiente_factura': calc['importe_pendiente_factura'],
                        }
            if datos_factura:
                resultado[factura] = datos_factura
        return resultado

    def _calcular_retenciones_exterior(self):
        """Genera de verdad los registros combinados (IVA + Renta en un
        mismo comprobante de Retención por Factura) y, para cada
        impuesto por separado, el asiento de Absorción (Gasto aparte) o
        la fila de Medios que corresponda (según la ficha del
        Proveedor)."""
        self.ensure_one()
        partner = self.partner_id
        es_exterior = bool(partner.l10n_py_concepto_iva_id and partner.l10n_py_concepto_iva_id.codigo == 'IVA.2')
        viejas = self.env['local_py.retencion_emitida'].search([
            ('orden_pago_id', '=', self.id), ('estado', '=', 'pendiente'),
        ]) if es_exterior else self.env['local_py.retencion_emitida']
        for vieja in viejas:
            if vieja.absorcion_move_id_iva:
                vieja.absorcion_move_id_iva.button_draft()
                vieja.absorcion_move_id_iva.unlink()
            if vieja.absorcion_move_id_renta:
                vieja.absorcion_move_id_renta.button_draft()
                vieja.absorcion_move_id_renta.unlink()
            linea = vieja.orden_pago_factura_id.move_line_id
            if linea:
                linea.l10n_py_renta_importe_cubierto -= vieja.renta_importe_cubierto_aporte
        viejas.unlink()

        evaluacion = self._evaluar_retencion_exterior()
        if not evaluacion:
            return

        partner = self.partner_id
        config = self._get_config_retencion()
        Retencion = self.env['local_py.retencion_emitida']
        for factura, datos in evaluacion.items():
            vals = {
                'orden_pago_id': self.id,
                'orden_pago_factura_id': factura.id,
                'fecha': self.fecha,
                'tipo_retencion': 'iva',
                'monto_gs': 0.0,
            }

            iva_datos = datos.get('iva')
            if iva_datos:
                vals.update({
                    'base_10': iva_datos['base'],
                    'monto_10': iva_datos['monto'],
                    'porcentaje': 100.0,
                    'concepto_iva_id': partner.l10n_py_concepto_iva_id.id,
                    'es_absorcion_iva': iva_datos['se_absorbe'],
                    'monto_gs': iva_datos['monto_gs'],
                })
                if iva_datos['se_absorbe']:
                    move = self._crear_movimiento_absorcion(
                        factura, iva_datos['monto'], 'IVA',
                        config.l10n_py_diario_retencion_iva_id, config.l10n_py_cuenta_gasto_absorcion_id,
                    )
                    vals['absorcion_move_id_iva'] = move.id
                else:
                    self.env['local_py.orden_pago.medio'].create({
                        'orden_pago_id': self.id,
                        'journal_id': config.l10n_py_diario_retencion_iva_id.id,
                        'importe': iva_datos['monto'],
                        'es_retencion': True,
                        'retencion_factura_id': factura.id,
                    })

            renta_datos = datos.get('renta')
            if renta_datos:
                vals.update({
                    'concepto_renta_id': renta_datos['concepto_id'],
                    'base_renta': renta_datos['base'],
                    'monto_renta': renta_datos['monto'],
                    'monto_renta_gs': renta_datos['monto_gs'],
                    'es_absorcion_renta': renta_datos['se_absorbe'],
                    'renta_importe_cubierto_aporte': renta_datos['importe_pendiente_factura'],
                })
                if renta_datos['se_absorbe']:
                    move = self._crear_movimiento_absorcion(
                        factura, renta_datos['monto'], 'Renta',
                        config.l10n_py_diario_retencion_renta_id, config.l10n_py_cuenta_gasto_absorcion_renta_id,
                    )
                    vals['absorcion_move_id_renta'] = move.id
                else:
                    self.env['local_py.orden_pago.medio'].create({
                        'orden_pago_id': self.id,
                        'journal_id': config.l10n_py_diario_retencion_renta_id.id,
                        'importe': renta_datos['monto'],
                        'es_retencion': True,
                        'retencion_factura_id': factura.id,
                    })
                factura.move_line_id.l10n_py_renta_importe_cubierto += renta_datos['importe_pendiente_factura']

            Retencion.create(vals)

    def _crear_movimiento_absorcion(self, factura, monto_header, tipo_label, journal, cuenta_gasto):
        """Asiento paralelo de una Retención con Absorción (IVA o Renta):
        Débito a la Cuenta de Gasto correspondiente, Crédito a la cuenta
        del Diario de Retención — no se concilia contra nada, es un
        costo aparte para la Compañía."""
        self.ensure_one()
        company = self.company_id
        cuenta_retencion = journal.default_account_id
        if not cuenta_retencion:
            raise UserError(
                'El Diario de Retención "%s" no tiene una Cuenta configurada '
                '(Contabilidad > Diarios > esa Cuenta contable).' % journal.name
            )

        es_moneda_extranjera = self.currency_id != company.currency_id
        if es_moneda_extranjera:
            monto_company = self.currency_id._convert(monto_header, company.currency_id, company, self.fecha)
        else:
            monto_company = monto_header

        concepto = 'Retención %s con Absorción - %s - %s' % (tipo_label, self.name, factura.move_id.name)
        move = self.env['account.move'].create({
            'journal_id': journal.id,
            'date': self.fecha,
            'ref': concepto,
            'line_ids': [
                (0, 0, {
                    'name': concepto,
                    'account_id': cuenta_gasto.id,
                    'partner_id': self.partner_id.id,
                    'debit': monto_company,
                    'credit': 0.0,
                    'currency_id': self.currency_id.id,
                    'amount_currency': monto_header if es_moneda_extranjera else monto_company,
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
        return move


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
        if not self.env.context.get('l10n_py_forzar_anulacion_retenciones'):
            retenciones_comprometidas = self.env['local_py.retencion_emitida'].search([
                ('orden_pago_id', '=', self.id), ('estado', 'in', ('levantada', 'json_generado')),
            ])
            if retenciones_comprometidas:
                raise UserError(
                    'Esta Orden de Pago tiene Retenciones ya incluidas en un archivo para la DNIT '
                    '(JSON Generado o Levantada) — no se puede deshacer la Confirmación '
                    'directamente. Primero hay que Anularlas en Localización Paraguay > '
                    'Retenciones Emitidas, y recién ahí se puede continuar.'
                )
        pagos = self.medio_ids.mapped('payment_ids')
        lineas_pago = pagos.mapped('move_id.line_ids')
        if any(lineas_pago.mapped('statement_line_id')):
            raise UserError(
                'Uno o más pagos de esta Orden de Pago ya están conciliados con el extracto '
                'bancario. Deshaga esa conciliación manualmente en Contabilidad > Banco antes '
                'de continuar.'
            )
        pagos_saldo_favor = pagos.filtered('l10n_py_es_saldo_favor')
        if pagos_saldo_favor:
            medios_que_lo_usan = pagos_saldo_favor.mapped('l10n_py_medios_saldo_favor_ids')
            ordenes_dependientes = medios_que_lo_usan.mapped('orden_pago_id') - self
            if ordenes_dependientes:
                raise UserError(
                    'Esta Orden de Pago generó un Saldo a Favor que ya fue usado en otra(s) '
                    'Orden(es) de Pago más reciente(s): %s. Hay que Deshacer la Confirmación '
                    'de esa(s) Orden(es) primero, antes de poder deshacer esta.'
                    % ', '.join(ordenes_dependientes.mapped('name'))
                )
        cheques_emitidos = self.env['local_py.chequera.cheque'].search([
            ('payment_id', 'in', pagos.ids), ('estado', '=', 'emitido'),
        ])
        if cheques_emitidos:
            if self.env.context.get('l10n_py_forzar_anulacion_retenciones'):
                # Esta llamada viene del flujo "Anular la Orden de Pago
                # completa" (wizard de Retenciones) — no hay nadie del otro
                # lado para responder la pregunta de "reutilizar o anular"
                # interactivamente, así que se resuelve sola como
                # Reutilizable (la opción más segura: el número de cheque
                # queda disponible, sin declararlo anulado sin que el
                # usuario lo haya decidido a propósito).
                cheques_emitidos.write({'estado': 'reutilizable'})
            else:
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
        medios_saldo_favor = self.medio_ids.filtered('saldo_favor_payment_id')
        if medios_saldo_favor:
            lineas_origen = medios_saldo_favor.mapped('saldo_favor_payment_id.move_id.line_ids').filtered(
                lambda l: l.account_id.account_type == 'liability_payable'
            )
            lineas_facturas = self.factura_ids.mapped('move_line_id')
            # El Pago original pertenece a OTRA Orden de Pago, y puede tener
            # Saldo a Favor usado por varias Órdenes distintas a la vez — acá
            # se deshace únicamente la conciliación puntual entre ese Pago y
            # las Facturas de ESTA Orden, sin tocar ninguna otra conciliación
            # que ese mismo Pago pueda tener con otras Órdenes.
            partial_reconciles = self.env['account.partial.reconcile'].search([
                '|',
                '&', ('debit_move_id', 'in', lineas_origen.ids), ('credit_move_id', 'in', lineas_facturas.ids),
                '&', ('credit_move_id', 'in', lineas_origen.ids), ('debit_move_id', 'in', lineas_facturas.ids),
            ])
            partial_reconciles.unlink()
        medios_retencion = self.medio_ids.filtered('es_retencion')
        for asiento in medios_retencion.mapped('retencion_move_id'):
            asiento.line_ids.remove_move_reconcile()
            asiento.button_draft()
            asiento.unlink()
        retenciones_op = self.env['local_py.retencion_emitida'].search([
            ('orden_pago_id', '=', self.id), ('tipo_retencion', '=', 'iva'),
        ])
        for asiento in retenciones_op.filtered('absorcion_move_id_iva').mapped('absorcion_move_id_iva'):
            asiento.button_draft()
            asiento.unlink()
        for asiento in retenciones_op.filtered('absorcion_move_id_renta').mapped('absorcion_move_id_renta'):
            asiento.button_draft()
            asiento.unlink()
        retenciones_pendientes = retenciones_op.filtered(lambda r: r.estado == 'pendiente')
        for retencion in retenciones_pendientes:
            linea = retencion.orden_pago_factura_id.move_line_id
            if linea:
                linea.l10n_py_iva_5_cubierto -= retencion.iva_5_cubierto_aporte
                linea.l10n_py_iva_10_cubierto -= retencion.iva_10_cubierto_aporte
                linea.l10n_py_renta_importe_cubierto -= retencion.renta_importe_cubierto_aporte
        retenciones_pendientes.unlink()
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

        def _prioridad_medio(medio):
            # 0 = Saldo a Favor, 1 = Cheque (Diario bancario con Chequera activa),
            # 2 = Transferencia (Diario bancario sin Chequera), 3 = Efectivo (Diario
            # de caja) — así el sobrante, si lo hay, siempre cae en el de menor
            # prioridad presente.
            if medio.saldo_favor_payment_id:
                return 0
            if medio.journal_id.type == 'cash':
                return 3
            return 1 if medio.chequera_id else 2

        medios_normales = medios_normales.sorted(key=_prioridad_medio)

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

        sobrante_por_medio = []
        if j < len(medios_pend):
            medio_j, monto_restante_j = medios_pend[j]
            if currency.compare_amounts(monto_restante_j, 0) > 0:
                sobrante_por_medio.append((medio_j, monto_restante_j))
            for medio_k, monto_k in medios_pend[j + 1:]:
                if currency.compare_amounts(monto_k, 0) > 0:
                    sobrante_por_medio.append((medio_k, monto_k))

        if not self.es_orden_retencion and i < len(facturas_pend):
            raise UserError(
                'No se pudo repartir exactamente el importe de los Medios de Pago contra '
                'las Facturas/Cuotas seleccionadas — falta cobertura. Revise los importes '
                'antes de continuar.'
            )
        if not self.es_orden_retencion and sobrante_por_medio and not self.permite_saldo_a_favor:
            raise UserError(
                'Sobra importe entre los Medios de Pago y las Facturas/Cuotas seleccionadas, '
                'y esta Orden no tiene aprobado dejarlo como Saldo a Favor. Vuelva a "En '
                'Proceso" para que el sistema le pregunte qué hacer con el sobrante.'
            )

        pagos_por_medio = {}
        for factura, medio, monto in asignaciones:
            if medio.saldo_favor_payment_id:
                # No se crea ningún Pago nuevo acá — se reutiliza directo la
                # porción disponible del Pago original (Saldo a Favor de una
                # Orden de Pago anterior), conciliándola contra esta Factura.
                # Si las monedas no coinciden exactamente, Odoo genera solo el
                # asiento de diferencia de cambio correspondiente (mismo
                # mecanismo nativo que usa el resto del reparto).
                linea_pago_payable = medio.saldo_favor_payment_id.move_id.line_ids.filtered(
                    lambda l: l.account_id.account_type == 'liability_payable' and not l.reconciled
                )
                (factura.move_line_id + linea_pago_payable).reconcile()
                continue

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
            pagos_por_medio.setdefault(medio.id, []).append(payment.id)

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
                    'proveedor_id': self.partner_id.id,
                    'moneda_id': self.currency_id.id,
                    'importe_registrado': medio.importe,
                })
                medio.write({'cheque_reutilizar_id': False, 'nro_documento': str(cheque.numero)})

            linea_pago_payable = payment.move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable' and not l.reconciled
            )
            (factura.move_line_id + linea_pago_payable).reconcile()

        for medio, monto in sobrante_por_medio:
            if medio.saldo_favor_payment_id:
                # No corresponde generar nada acá — simplemente no se usó esa
                # porción del Saldo a Favor original, que sigue disponible tal
                # cual estaba (su Pago de origen no se tocó en absoluto).
                continue

            comentario = 'Pago Orden de Pago %s (Saldo a Favor)' % self.name
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
                'l10n_py_es_saldo_favor': True,
            })
            payment.action_post()
            # El saldo disponible depende del saldo pendiente de la línea
            # contable del Pago, que recién queda definitivo al contabilizar
            # (arriba) — se fuerza el recálculo acá para no dejar guardado
            # un 0 de un instante anterior a que existiera el asiento real.
            payment._compute_l10n_py_saldo_favor_disponible()
            if payment.move_id:
                payment.move_id.l10n_py_comentario = comentario
            pagos_por_medio.setdefault(medio.id, []).append(payment.id)
            # No se concilia contra ninguna Factura a propósito — es la porción
            # que excede lo que se le debía al Proveedor, y queda disponible
            # como Saldo a Favor en su cuenta corriente (Odoo lo maneja de forma
            # nativa: un Pago sin conciliar queda "abierto" hasta que se aplique
            # a mano contra una Factura futura).

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
                    'proveedor_id': self.partner_id.id,
                    'moneda_id': self.currency_id.id,
                    'importe_registrado': medio.importe,
                })
                medio.write({'cheque_reutilizar_id': False, 'nro_documento': str(cheque.numero)})

        # Si un mismo Medio (por ejemplo, un cheque) tuvo que repartirse en
        # más de un Pago para cubrir varias Facturas, se agrupan en un Lote
        # de Pago — así, al conciliar el extracto bancario, se hacen
        # coincidir todos juntos contra el único movimiento real del banco,
        # en vez de tener que buscarlos y emparejarlos sueltos uno por uno.
        for medio_id, payment_ids in pagos_por_medio.items():
            if len(payment_ids) <= 1:
                continue
            if 'account.batch.payment' not in self.env:
                # La función "Lotes de Pago" no está habilitada en Ajustes >
                # Contabilidad — se omite el agrupamiento (no es un dato
                # obligatorio para conciliar, solo una ayuda) en vez de
                # interrumpir la generación normal de los Pagos.
                continue
            pagos = self.env['account.payment'].browse(payment_ids)
            self.env['account.batch.payment'].create({
                'journal_id': pagos[0].journal_id.id,
                'payment_ids': [(6, 0, pagos.ids)],
                'batch_type': 'outbound',
                'payment_method_id': pagos[0].payment_method_id.id,
                'date': self.fecha,
            })

    def _generar_pagos_a_cuenta(self):
        """Genera los Pagos de una Orden de tipo "Pago a Cuenta" — sin
        Proveedor, sin Facturas, y sin conciliación contra nada externo:
        cada Pago va directo contra la Cuenta elegida en la cabecera
        (posible porque esa Cuenta tiene que ser de tipo "Por Pagar" o
        "Por Cobrar" — el único tipo que Odoo acepta como contraparte de
        un Pago sin Contacto asociado).

        AVISO: mecanismo nuevo y menos probado que el resto del módulo
        — revisar con atención los primeros asientos que genere en la
        práctica."""
        self.ensure_one()
        AccountPayment = self.env['account.payment'].with_context(l10n_py_allow_orden_pago_write=True)

        for medio in self.medio_ids:
            comentario = '%s - Orden de Pago %s' % (self.referencia_pago_cuenta, self.name)
            payment = AccountPayment.create({
                'payment_type': 'outbound',
                'partner_id': False,
                'destination_account_id': self.cuenta_pago_id.id,
                'journal_id': medio.journal_id.id,
                'amount': medio.importe,
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
                    'proveedor_id': False,
                    'moneda_id': self.currency_id.id,
                    'importe_registrado': medio.importe,
                })
                medio.write({'cheque_reutilizar_id': False, 'nro_documento': str(cheque.numero)})

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

        tipo_label = 'Renta' if journal == self._get_config_retencion().l10n_py_diario_retencion_renta_id else 'IVA'
        concepto = 'Retención %s - %s' % (tipo_label, self.name)
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
