# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class TllrFcOt(models.Model):
    """Orden de trabajo.

    En la Fase 2 la OT nace de la recepción, en estado En espera, con los
    servicios solicitados como referencia. El resto del ciclo (puestos,
    personal, repuestos, horas, control de calidad, facturación y entrega)
    se incorpora en las fases siguientes.
    """
    _name = 'tllr_fc.ot'
    _description = "Orden de trabajo"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'tllr_fc.mixin.wizard']
    _order = 'id desc'
    _check_company_auto = True

    name = fields.Char(
        string="Número", required=True, readonly=True, copy=False, default="Nuevo")
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True, index=True,
        default=lambda self: self.env.company)
    state = fields.Selection([
        ('espera', "En espera"),
        ('proceso', "En proceso"),
        ('calidad', "En control de calidad"),
        ('listo', "Listo para entrega"),
        ('entregado', "Entregado"),
        ('cancelada', "Cancelada"),
    ], string="Estado", required=True, default='espera', copy=False,
        tracking=True, index=True)
    tipo = fields.Selection([
        ('cliente', "Cliente"),
        ('interno', "Interno"),
        ('garantia', "Garantía"),
    ], string="Tipo de OT", required=True, default='cliente', tracking=True)
    recepcion_id = fields.Many2one(
        'tllr_fc.recepcion', string="Recepción", required=True, readonly=True,
        copy=False, ondelete='restrict', index=True)
    vehiculo_id = fields.Many2one(
        'tllr_fc.vehiculo', string="Vehículo", required=True, readonly=True,
        ondelete='restrict', check_company=True, index=True)
    partner_id = fields.Many2one(
        'res.partner', string="Cliente a facturar", required=True, readonly=True,
        ondelete='restrict', index=True)
    partner_secundario_id = fields.Many2one(
        'res.partner', string="Contacto secundario", readonly=True, ondelete='restrict')
    combustible_ingreso = fields.Selection([
        ('reserva', "Reserva"),
        ('1_4', "1/4"),
        ('1_2', "1/2"),
        ('3_4', "3/4"),
        ('lleno', "Lleno"),
    ], string="Combustible al ingreso", readonly=True)
    kilometraje_ingreso = fields.Integer(string="Kilometraje al ingreso", readonly=True)
    fecha_ingreso = fields.Datetime(string="Fecha de ingreso", readonly=True)
    fecha_entrega = fields.Datetime(string="Fecha de entrega", readonly=True, copy=False)
    dias_taller = fields.Integer(string="Días en taller", compute='_compute_dias_taller')
    motivo_cancelacion_id = fields.Many2one(
        'tllr_fc.motivo', string="Motivo de cancelación", readonly=True, copy=False,
        domain="[('tipo', '=', 'cancelacion')]", ondelete='restrict')
    servicio_ids = fields.One2many(
        'tllr_fc.ot.servicio', 'ot_id', string="Servicios", copy=False)
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', string="Moneda")
    responsable_id = fields.Many2one(
        'tllr_fc.personal', string="Responsable", tracking=True, check_company=True,
        copy=False, help="Una persona por OT. Debe ser distinta del personal asignado a los "
                         "puestos (el supervisor puede autorizar una excepción).")
    requiere_qc = fields.Boolean(
        string="Requiere control de calidad", tracking=True, copy=False,
        help="El supervisor lo marca para exigir el control aunque el ajuste del tipo de OT "
             "no lo pida.")
    puesto_line_ids = fields.One2many(
        'tllr_fc.ot.puesto', 'ot_id', string="Puestos", copy=False)
    puesto_activo_id = fields.Many2one(
        'tllr_fc.puesto', string="Puesto activo", compute='_compute_puesto_activo',
        inverse='_inverse_puesto_activo', store=True, index=True,
        group_expand='_read_group_puesto_activo_id')
    personal_ids = fields.Many2many(
        'tllr_fc.personal', string="Personal asignado", compute='_compute_personal',
        store=True)
    producto_ids = fields.One2many(
        'tllr_fc.ot.producto', 'ot_id', string="Repuestos, insumos y accesorios", copy=False)
    descripcion_trabajos = fields.Text(string="Trabajos realizados")
    hora_ids = fields.One2many('tllr_fc.ot.hora', 'ot_id', string="Horas trabajadas", copy=False)
    herramienta_danada_ids = fields.One2many(
        'tllr_fc.ot.herramienta_danada', 'ot_id', string="Herramientas dañadas", copy=False)
    aprobacion_ids = fields.One2many(
        'tllr_fc.ot.aprobacion', 'ot_id', string="Aprobaciones de adicionales", copy=False)
    control_ids = fields.One2many(
        'tllr_fc.control_calidad', 'ot_id', string="Controles de calidad", copy=False)
    control_count = fields.Integer(string="Controles", compute='_compute_control_count')
    horas_reales = fields.Float(string="Horas reales", compute='_compute_horas')
    costo_horas = fields.Monetary(
        string="Costo de horas", currency_field='currency_id', compute='_compute_horas',
        groups='tllr_fc.group_supervisor')
    aviso_horas = fields.Char(string="Aviso de horas", compute='_compute_horas')
    adicionales_pendientes = fields.Integer(
        string="Adicionales pendientes de aprobación", compute='_compute_adicionales_pendientes',
        store=True)
    detenida = fields.Boolean(string="Detenida", readonly=True, copy=False, tracking=True)
    motivo_detencion_id = fields.Many2one(
        'tllr_fc.motivo', string="Motivo de detención", readonly=True, copy=False,
        domain="[('tipo', '=', 'detencion')]", ondelete='restrict')
    fecha_reanudacion_estimada = fields.Date(
        string="Reanudación estimada", readonly=True, copy=False)
    detenida_desde = fields.Datetime(string="Detenida desde", readonly=True, copy=False)
    dias_detenida = fields.Float(
        string="Días detenida (acumulado)", readonly=True, copy=False, digits=(16, 2))
    dias_detenida_total = fields.Float(
        string="Días detenida", compute='_compute_dias_detenida_total', digits=(16, 2))
    ot_origen_id = fields.Many2one(
        'tllr_fc.ot', string="OT original", readonly=True, copy=False, ondelete='restrict',
        help="En una OT de garantía, la OT que originó el reclamo.")
    ot_garantia_ids = fields.One2many(
        'tllr_fc.ot', 'ot_origen_id', string="OT de garantía", readonly=True)
    cerrada_facturar = fields.Boolean(
        string="Cerrada para facturar", readonly=True, copy=False, tracking=True)
    fecha_cierre_facturar = fields.Datetime(
        string="Fecha de cierre para facturar", readonly=True, copy=False)
    liquidada = fields.Boolean(
        string="Cancelada con liquidación", readonly=True, copy=False, tracking=True)
    entrega_habilitada = fields.Boolean(
        string="Entrega habilitada", readonly=True, copy=False, tracking=True,
        help="En una OT cancelada: se eligió entregar el vehículo al cliente. "
             "Se responde al cancelar y un supervisor puede habilitarla después.")
    kilometraje_salida = fields.Integer(string="Kilometraje de salida", readonly=True, copy=False)
    puede_refacturar = fields.Boolean(
        string="Puede refacturarse", compute='_compute_puede_refacturar',
        help="La factura de la OT fue anulada con una nota de crédito total y no hay otra activa.")
    factura_ids = fields.One2many(
        'account.move', 'tllr_fc_ot_id', string="Facturas",
        domain=[('move_type', 'in', ('out_invoice', 'out_refund'))], readonly=True)
    estado_facturacion = fields.Selection(
        [('sin_facturar', "Sin facturar"), ('borrador', "Factura en borrador"),
         ('confirmada', "Factura confirmada")],
        string="Facturación", compute='_compute_estado_facturacion')
    estado_pago = fields.Selection(
        [('no_pagada', "No pagada"), ('parcial', "Pago parcial"), ('pagada', "Pagada")],
        string="Pago", compute='_compute_estado_facturacion')
    entrega_ids = fields.One2many('tllr_fc.entrega', 'ot_id', string="Entregas", readonly=True)
    entrega_count = fields.Integer(string="Cantidad de entregas", compute='_compute_conteos')
    garantia_ids = fields.One2many('tllr_fc.garantia', 'ot_id', string="Garantías", readonly=True)
    traslado_count = fields.Integer(string="Traslados de stock", compute='_compute_traslado_count')
    garantia_count = fields.Integer(string="Cantidad de garantías", compute='_compute_conteos')
    descuento_cliente = fields.Float(
        string="Descuento del cliente (%)", related='partner_id.tllr_fc_descuento')
    total_servicios = fields.Monetary(
        string="Total servicios", currency_field='currency_id', compute='_compute_totales')
    total_productos = fields.Monetary(
        string="Total repuestos e insumos", currency_field='currency_id',
        compute='_compute_totales')
    total = fields.Monetary(
        string="Total", currency_field='currency_id', compute='_compute_totales')
    horas_estandar = fields.Float(string="Horas estándar", compute='_compute_totales')
    lineas_cobrar = fields.Integer(
        string="Líneas a cobrar", compute='_compute_requiere_factura',
        help="En una OT de garantía, líneas marcadas «Cobrar al cliente».")
    requiere_factura = fields.Boolean(
        string="Requiere factura", compute='_compute_requiere_factura',
        help="Las OT de cliente siempre; las de garantía solo si tienen líneas a cobrar.")
    ingreso = fields.Monetary(
        string="Ingreso", currency_field='currency_id', compute='_compute_rentabilidad',
        groups='tllr_fc.group_supervisor',
        help="Total facturado (impuesto incluido); estimado desde la OT hasta que se confirme la factura.")
    costo_propio = fields.Monetary(
        string="Costo de la OT", currency_field='currency_id', compute='_compute_rentabilidad',
        groups='tllr_fc.group_supervisor',
        help="Repuestos, insumos y accesorios consumidos y costo de los servicios, en negativo. "
             "En una OT de garantía, solo lo que se cobra al cliente.")
    mano_obra = fields.Monetary(
        string="Mano de obra", currency_field='currency_id', compute='_compute_rentabilidad',
        groups='tllr_fc.group_supervisor',
        help="Costo de las horas trabajadas (en negativo).")
    impuesto = fields.Monetary(
        string="Impuesto", currency_field='currency_id', compute='_compute_rentabilidad',
        groups='tllr_fc.group_supervisor',
        help="Impuesto total de las facturas confirmadas (estimado si aún no hay factura), en negativo.")
    ajustes_costo = fields.Monetary(
        string="Ajustes", currency_field='currency_id', compute='_compute_rentabilidad',
        groups='tllr_fc.group_supervisor',
        help="Suma de los ajustes de costo de la OT, en negativo.")
    costo_garantia_absorbido = fields.Monetary(
        string="Costo de garantía no cobrado", currency_field='currency_id',
        compute='_compute_rentabilidad', groups='tllr_fc.group_supervisor', recursive=True,
        help="En una OT de garantía: costo que no se cobra y se suma a la OT original.")
    costo_garantias_origen = fields.Monetary(
        string="Costo de garantías de esta OT", currency_field='currency_id',
        compute='_compute_rentabilidad', groups='tllr_fc.group_supervisor',
        help="Costo no cobrado de las OT de garantía que reclamaron sobre esta OT.")
    margen = fields.Monetary(
        string="Margen", currency_field='currency_id', compute='_compute_rentabilidad',
        groups='tllr_fc.group_supervisor')
    notas_credito = fields.Monetary(
        string="Notas de crédito", currency_field='currency_id', compute='_compute_rentabilidad',
        groups='tllr_fc.group_supervisor',
        help="Notas de crédito parciales confirmadas, en negativo. Ya están restadas del ingreso.")
    nota_credito_count = fields.Integer(
        string="Cantidad de notas de crédito", compute='_compute_nota_credito_count')
    margen_porcentaje = fields.Float(
        string="Margen (%)", compute='_compute_rentabilidad', groups='tllr_fc.group_supervisor')
    servicios_resumen = fields.Char(string="Servicios (resumen)", compute='_compute_resumen')
    servicios_pendientes = fields.Integer(
        string="Servicios pendientes", compute='_compute_resumen')
    tiene_adicionales = fields.Boolean(string="Con adicionales", compute='_compute_resumen')

    @api.depends('fecha_ingreso', 'fecha_entrega', 'state')
    def _compute_dias_taller(self):
        ahora = fields.Datetime.now()
        for ot in self:
            if not ot.fecha_ingreso:
                ot.dias_taller = 0
                continue
            fin = ot.fecha_entrega or ahora
            ot.dias_taller = max((fin - ot.fecha_ingreso).days, 0)

    @api.depends('control_ids')
    def _compute_control_count(self):
        for ot in self:
            ot.control_count = len(ot.control_ids)

    @api.depends('hora_ids.horas', 'hora_ids.fecha', 'hora_ids.personal_id', 'hora_ids.aviso')
    def _compute_horas(self):
        for ot in self:
            horas = ot.hora_ids.sudo()
            ot.horas_reales = sum(horas.mapped('horas'))
            ot.costo_horas = sum(horas.mapped('costo'))
            avisos = [a for a in horas.mapped('aviso') if a]
            ot.aviso_horas = ' '.join(sorted(set(avisos))) if avisos else False

    @api.depends('tipo', 'servicio_ids.facturable', 'producto_ids.facturable')
    def _compute_requiere_factura(self):
        for ot in self:
            cobrar = 0
            if ot.tipo == 'garantia':
                cobrar = (len(ot.servicio_ids.filtered('facturable'))
                          + len(ot.producto_ids.filtered('facturable')))
            ot.lineas_cobrar = cobrar
            ot.requiere_factura = ot.tipo == 'cliente' or (ot.tipo == 'garantia' and cobrar > 0)

    def _tllr_fc_horas_reparto(self):
        """Costo de las horas repartido: (imputable a lo cobrado, no cobrado).

        - Cliente: todo a lo cobrado (se cobra la OT).
        - Interna: todo a no cobrado (gasto interno).
        - Garantía: en proporción a las horas estándar de los servicios cobrados.
        """
        self.ensure_one()
        ot = self.sudo()
        horas = sum(ot.hora_ids.mapped('costo'))
        if ot.tipo == 'cliente':
            return horas, 0.0
        if ot.tipo == 'interno':
            return 0.0, horas
        servicios = ot.servicio_ids
        total = sum(servicios.mapped('horas_estandar'))
        cobradas = sum(servicios.filtered('facturable').mapped('horas_estandar'))
        cobrado = horas * cobradas / total if total else 0.0
        return cobrado, horas - cobrado

    def _tllr_fc_desglose_costos(self):
        """Costo de la OT desglosado: materiales y servicios, mano de obra, ajustes, no cobrado.

        Valores positivos. En una OT de garantía, materiales y mano de obra son solo lo que se
        cobra al cliente; el resto es el costo absorbido.
        """
        self.ensure_one()
        ot = self.sudo()
        servicios = ot.servicio_ids
        productos = ot.producto_ids
        horas_cobradas, horas_no_cobradas = ot._tllr_fc_horas_reparto()
        ajustes = sum(ot.ajuste_ids.mapped('monto'))
        if ot.tipo != 'garantia':
            materiales = sum(productos.mapped('costo')) + sum(servicios.mapped('costo_efectivo'))
            return {'materiales': materiales, 'mano_obra': horas_cobradas + horas_no_cobradas,
                    'ajustes': ajustes, 'absorbido': 0.0}
        cobrados_s = servicios.filtered('facturable')
        cobrados_p = productos.filtered('facturable')
        return {
            'materiales': sum(cobrados_p.mapped('costo')) + sum(cobrados_s.mapped('costo_efectivo')),
            'mano_obra': horas_cobradas,
            'ajustes': ajustes,
            'absorbido': (sum((productos - cobrados_p).mapped('costo'))
                          + sum((servicios - cobrados_s).mapped('costo_efectivo'))
                          + horas_no_cobradas),
        }

    def _tllr_fc_costos(self):
        """Reparte el costo de la OT: (propio, no cobrado de garantía)."""
        self.ensure_one()
        d = self._tllr_fc_desglose_costos()
        return d['materiales'] + d['mano_obra'] + d['ajustes'], d['absorbido']

    def _tllr_fc_ingreso_impuesto(self):
        """(ingreso, impuesto): total e impuesto de las facturas confirmadas de la OT.

        Sin factura confirmada se estiman con los precios de la OT y los impuestos de venta
        de cada producto.
        """
        self.ensure_one()
        ot = self.sudo()
        if ot.tipo == 'interno':
            return 0.0, 0.0
        confirmadas = ot._tllr_fc_facturas().filtered(lambda m: m.state == 'posted')
        if confirmadas:
            # Las notas de crédito (parciales) vienen con signo negativo y restan.
            documentos = confirmadas | ot._tllr_fc_notas_credito()
            return (sum(documentos.mapped('amount_total_signed')),
                    sum(documentos.mapped('amount_tax_signed')))
        if ot.state == 'cancelada':
            # Una OT cancelada no estima ingreso: solo cuenta lo realmente facturado.
            return 0.0, 0.0
        impuesto = 0.0
        for linea in list(ot.servicio_ids) + list(ot.producto_ids):
            if not linea.subtotal:
                continue
            impuestos = linea.product_id.taxes_id.filtered(
                lambda t: t.company_id == ot.company_id)
            if impuestos:
                calculo = impuestos.compute_all(linea.subtotal, currency=ot.currency_id)
                impuesto += sum(t['amount'] for t in calculo['taxes'])
        return ot.total + impuesto, impuesto

    @api.depends('tipo', 'state', 'total', 'servicio_ids.costo_efectivo', 'servicio_ids.facturable',
                 'servicio_ids.subtotal', 'producto_ids.subtotal',
                 'producto_ids.costo', 'producto_ids.facturable', 'hora_ids.costo',
                 'ajuste_ids.monto', 'factura_ids.state', 'factura_ids.amount_total_signed',
                 'factura_ids.amount_tax_signed', 'factura_ids.payment_state',
                 'factura_ids.move_type', 'ot_garantia_ids.state', 'ot_garantia_ids.costo_garantia_absorbido')
    def _compute_rentabilidad(self):
        for ot in self:
            d = ot._tllr_fc_desglose_costos()
            origen = sum(
                garantia._tllr_fc_costos()[1] for garantia in ot.sudo().ot_garantia_ids
                if garantia.state != 'cancelada')
            ingreso, impuesto = ot._tllr_fc_ingreso_impuesto()
            ot.notas_credito = sum(ot._tllr_fc_notas_credito().mapped('amount_total_signed'))
            # Ingreso en positivo; todos los costos en negativo.
            ot.ingreso = ingreso
            ot.costo_propio = -d['materiales']
            ot.mano_obra = -d['mano_obra']
            ot.impuesto = -impuesto
            ot.ajustes_costo = -d['ajustes']
            ot.costo_garantia_absorbido = d['absorbido']
            ot.costo_garantias_origen = -origen
            ot.margen = (ingreso - d['materiales'] - d['mano_obra'] - impuesto
                         - origen - d['ajustes'])
            # Sin ingreso y con pérdida: -100 % (la pérdida iguala lo gastado).
            if ingreso:
                ot.margen_porcentaje = ot.margen / ingreso
            else:
                ot.margen_porcentaje = -1.0 if ot.margen < -0.005 else 0.0

    @api.depends('servicio_ids.state_aprobacion', 'producto_ids.state_aprobacion')
    def _compute_adicionales_pendientes(self):
        for ot in self:
            ot.adicionales_pendientes = (
                len(ot.servicio_ids.filtered(lambda s: s.state_aprobacion == 'pendiente'))
                + len(ot.producto_ids.filtered(lambda p: p.state_aprobacion == 'pendiente')))

    @api.depends('detenida', 'detenida_desde', 'dias_detenida')
    def _compute_dias_detenida_total(self):
        ahora = fields.Datetime.now()
        for ot in self:
            actual = 0.0
            if ot.detenida and ot.detenida_desde:
                actual = (ahora - ot.detenida_desde).total_seconds() / 86400.0
            ot.dias_detenida_total = ot.dias_detenida + actual

    @api.depends('factura_ids.state', 'factura_ids.payment_state')
    def _compute_estado_facturacion(self):
        for ot in self:
            facturas = ot.sudo()._tllr_fc_facturas().filtered(
                lambda m: m.move_type == 'out_invoice' and m.state != 'cancel')
            confirmadas = facturas.filtered(lambda m: m.state == 'posted')
            if confirmadas:
                ot.estado_facturacion = 'confirmada'
                pagos = confirmadas.mapped('payment_state')
                if all(p in ('paid', 'in_payment') for p in pagos):
                    ot.estado_pago = 'pagada'
                elif any(p in ('paid', 'in_payment', 'partial') for p in pagos):
                    ot.estado_pago = 'parcial'
                else:
                    ot.estado_pago = 'no_pagada'
            else:
                ot.estado_facturacion = 'borrador' if facturas else 'sin_facturar'
                ot.estado_pago = 'no_pagada'

    @api.depends('factura_ids.state', 'factura_ids.move_type')
    def _compute_nota_credito_count(self):
        for ot in self:
            ot.nota_credito_count = len(ot.sudo().factura_ids.filtered(
                lambda m: m.move_type == 'out_refund' and m.state == 'posted'))

    def action_ver_notas_credito(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': "Notas de crédito",
            'res_model': 'account.move', 'view_mode': 'list,form',
            'domain': [('id', 'in', self.sudo().factura_ids.filtered(
                lambda m: m.move_type == 'out_refund').ids)],
            'context': {'default_move_type': 'out_refund', 'create': False},
        }

    def _compute_traslado_count(self):
        datos = self.env['stock.picking'].sudo()._read_group(
            [('tllr_fc_ot_id', 'in', self.ids)], ['tllr_fc_ot_id'], ['__count'])
        conteos = {ot.id: cantidad for ot, cantidad in datos}
        for ot in self:
            ot.traslado_count = conteos.get(ot.id, 0)

    @api.depends('entrega_ids', 'garantia_ids')
    def _compute_conteos(self):
        for ot in self:
            ot.entrega_count = len(ot.entrega_ids)
            ot.garantia_count = len(ot.garantia_ids)

    @api.depends('puesto_line_ids.state', 'puesto_line_ids.puesto_id', 'state')
    def _compute_puesto_activo(self):
        for ot in self:
            if ot.state in ('espera', 'calidad', 'listo'):
                ot.puesto_activo_id = ot.company_id._tllr_fc_puesto_sistema(ot.state)
                continue
            activa = ot.puesto_line_ids.filtered(lambda l: l.state == 'activo')[:1]
            ot.puesto_activo_id = activa.puesto_id

    personal_horas_ids = fields.Many2many(
        'tllr_fc.personal', string="Personal que puede cargar horas",
        compute='_compute_personal_horas')

    @api.depends('state', 'personal_ids', 'responsable_id',
                 'control_ids.responsable_id', 'control_ids.state')
    def _compute_personal_horas(self):
        for ot in self:
            if ot.state == 'calidad':
                ot.personal_horas_ids = ot.control_ids.filtered(
                    lambda c: c.state == 'borrador').responsable_id
            else:
                ot.personal_horas_ids = ot.personal_ids | ot.responsable_id

    @api.depends('puesto_line_ids.personal_ids')
    def _compute_personal(self):
        for ot in self:
            ot.personal_ids = ot.puesto_line_ids.personal_ids

    @api.depends('servicio_ids.subtotal', 'servicio_ids.horas_estandar',
                 'producto_ids.subtotal')
    def _compute_totales(self):
        for ot in self:
            ot.total_servicios = sum(ot.servicio_ids.mapped('subtotal'))
            ot.total_productos = sum(ot.producto_ids.mapped('subtotal'))
            ot.total = ot.total_servicios + ot.total_productos
            ot.horas_estandar = sum(ot.servicio_ids.mapped('horas_estandar'))

    @api.depends('servicio_ids.product_id', 'servicio_ids.estado', 'servicio_ids.adicional',
                 'producto_ids.adicional')
    def _compute_resumen(self):
        for ot in self:
            ot.servicios_resumen = ', '.join(
                ot.servicio_ids.filtered(lambda s: s.estado != 'no_realizado')
                .mapped('product_id.name'))
            ot.servicios_pendientes = len(ot.servicio_ids.filtered(
                lambda s: s.estado == 'pendiente'))
            ot.tiene_adicionales = bool(
                ot.servicio_ids.filtered('adicional') or ot.producto_ids.filtered('adicional'))

    @api.model
    def _read_group_puesto_activo_id(self, puestos, domain):
        """El tablero muestra todos los puestos activos como columnas."""
        normales = self.env['tllr_fc.puesto'].search(
            [('company_id', 'in', self.env.companies.ids),
             ('es_calidad', '=', False), ('sistema', '=', False)])
        espera = calidad = listo = self.env['tllr_fc.puesto']
        for compania in self.env.companies:
            espera |= compania._tllr_fc_puesto_sistema('espera')
            calidad |= compania._tllr_fc_puesto_sistema('calidad')
            listo |= compania._tllr_fc_puesto_sistema('listo')
        return espera | normales | calidad | listo

    # ------------------------------------------------------------------
    # Tablero: arrastre de tarjetas
    # ------------------------------------------------------------------
    def _inverse_puesto_activo(self):
        """Arrastrar una tarjeta a otra columna del tablero.

        Las columnas son En espera, los puestos reales, Control de calidad y Listo
        para entrega. Solo el supervisor mueve tarjetas y solo entre columnas
        contiguas del recorrido de la OT; cualquier incumplimiento revierte el
        movimiento:
        - En espera → primer puesto: inicia la OT.
        - Puesto → puesto siguiente: termina el puesto activo.
        - Último puesto → Control de calidad (o Listo si la OT no exige control).
        - Control de calidad → último puesto / Listo → Control de calidad /
          primer puesto → En espera: vuelven un estado atrás (con la nota
          «Movida en el tablero»).
        """
        for ot in self:
            destino = ot.puesto_activo_id
            actual = ot.puesto_line_ids.filtered(lambda l: l.state == 'activo')[:1]
            if ot.state in ('espera', 'calidad', 'listo'):
                origen = ot.company_id._tllr_fc_puesto_sistema(ot.state)
            else:
                origen = actual.puesto_id
            if destino == origen:
                continue
            if not self._tllr_fc_es_supervisor():
                raise AccessError(
                    "Solo el supervisor o el administrador de taller pueden mover las OT "
                    "entre puestos.")
            if ot.state in ('entregado', 'cancelada'):
                raise UserError("La OT %s está cerrada: no se puede mover." % ot.name)
            if not destino:
                raise UserError(
                    "La OT %s no puede quedar «Sin puesto»: usá una de las columnas." % ot.name)
            lineas = ot.puesto_line_ids.sorted(lambda l: (l.sequence, l.id))
            ultimo = lineas[-1:].puesto_id
            primero = lineas[:1].puesto_id
            ctx = ot.with_context(tllr_fc_excepcion=True)
            sistema = destino.sistema or ('calidad' if destino.es_calidad else False)
            if sistema == 'espera':
                if ot.state != 'proceso' or actual.puesto_id != primero:
                    raise UserError(
                        "La OT %s solo vuelve a «En espera» desde su primer puesto. Para otros "
                        "retrocesos usá «Retroceder puesto» o «Volver atrás»." % ot.name)
                ctx._tllr_fc_ejecutar_volver_estado("Movida en el tablero")
            elif sistema == 'calidad':
                if ot.state == 'listo':
                    ctx._tllr_fc_ejecutar_volver_estado("Movida en el tablero")
                    continue
                if ot.state != 'proceso':
                    raise UserError(
                        "La OT %s no está en proceso: no se puede pasar a control de calidad." % ot.name)
                if lineas.filtered(lambda l: l.state == 'pendiente'):
                    raise UserError(
                        "La OT %s todavía tiene puestos pendientes: solo se pasa a control de "
                        "calidad desde el último puesto." % ot.name)
                if not ot._tllr_fc_exige_qc():
                    raise UserError(
                        "La OT %s no requiere control de calidad (activá «Requiere control de "
                        "calidad» en la OT) o pasala a «Listo para entrega»." % ot.name)
                ot._tllr_fc_verificar_puesto_terminable()
                ot._tllr_fc_avanzar_puesto()
            elif sistema == 'listo':
                if (ot.state != 'proceso' or lineas.filtered(lambda l: l.state == 'pendiente')
                        or ot._tllr_fc_exige_qc()):
                    raise UserError(
                        "La OT %s solo pasa a «Listo para entrega» desde el último puesto y si no "
                        "exige control de calidad; si lo exige, confirmá el control." % ot.name)
                ot._tllr_fc_verificar_puesto_terminable()
                ot._tllr_fc_avanzar_puesto()
            else:
                # Destino: un puesto real.
                if ot.state == 'espera':
                    if destino != primero:
                        raise UserError(
                            "La OT %s se inicia en su primer puesto (%s)." % (ot.name, primero.name))
                    resultado = ot.action_iniciar()
                    if isinstance(resultado, dict):
                        raise UserError(
                            "La OT %s necesita una autorización para iniciarse: iniciala desde "
                            "el formulario de la OT." % ot.name)
                elif ot.state == 'calidad':
                    if destino != ultimo:
                        raise UserError(
                            "La OT %s solo puede volver al último puesto de su recorrido (%s)." % (
                                ot.name, ultimo.name or "ninguno"))
                    ctx._tllr_fc_ejecutar_volver_estado("Movida en el tablero")
                elif ot.state == 'proceso':
                    siguiente = lineas.filtered(lambda l: l.state == 'pendiente')[:1]
                    if not siguiente or siguiente.puesto_id != destino:
                        raise UserError(
                            "La OT %s solo puede pasar al puesto que sigue en su recorrido (%s). "
                            "Para volver a un puesto anterior usá «Retroceder puesto»." % (
                                ot.name, siguiente.puesto_id.name or "ninguno"))
                    ot._tllr_fc_verificar_puesto_terminable()
                    ot._tllr_fc_avanzar_puesto(avanzar_ot=False)
                else:
                    raise UserError(
                        "La OT %s está «Lista para entrega»: usá «Volver atrás» para reabrirla." % ot.name)

    # ------------------------------------------------------------------
    # Recorrido por los puestos
    # ------------------------------------------------------------------
    def _tllr_fc_es_supervisor(self):
        return self.env.user.has_group('tllr_fc.group_supervisor')

    def _tllr_fc_verificar_no_detenida(self, accion="continuar"):
        self.ensure_one()
        if self.detenida:
            raise UserError(
                "La OT %s está detenida (%s): no se puede %s hasta reanudarla." % (
                    self.name, self.motivo_detencion_id.name or '', accion))

    def _tllr_fc_verificar_puesto_terminable(self):
        self.ensure_one()
        actual = self.puesto_line_ids.filtered(lambda l: l.state == 'activo')[:1]
        if not actual:
            raise UserError("La OT %s no tiene un puesto activo." % self.name)
        pendientes = actual.servicio_ids.filtered(lambda s: s.estado == 'pendiente')
        if pendientes:
            raise UserError(
                "Faltan servicios por terminar en el puesto «%s»: %s." % (
                    actual.name, ', '.join(pendientes.mapped('product_id.name'))))
        actual._tllr_fc_validar_cierre()
        return actual

    def _tllr_fc_avanzar_puesto(self, avanzar_ot=True):
        """Termina el puesto activo y activa el siguiente.

        Si era el último y `avanzar_ot`, la OT sale de proceso.
        """
        self.ensure_one()
        self._tllr_fc_verificar_no_detenida("avanzar de puesto")
        ahora = fields.Datetime.now()
        actual = self.puesto_line_ids.filtered(lambda l: l.state == 'activo')[:1]
        siguiente = self.puesto_line_ids.filtered(lambda l: l.state == 'pendiente')[:1]
        lineas = self.with_context(tllr_fc_permitir_write=True).puesto_line_ids
        actual = lineas.browse(actual.id)
        siguiente = lineas.browse(siguiente.id)
        actual.write({'state': 'terminado', 'fecha_fin': ahora})
        if siguiente:
            siguiente.write({'state': 'activo', 'fecha_inicio': ahora})
            self.message_post(body="Puesto «%s» terminado. Pasa al puesto «%s»." % (
                actual.name, siguiente.name))
            self.producto_ids._tllr_fc_sincronizar_stock()
        else:
            self.message_post(body="Puesto «%s» terminado (último puesto)." % actual.name)
            if avanzar_ot:
                self._tllr_fc_finalizar_recorrido()

    def _tllr_fc_exige_qc(self):
        self.ensure_one()
        return bool(
            self.requiere_qc
            or self.company_id['tllr_fc_qc_%s' % self.tipo])

    def _tllr_fc_finalizar_recorrido(self):
        self.ensure_one()
        sin_cerrar = self.servicio_ids.filtered(lambda s: s.estado == 'pendiente')
        if sin_cerrar:
            raise UserError(
                "No se puede terminar la OT: hay servicios pendientes (%s)." % ', '.join(
                    sin_cerrar.mapped('product_id.name')))
        # Lo reservado y no usado vuelve al stock.
        self.state = 'calidad' if self._tllr_fc_exige_qc() else 'listo'
        self.producto_ids._tllr_fc_sincronizar_stock()
        if self.state == 'calidad':
            control = self._tllr_fc_crear_control()
            self.message_post(body="Todos los puestos terminaron: la OT pasa a control de calidad (%s)."
                              % control.name)
        else:
            self.message_post(body="Todos los puestos terminaron: la OT está lista para entrega.")

    # ------------------------------------------------------------------
    # Control de calidad
    # ------------------------------------------------------------------
    def _tllr_fc_lineas_de_control(self):
        """Comandos para las líneas de un control: un servicio terminado por línea."""
        self.ensure_one()
        comandos = []
        for servicio in self.servicio_ids.filtered(lambda s: s.estado == 'terminado'):
            checks = [(0, 0, {'name': punto.name})
                      for punto in servicio.product_id.product_tmpl_id.sudo().tllr_fc_checklist_ids]
            comandos.append((0, 0, {'ot_servicio_id': servicio.id, 'check_ids': checks}))
        return comandos

    def _tllr_fc_crear_control(self):
        """Devuelve el control en borrador de la OT, creándolo si no existe."""
        self.ensure_one()
        borrador = self.control_ids.filtered(lambda c: c.state == 'borrador')[:1]
        if borrador:
            return borrador
        return self.env['tllr_fc.control_calidad'].sudo().create({
            'ot_id': self.id,
            'responsable_id': self.responsable_id.id,
        })

    def _tllr_fc_devolver_a_proceso(self, servicios):
        """Un control rechazado devuelve la OT a proceso.

        Los servicios rechazados vuelven a pendiente y se reactiva el primer puesto
        que los realiza; los puestos siguientes vuelven a pendiente para repetir el
        recorrido (sus servicios ya terminados no se tocan).
        """
        self.ensure_one()
        lineas = self.puesto_line_ids.sorted(lambda l: (l.sequence, l.id))
        con_rechazo = (servicios.puesto_line_id & lineas).sorted(lambda l: (l.sequence, l.id))
        destino = con_rechazo[:1] or lineas[-1:]
        for servicio in servicios:
            servicio.with_context(tllr_fc_permitir_write=True).write({
                'estado': 'pendiente', 'terminado_por_id': False, 'fecha_terminado': False})
        posicion = list(lineas.ids).index(destino.id) if destino else 0
        for indice, linea in enumerate(lineas):
            ctx = linea.with_context(tllr_fc_permitir_write=True)
            if indice == posicion:
                ctx.write({'state': 'activo', 'fecha_fin': False})
            elif indice > posicion:
                ctx.write({'state': 'pendiente', 'fecha_inicio': False, 'fecha_fin': False})
        self.state = 'proceso'
        self.producto_ids._tllr_fc_sincronizar_stock()

    # ------------------------------------------------------------------
    # Volver atrás en los estados de la OT
    # ------------------------------------------------------------------
    def action_volver_estado(self):
        """Vuelve la OT un estado atrás (supervisor, con motivo).

        - En control de calidad → En proceso (el último puesto vuelve a activo).
        - Listo para entrega → En control de calidad (nuevo control en borrador).
        - En proceso → En espera, solo si todavía no se ejecutó nada.
        Entregada y cancelada no se reabren.
        """
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden volver atrás el estado de la OT.")
        destinos = {'calidad': 'proceso', 'listo': 'calidad', 'proceso': 'espera'}
        if self.state not in destinos:
            raise UserError("Una OT %s no se puede reabrir." % (
                "entregada" if self.state == 'entregado' else "cancelada"))
        if self.state == 'proceso':
            self._tllr_fc_verificar_puede_volver_a_espera()
        etiquetas = dict(self._fields['state'].selection)
        if not self.env.context.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_volver_estado', 'supervisor',
                "Volver la OT de «%s» a «%s»." % (
                    etiquetas[self.state], etiquetas[destinos[self.state]]))
        return self._tllr_fc_ejecutar_volver_estado(self.env.context.get('tllr_fc_motivo', ''))

    def _tllr_fc_ejecutar_volver_estado(self, motivo):
        self.ensure_one()
        etiquetas = dict(self._fields['state'].selection)
        origen = self.state
        if origen == 'proceso':
            self._tllr_fc_verificar_puede_volver_a_espera()
        if origen == 'listo' and (self.cerrada_facturar or self._tllr_fc_facturas()):
            raise UserError(
                "La OT %s ya fue cerrada para facturar: reabrí primero la facturación "
                "(o emití la nota de crédito si la factura está confirmada)." % self.name)
        if origen == 'calidad' or (origen == 'listo' and not self._tllr_fc_exige_qc()):
            borradores = self.control_ids.filtered(lambda c: c.state == 'borrador')
            borradores.sudo().unlink()
            lineas = self.puesto_line_ids.sorted(lambda l: (l.sequence, l.id))
            if lineas:
                lineas[-1].with_context(tllr_fc_permitir_write=True).write(
                    {'state': 'activo', 'fecha_fin': False})
            self.state = 'proceso'
            self.producto_ids._tllr_fc_sincronizar_stock()
        elif origen == 'listo':
            self.state = 'calidad'
            self.producto_ids._tllr_fc_sincronizar_stock()
            self._tllr_fc_crear_control()
        else:
            self.puesto_line_ids.with_context(tllr_fc_permitir_write=True).write(
                {'state': 'pendiente', 'fecha_inicio': False, 'fecha_fin': False})
            self.state = 'espera'
            self.producto_ids._tllr_fc_sincronizar_stock()
        self.message_post(body="La OT volvió de «%s» a «%s». Motivo: %s" % (
            etiquetas[origen], etiquetas[self.state], motivo))
        return True

    def _tllr_fc_verificar_puede_volver_a_espera(self):
        self.ensure_one()
        if (self.servicio_ids.filtered(lambda s: s.estado != 'pendiente')
                or self.hora_ids or self.producto_ids.filtered('cantidad_consumida')):
            raise UserError(
                "No se puede volver a «En espera»: ya hay servicios terminados, horas cargadas "
                "o repuestos consumidos. Usá «Retroceder puesto» para un retrabajo.")

    def action_ver_controles(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Controles de calidad",
            'res_model': 'tllr_fc.control_calidad',
            'view_mode': 'list,form',
            'domain': [('ot_id', '=', self.id)],
        }

    def action_abrir_control(self):
        """Abre el control en borrador de la OT (lo crea si falta)."""
        self.ensure_one()
        if self.state != 'calidad':
            raise UserError("La OT no está en control de calidad.")
        control = self._tllr_fc_crear_control()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'tllr_fc.control_calidad',
            'res_id': control.id,
            'view_mode': 'form',
        }

    # ------------------------------------------------------------------
    # OT detenida
    # ------------------------------------------------------------------
    def action_detener(self):
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden detener una OT.")
        if self.state not in ('espera', 'proceso'):
            raise UserError("Solo se puede detener una OT en espera o en proceso.")
        if self.detenida:
            raise UserError("La OT ya está detenida.")
        return {
            'type': 'ir.actions.act_window',
            'name': "Detener OT",
            'res_model': 'tllr_fc.wizard.detener',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ot_id': self.id},
        }

    def _tllr_fc_detener(self, motivo, fecha_estimada):
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden detener una OT.")
        if self.state not in ('espera', 'proceso') or self.detenida:
            raise UserError("La OT no se puede detener en su estado actual.")
        self.write({
            'detenida': True,
            'motivo_detencion_id': motivo.id,
            'fecha_reanudacion_estimada': fecha_estimada,
            'detenida_desde': fields.Datetime.now(),
        })
        self.message_post(body="OT detenida: %s%s." % (
            motivo.name,
            (" (reanudación estimada %s)" % fecha_estimada) if fecha_estimada else ''))

    def _tllr_fc_cerrar_detencion(self):
        """Suma el tramo detenido al acumulado y deja la OT en marcha."""
        for ot in self.filtered('detenida'):
            tramo = 0.0
            if ot.detenida_desde:
                tramo = (fields.Datetime.now() - ot.detenida_desde).total_seconds() / 86400.0
            ot.write({
                'detenida': False,
                'dias_detenida': ot.dias_detenida + tramo,
                'detenida_desde': False,
                'fecha_reanudacion_estimada': False,
            })

    def action_reanudar(self):
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden reanudar una OT.")
        if not self.detenida:
            raise UserError("La OT no está detenida.")
        self._tllr_fc_cerrar_detencion()
        self.message_post(body="OT reanudada. Días detenida acumulados: %.2f." % self.dias_detenida)
        return True

    # ------------------------------------------------------------------
    # Trabajos adicionales
    # ------------------------------------------------------------------
    def action_registrar_aprobacion(self):
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller registran aprobaciones.")
        if not self.adicionales_pendientes:
            raise UserError("La OT no tiene adicionales pendientes de aprobación.")
        return {
            'type': 'ir.actions.act_window',
            'name': "Registrar aprobación",
            'res_model': 'tllr_fc.wizard.aprobacion',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ot_id': self.id},
        }

    def _tllr_fc_accion_cobro(self, modelo, nombre, dominio_extra=None):
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller marcan «Cobrar al cliente».")
        if self.tipo != 'garantia' or self.state not in ('espera', 'proceso', 'listo') \
                or self.cerrada_facturar:
            raise UserError("«Cobrar al cliente» se marca en una OT de garantía que aún no se cerró para facturar.")
        vista = self.env.ref('tllr_fc.view_tllr_fc_%s_cobro_list' % (
            'servicio' if modelo == 'tllr_fc.ot.servicio' else 'producto'))
        return {
            'type': 'ir.actions.act_window', 'name': nombre, 'res_model': modelo,
            'view_mode': 'list', 'views': [(vista.id, 'list')], 'target': 'new',
            'domain': [('ot_id', '=', self.id)] + (dominio_extra or []),
        }

    def action_cobro_servicios(self):
        """Lista editable (solo «Cobrar al cliente») de los servicios de la OT de garantía."""
        return self._tllr_fc_accion_cobro('tllr_fc.ot.servicio', "Servicios a cobrar")

    def action_cobro_productos(self):
        """Lista editable (solo «Cobrar al cliente») de los repuestos de la OT de garantía."""
        return self._tllr_fc_accion_cobro(
            'tllr_fc.ot.producto', "Repuestos a cobrar",
            [('uso', 'in', ['repuesto', 'insumo_facturable', 'accesorio'])])

    # ------------------------------------------------------------------
    # Facturación directa
    # ------------------------------------------------------------------
    def _tllr_fc_facturas(self):
        """Facturas de cliente vigentes de la OT (gancho: Ventas agrega las del pedido).

        Una factura anulada por una nota de crédito total ya no cuenta.
        """
        self.ensure_one()
        return self.sudo().factura_ids.filtered(
            lambda m: m.move_type == 'out_invoice'
            and not (m.state == 'posted' and m._tllr_fc_totalmente_acreditada()))

    def _tllr_fc_notas_credito(self):
        """Notas de crédito confirmadas (parciales) de las facturas vigentes de la OT."""
        self.ensure_one()
        facturas = self._tllr_fc_facturas()
        return self.sudo().factura_ids.filtered(
            lambda m: m.move_type == 'out_refund' and m.state == 'posted'
            and m.reversed_entry_id in facturas)

    def _tllr_fc_nota_credito_parcial(self, nota):
        """Una nota de crédito parcial resta ingreso a la OT y queda relacionada."""
        self.ensure_one()
        factura = nota.reversed_entry_id
        self.message_post(body=(
            "Nota de crédito parcial %s por %s sobre la factura %s: se resta del ingreso de la "
            "OT. Acreditado en total: %s de %s.") % (
                nota._get_html_link(), nota.amount_total, factura._get_html_link(),
                factura._tllr_fc_acreditado(), factura.amount_total))

    def _compute_puede_refacturar(self):
        for ot in self:
            facturas = ot.sudo().factura_ids.filtered(
                lambda m: m.move_type == 'out_invoice' and m.state == 'posted')
            ot.puede_refacturar = bool(
                ot.tipo in ('cliente', 'garantia')
                and (ot.state in ('listo', 'entregado') or (ot.state == 'cancelada' and ot.liquidada))
                and facturas and not ot._tllr_fc_facturas()
                and not ot.cerrada_facturar
                and (ot.tipo == 'cliente' or ot.lineas_cobrar))

    def _tllr_fc_nota_credito_total(self, nota):
        """Una nota de crédito total deja la OT sin factura activa y lista para refacturar."""
        self.ensure_one()
        factura = nota.reversed_entry_id
        self._tllr_fc_revertir_asientos(origen=factura)
        if self.cerrada_facturar:
            self.sudo().write({'cerrada_facturar': False, 'fecha_cierre_facturar': False})
        self.message_post(body=(
            "Nota de crédito %s por el total de la factura %s. La OT queda sin factura "
            "activa: el supervisor puede volver a facturarla con «Refacturar».") % (
                nota._get_html_link(), factura._get_html_link()))

    def _tllr_fc_lineas_factura(self, solo_realizado=False):
        """Líneas de la factura: servicios, repuestos, insumos facturables y accesorios."""
        self.ensure_one()
        lineas = []
        for servicio in self.servicio_ids.filtered(
                lambda s: s.facturable and (s.estado == 'terminado' or not solo_realizado)
                and s.estado != 'no_realizado'):
            if solo_realizado and servicio.estado != 'terminado':
                continue
            lineas.append((0, 0, {
                'product_id': servicio.product_id.id,
                'name': servicio.descripcion or servicio.product_id.display_name,
                'quantity': servicio.cantidad,
                'price_unit': servicio.precio_unitario,
                'discount': servicio.descuento,
            }))
        for linea in self.producto_ids.filtered('facturable'):
            cantidad = linea.cantidad_consumida if solo_realizado else linea.cantidad_utilizada
            if cantidad <= 0:
                continue
            lineas.append((0, 0, {
                'product_id': linea.product_id.id,
                'name': linea.descripcion or linea.product_id.display_name,
                'quantity': cantidad,
                'price_unit': linea.precio_unitario,
                'discount': linea.descuento,
            }))
        return lineas

    def _tllr_fc_verificar_precios(self, solo_realizado=False):
        self.ensure_one()
        sin_precio = []
        for servicio in self.servicio_ids.filtered(
                lambda s: s.facturable and (s.estado == 'terminado' or not solo_realizado)):
            if not servicio.precio_unitario:
                sin_precio.append(servicio.product_id.display_name)
        for linea in self.producto_ids.filtered('facturable'):
            cantidad = linea.cantidad_consumida if solo_realizado else linea.cantidad_utilizada
            if cantidad > 0 and not linea.precio_unitario:
                sin_precio.append(linea.product_id.display_name)
        if sin_precio:
            raise UserError(
                "No se puede facturar la OT %s: faltan precios de venta en %s. Cargá el precio "
                "en la ficha del producto o en la línea (supervisor)." % (
                    self.name, ', '.join(sin_precio)))

    def _tllr_fc_generar_documento_venta(self, solo_realizado=False):
        """Crea la factura de cliente directa en borrador (gancho para Ventas)."""
        self.ensure_one()
        compania = self.company_id
        if not compania.tllr_fc_diario_venta_id:
            raise UserError(
                "Definí el «Diario de factura de venta» en Taller › Configuración › Ajustes "
                "antes de cerrar la OT para facturar.")
        lineas = self._tllr_fc_lineas_factura(solo_realizado)
        if not lineas:
            raise UserError("La OT %s no tiene líneas para facturar." % self.name)
        factura = self.env['account.move'].sudo().with_company(compania).create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_id.id,
            'journal_id': compania.tllr_fc_diario_venta_id.id,
            'invoice_origin': self.name,
            'ref': self.name,
            'tllr_fc_ot_id': self.id,
            'company_id': compania.id,
            'invoice_line_ids': lineas,
        })
        return factura

    def action_cerrar_facturar(self):
        """Estado «Listo»: genera la factura (o el documento de venta) y bloquea la OT."""
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden cerrar la OT para facturar.")
        if self.tipo == 'interno':
            raise UserError("Las OT internas no se facturan.")
        if self.tipo == 'garantia' and not self.lineas_cobrar:
            raise UserError(
                "La OT de garantía no tiene líneas marcadas «Cobrar al cliente»: no hay nada "
                "para facturar.")
        refacturando = bool(self.env.context.get('tllr_fc_refacturando')) and self.puede_refacturar
        if self.state != 'listo' and not refacturando:
            raise UserError("Solo se cierra para facturar una OT lista para entrega.")
        if self.cerrada_facturar:
            raise UserError("La OT ya fue cerrada para facturar.")
        self._tllr_fc_verificar_precios()
        if self.adicionales_pendientes and not self.env.context.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_cerrar_facturar', 'supervisor',
                "Cerrar para facturar con %s adicional(es) sin aprobación del cliente." %
                self.adicionales_pendientes)
        documento = self._tllr_fc_generar_documento_venta()
        self.write({
            'cerrada_facturar': True,
            'fecha_cierre_facturar': fields.Datetime.now(),
        })
        self.message_post(body="OT cerrada para facturar. Se generó %s." % (
            documento._get_html_link() if hasattr(documento, '_get_html_link') else documento.display_name))
        return True

    def action_reabrir_facturar(self):
        """Reabre la OT cerrada para facturar (solo sin factura confirmada)."""
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden reabrir la facturación.")
        if not self.cerrada_facturar:
            raise UserError("La OT no está cerrada para facturar.")
        facturas = self._tllr_fc_facturas()
        if facturas.filtered(lambda m: m.state == 'posted'):
            raise UserError(
                "La OT tiene una factura confirmada: emití primero la nota de crédito en Contabilidad.")
        if not self.env.context.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_reabrir_facturar', 'supervisor',
                "Reabrir la OT %s: se elimina la factura en borrador." % self.name)
        borradores = facturas.filtered(lambda m: m.state == 'draft')
        borradores.sudo().with_context(tllr_fc_permitir_write=True).unlink()
        # Facturas ya anuladas por nota de crédito: se revierte su asiento de costo.
        self.sudo()._tllr_fc_revertir_asientos()
        self.write({'cerrada_facturar': False, 'fecha_cierre_facturar': False})
        self.message_post(body="Facturación reabierta. Motivo: %s" % self.env.context.get('tllr_fc_motivo', ''))
        return True

    def action_refacturar(self):
        """Abre el asistente para volver a facturar una OT cuya factura fue anulada."""
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden refacturar.")
        if not self.puede_refacturar:
            raise UserError(
                "La OT no se puede refacturar: necesita una factura anulada con una nota de "
                "crédito total y ninguna otra factura activa.")
        return {
            'type': 'ir.actions.act_window', 'name': "Refacturar la OT",
            'res_model': 'tllr_fc.wizard.refacturar', 'view_mode': 'form', 'target': 'new',
            'context': {'default_ot_id': self.id},
        }

    def action_ver_facturas(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Facturas",
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.sudo().factura_ids.ids)],
            'context': {'default_move_type': 'out_invoice'},
        }

    # ------------------------------------------------------------------
    # Entrega
    # ------------------------------------------------------------------
    def _tllr_fc_lineas_de_entrega(self):
        """Valores de las líneas de revisión: inventario de la recepción y repuestos del cliente."""
        self.ensure_one()
        lineas = []
        for item in self.recepcion_id.item_ids.filtered(lambda i: i.presente == 'si'):
            lineas.append({
                'origen': 'recepcion', 'name': item.name, 'presente_recepcion': True,
                'observacion_recepcion': item.observacion})
        for linea in self.producto_ids.filtered('provisto_cliente'):
            lineas.append({
                'origen': 'repuesto_cliente', 'name': linea.product_id.display_name,
                'presente_recepcion': True, 'entregado': 'si',
                'observacion_recepcion': linea.descripcion})
        return lineas

    def _tllr_fc_entregable(self):
        """OT lista, u OT cancelada cuyo vehículo se decidió entregar y aún no se entregó."""
        self.ensure_one()
        return self.state == 'listo' or (
            self.state == 'cancelada' and self.entrega_habilitada and not self.fecha_entrega)

    def action_habilitar_entrega(self):
        """El supervisor habilita después la entrega de una OT cancelada (con motivo)."""
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden habilitar la entrega.")
        if self.state != 'cancelada' or self.entrega_habilitada or self.fecha_entrega:
            raise UserError("La entrega no se puede habilitar en esta OT.")
        if not self.env.context.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_habilitar_entrega', 'supervisor',
                "Habilitar la entrega del vehículo de la OT cancelada %s." % self.name)
        self.write({'entrega_habilitada': True})
        self.message_post(body="Entrega del vehículo habilitada. Motivo: %s" % self.env.context.get(
            'tllr_fc_motivo', ''))
        return True

    def action_entregar(self):
        """Crea (o abre) la entrega en borrador de la OT."""
        self.ensure_one()
        if not self._tllr_fc_entregable():
            raise UserError(
                "Solo se entrega una OT lista o una OT cancelada con la entrega habilitada.")
        entrega = self.entrega_ids.filtered(lambda e: e.state == 'borrador')[:1]
        if not entrega:
            entrega = self.env['tllr_fc.entrega'].create({'ot_id': self.id})
        return {
            'type': 'ir.actions.act_window', 'res_model': 'tllr_fc.entrega',
            'res_id': entrega.id, 'view_mode': 'form', 'target': 'current'}

    def action_ver_entregas(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': "Entregas", 'res_model': 'tllr_fc.entrega',
            'view_mode': 'list,form', 'domain': [('ot_id', '=', self.id)]}

    def action_ver_traslados(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': "Traslados de stock",
            'res_model': 'stock.picking', 'view_mode': 'list,form',
            'domain': [('tllr_fc_ot_id', '=', self.id)],
            'context': {'create': False}}

    def _tllr_fc_asignar_puesto_productos(self):
        """Los repuestos sin puesto pasan al primer puesto de la OT."""
        for ot in self:
            primero = ot.puesto_line_ids.sorted(lambda l: (l.sequence, l.id))[:1]
            if not primero:
                continue
            sin_puesto = ot.producto_ids.filtered(lambda p: not p.puesto_line_id)
            if sin_puesto:
                sin_puesto.write({'puesto_line_id': primero.id})

    def action_ver_garantias(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': "Garantías", 'res_model': 'tllr_fc.garantia',
            'view_mode': 'list,form', 'domain': [('ot_id', '=', self.id)]}

    def _tllr_fc_aplicar_entrega(self, entrega):
        """Efectos de confirmar la entrega sobre la OT, el vehículo y las garantías."""
        self.ensure_one()
        ahora = entrega.fecha or fields.Datetime.now()
        vals = {'fecha_entrega': ahora, 'kilometraje_salida': entrega.kilometraje_salida}
        if self.state == 'listo':
            vals['state'] = 'entregado'
        self.write(vals)
        if entrega.kilometraje_salida > self.vehiculo_id.kilometraje:
            self.vehiculo_id.write({'kilometraje': entrega.kilometraje_salida})
        # Una OT cancelada sin liquidar no cobró nada: no genera garantías ni asiento de entrega.
        if self.tipo == 'cliente' and (self.state != 'cancelada' or self.liquidada):
            garantias = self.env['tllr_fc.garantia']._tllr_fc_crear_de_entrega(
                self, ahora, entrega.kilometraje_salida)
            if garantias:
                self.message_post(body="Se registraron %s garantía(s)." % len(garantias))
        self._tllr_fc_cerrar_detencion()
        if self.state != 'cancelada':
            self.sudo()._tllr_fc_asiento_entrega()
        self.message_post(body="Vehículo entregado (entrega %s)." % entrega.name)

    def action_avisar_cliente(self):
        """Envía al contacto principal el aviso de vehículo listo (manual)."""
        self.ensure_one()
        if self.state != 'listo':
            raise UserError("El aviso se envía cuando la OT está lista para entrega.")
        if not self.partner_id.email:
            raise UserError("El cliente %s no tiene correo electrónico." % self.partner_id.name)
        plantilla = self.env.ref('tllr_fc.mail_template_ot_aviso')
        plantilla.send_mail(self.id, force_send=False)
        self.message_post(body="Aviso de vehículo listo enviado a %s." % self.partner_id.name)
        return True

    def action_reclamo_garantia(self):
        self.ensure_one()
        if self.state != 'entregado' or self.tipo != 'cliente':
            raise UserError("Solo se reclama sobre una OT de cliente entregada.")
        if not self.garantia_ids.filtered(lambda g: not g.reclamo_ot_id):
            raise UserError(
                "La OT %s no tiene garantías disponibles para reclamar. Las garantías se crean "
                "al entregar, según los días de garantía de la ficha de cada producto; para una OT "
                "entregada antes, el administrador de taller puede cargarla en Operación › "
                "Garantías, o podés generar una recepción de tipo Garantía eligiendo la OT original."
                % self.name)
        return {
            'type': 'ir.actions.act_window', 'name': "Reclamo de garantía",
            'res_model': 'tllr_fc.wizard.reclamo_garantia', 'view_mode': 'form',
            'target': 'new', 'context': {'default_ot_id': self.id}}

    # ------------------------------------------------------------------
    # Cancelación
    # ------------------------------------------------------------------
    def _tllr_fc_trabajo_realizado(self):
        self.ensure_one()
        return bool(
            self.servicio_ids.filtered(lambda s: s.estado == 'terminado')
            or self.producto_ids.filtered('cantidad_consumida')
            or self.hora_ids)

    def action_cancelar(self):
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden cancelar la OT.")
        if self.state not in ('espera', 'proceso', 'calidad', 'listo'):
            raise UserError("La OT ya está cerrada.")
        return {
            'type': 'ir.actions.act_window', 'name': "Cancelar OT",
            'res_model': 'tllr_fc.wizard.cancelar', 'view_mode': 'form',
            'target': 'new', 'context': {'default_ot_id': self.id}}

    def _tllr_fc_cancelar(self, motivo, liquidar):
        """Cancela la OT: con liquidación factura lo realizado; siempre libera reservas."""
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden cancelar la OT.")
        if self.state not in ('espera', 'proceso', 'calidad', 'listo'):
            raise UserError("La OT ya está cerrada.")
        facturas = self._tllr_fc_facturas()
        if facturas.filtered(lambda m: m.state == 'posted'):
            raise UserError(
                "La OT %s tiene una factura confirmada: emití primero la nota de crédito en "
                "Contabilidad." % self.name)
        if liquidar:
            if self.tipo != 'cliente' or not self._tllr_fc_trabajo_realizado():
                raise UserError("Solo se liquida una OT de cliente con trabajo realizado.")
            self._tllr_fc_verificar_precios(solo_realizado=True)
        facturas.filtered(lambda m: m.state == 'draft').sudo().unlink()
        for control in self.control_ids.filtered(lambda c: c.state == 'borrador'):
            control.sudo().unlink()
        documento = False
        if liquidar:
            documento = self._tllr_fc_generar_documento_venta(solo_realizado=True)
        self.write({
            'state': 'cancelada',
            'motivo_cancelacion_id': motivo.id,
            'liquidada': bool(liquidar),
            'cerrada_facturar': bool(liquidar),
            'fecha_cierre_facturar': fields.Datetime.now() if liquidar else False,
        })
        self.producto_ids._tllr_fc_sincronizar_stock()
        self._tllr_fc_cerrar_detencion()
        self._tllr_fc_liberar_garantias()
        if not liquidar:
            self.sudo()._tllr_fc_asiento_cancelacion()
        texto = "OT cancelada (%s)." % motivo.name
        if liquidar:
            texto += " Se facturó lo realizado: %s." % (
                documento._get_html_link() if hasattr(documento, '_get_html_link') else documento.display_name)
        elif self._tllr_fc_trabajo_realizado():
            texto += " Cancelada sin liquidar lo ejecutado. Motivo: %s" % self.env.context.get('tllr_fc_motivo', '')
        self.message_post(body=texto)
        return True

    # ------------------------------------------------------------------
    # Ganchos para los módulos puente (Ventas / Compras)
    # ------------------------------------------------------------------
    def _tllr_fc_requiere_presupuesto(self):
        """Con Ventas activo, las OT de cliente requieren presupuesto confirmado."""
        self.ensure_one()
        return False

    def _tllr_fc_presupuesto_ok_para_iniciar(self):
        self.ensure_one()
        return True

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == "Nuevo":
                compania = self.env['res.company'].browse(
                    vals.get('company_id') or self.env.company.id)
                vals['name'] = compania._tllr_fc_siguiente_codigo('tllr_fc.ot')
        return super().create(vals_list)

    def write(self, vals):
        if not self._tllr_fc_es_supervisor():
            if 'tipo' in vals:
                raise AccessError(
                    "Solo el supervisor o el administrador de taller pueden cambiar el tipo de OT.")
            if 'requiere_qc' in vals:
                raise AccessError(
                    "Solo el supervisor o el administrador de taller pueden exigir el control de calidad.")
            if 'responsable_id' in vals:
                raise AccessError(
                    "Solo el supervisor o el administrador de taller pueden definir el responsable.")
        if vals.get('requiere_qc') is False:
            for ot in self:
                if ot.company_id['tllr_fc_qc_%s' % (vals.get('tipo') or ot.tipo)]:
                    raise UserError(
                        "No se puede quitar el control de calidad: el ajuste de la compañía lo "
                        "exige para las OT de este tipo.")
        return super().write(vals)

    def action_iniciar(self):
        """En espera → En proceso. Activa el primer puesto."""
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor o el administrador de taller pueden iniciar la OT.")
        if self.state != 'espera':
            raise UserError("Solo se puede iniciar una OT que está en espera.")
        self._tllr_fc_verificar_no_detenida("iniciar")
        if not self.responsable_id:
            raise UserError("Indicá el responsable de la OT antes de iniciarla.")
        lineas = self.puesto_line_ids
        if not lineas:
            raise UserError("Agregá al menos un puesto a la OT antes de iniciarla.")
        sin_personal = lineas.filtered(lambda l: not l.personal_ids)
        if sin_personal:
            raise UserError(
                "Asigná al menos una persona a cada puesto: %s." % ', '.join(sin_personal.mapped('name')))
        sin_puesto = self.servicio_ids.filtered(
            lambda s: not s.puesto_line_id and s.estado != 'no_realizado')
        if sin_puesto:
            raise UserError(
                "Hay servicios sin puesto asignado: %s." % ', '.join(sin_puesto.mapped('product_id.name')))
        if not self.servicio_ids:
            raise UserError("La OT no tiene servicios.")
        if self.responsable_id in self.personal_ids and not self.env.context.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_iniciar', 'supervisor',
                "El responsable «%s» también figura como personal de un puesto." % self.responsable_id.name)
        if (self._tllr_fc_requiere_presupuesto() and not self._tllr_fc_presupuesto_ok_para_iniciar()
                and not self.env.context.get('tllr_fc_excepcion')):
            return self._tllr_fc_abrir_excepcion(
                'action_iniciar', 'supervisor',
                "Iniciar la OT sin el presupuesto confirmado por el cliente.")
        primera = lineas.sorted(lambda l: (l.sequence, l.id))[:1]
        ahora = fields.Datetime.now()
        self._tllr_fc_asignar_puesto_productos()
        lineas.with_context(tllr_fc_permitir_write=True).write({'state': 'pendiente'})
        primera.with_context(tllr_fc_permitir_write=True).write(
            {'state': 'activo', 'fecha_inicio': ahora})
        self.state = 'proceso'
        self.producto_ids._tllr_fc_sincronizar_stock()
        self.message_post(body="OT iniciada. Puesto activo: «%s»." % primera.name)
        return True

    def action_terminar_puesto(self):
        """Termina el puesto activo y pasa al siguiente (o cierra el recorrido)."""
        for ot in self:
            if ot.state != 'proceso':
                raise UserError("La OT %s no está en proceso." % ot.name)
            actual = ot._tllr_fc_verificar_puesto_terminable()
            if not actual._tllr_fc_usuario_puede_operar():
                raise AccessError(
                    "Solo el supervisor o el personal asignado al puesto activo pueden terminarlo.")
            ot._tllr_fc_avanzar_puesto()
        return True

    def action_retroceder_puesto(self):
        """Vuelve al puesto anterior para un retrabajo (supervisor, con motivo)."""
        self.ensure_one()
        if not self._tllr_fc_es_supervisor():
            raise AccessError("Solo el supervisor puede retroceder la OT a un puesto anterior.")
        if self.state != 'proceso':
            raise UserError("Solo se puede retroceder una OT en proceso.")
        lineas = self.puesto_line_ids.sorted(lambda l: (l.sequence, l.id))
        actual = lineas.filtered(lambda l: l.state == 'activo')[:1]
        anteriores = lineas.filtered(lambda l: l.state == 'terminado')
        if not actual or not anteriores:
            raise UserError("La OT no tiene un puesto anterior al que volver.")
        if not self.env.context.get('tllr_fc_excepcion'):
            return self._tllr_fc_abrir_excepcion(
                'action_retroceder_puesto', 'supervisor',
                "Volver al puesto «%s» (retrabajo)." % anteriores[-1].name)
        destino = anteriores[-1]
        ctx = self.with_context(tllr_fc_permitir_write=True)
        actual.with_context(tllr_fc_permitir_write=True).write({'state': 'pendiente', 'fecha_inicio': False})
        destino.with_context(tllr_fc_permitir_write=True).write({'state': 'activo', 'fecha_fin': False})
        # Los servicios terminados del puesto de destino se retrabajan.
        for servicio in destino.servicio_ids.filtered(lambda s: s.estado == 'terminado'):
            servicio.with_context(tllr_fc_permitir_write=True).write({
                'estado': 'pendiente', 'terminado_por_id': False, 'fecha_terminado': False})
        ctx.message_post(body="Retroceso al puesto «%s» para retrabajo. Motivo: %s" % (
            destino.name, self.env.context.get('tllr_fc_motivo', '')))
        self.producto_ids._tllr_fc_sincronizar_stock()
        return True

    def _tllr_fc_liberar_garantias(self):
        """Una OT de garantía cancelada devuelve las garantías reclamadas a Vigente."""
        self.env['tllr_fc.garantia'].sudo().search(
            [('reclamo_ot_id', 'in', self.ids)])._tllr_fc_liberar_reclamo()

    def _tllr_fc_cancelar_por_recepcion(self):
        """Cancela la OT en espera cuando se anula su recepción (sin liquidación)."""
        motivo = self.env.ref(
            'tllr_fc.motivo_cancelacion_recepcion_anulada', raise_if_not_found=False)
        for ot in self:
            ot.write({
                'state': 'cancelada',
                'motivo_cancelacion_id': motivo.id if motivo else False,
            })
            ot.producto_ids._tllr_fc_sincronizar_stock()
            ot._tllr_fc_cerrar_detencion()
            ot._tllr_fc_liberar_garantias()
            ot.message_post(body="OT cancelada porque se anuló su recepción (sin liquidación).")

    def action_ver_recepcion(self):
        self.ensure_one()
        return self.recepcion_id._tllr_fc_accion_formulario()
