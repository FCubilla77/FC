# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TllrFcGarantia(models.Model):
    """Garantía de un servicio o producto entregado al cliente."""
    _name = 'tllr_fc.garantia'
    _description = "Garantía"
    _order = 'fecha_limite, id'
    _check_company_auto = True

    ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT original", required=True, ondelete='restrict', index=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía", related='ot_id.company_id', store=True, index=True)
    vehiculo_id = fields.Many2one(
        'tllr_fc.vehiculo', string="Vehículo", related='ot_id.vehiculo_id', store=True)
    partner_id = fields.Many2one(
        'res.partner', string="Cliente", related='ot_id.partner_id', store=True)
    product_id = fields.Many2one(
        'product.product', string="Servicio / producto", required=True, ondelete='restrict')
    fecha_entrega = fields.Date(string="Fecha de entrega", required=True)
    dias = fields.Integer(string="Días de garantía")
    km = fields.Integer(string="Km de garantía")
    fecha_limite = fields.Date(string="Vence el", required=True, index=True)
    km_limite = fields.Integer(string="Km límite", help="0 = no aplica.")
    state = fields.Selection(
        [('vigente', "Vigente"), ('en_reclamo', "En reclamo"), ('ejecutada', "Ejecutada"),
         ('vencida_fecha', "Vencida por fecha"), ('vencida_km', "Vencida por kilometraje")],
        string="Estado", compute='_compute_state',
        help="Vigente: disponible para reclamar. En reclamo: hay una OT de garantía abierta. "
             "Ejecutada: la OT de garantía se entregó y la garantía ya no tiene vigencia.")
    reclamo_recepcion_id = fields.Many2one(
        'tllr_fc.recepcion', string="Recepción del reclamo", copy=False, readonly=True,
        ondelete='set null')
    reclamo_ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT de garantía", copy=False, readonly=True, ondelete='set null')

    @api.onchange('ot_id')
    def _onchange_ot_id(self):
        if self.ot_id:
            self.fecha_entrega = fields.Date.to_date(self.ot_id.fecha_entrega) or fields.Date.today()
            return {'domain': {'product_id': [
                ('id', 'in', (self.ot_id.servicio_ids.product_id
                              | self.ot_id.producto_ids.product_id).ids)]}}

    @api.onchange('product_id', 'fecha_entrega')
    def _onchange_plazos(self):
        plantilla = self.product_id.product_tmpl_id
        if plantilla and self.fecha_entrega:
            self.dias = plantilla.tllr_fc_garantia_dias
            self.km = plantilla.tllr_fc_garantia_km
            self.fecha_limite = self.fecha_entrega + timedelta(days=self.dias)
            self.km_limite = (self.ot_id.kilometraje_salida + self.km) if self.km else 0

    @api.constrains('ot_id')
    def _check_ot_cliente(self):
        for garantia in self:
            if garantia.ot_id.tipo != 'cliente':
                raise ValidationError("Solo las OT de cliente tienen garantías.")

    def _tllr_fc_estado_a(self, fecha, km):
        self.ensure_one()
        if self.fecha_limite and fecha > self.fecha_limite:
            return 'vencida_fecha'
        if self.km_limite and km and km > self.km_limite:
            return 'vencida_km'
        return 'vigente'

    @api.depends('fecha_limite', 'km_limite', 'vehiculo_id.kilometraje',
                 'reclamo_ot_id.state', 'reclamo_recepcion_id')
    def _compute_state(self):
        hoy = fields.Date.context_today(self)
        for garantia in self:
            if garantia.reclamo_ot_id and garantia.reclamo_ot_id.state == 'entregado':
                garantia.state = 'ejecutada'
            elif garantia.reclamo_ot_id or garantia.reclamo_recepcion_id:
                garantia.state = 'en_reclamo'
            else:
                garantia.state = garantia._tllr_fc_estado_a(
                    hoy, garantia.vehiculo_id.kilometraje)

    def _tllr_fc_liberar_reclamo(self):
        """Libera el reclamo (OT de garantía cancelada o recepción anulada): vuelve a Vigente."""
        self.sudo().write({'reclamo_ot_id': False, 'reclamo_recepcion_id': False})

    @api.depends('product_id', 'ot_id')
    def _compute_display_name(self):
        for garantia in self:
            garantia.display_name = "%s - %s" % (
                garantia.ot_id.name or '', garantia.product_id.display_name or '')

    @api.model
    def _tllr_fc_crear_de_entrega(self, ot, fecha, km_salida):
        """Crea las garantías de los servicios y productos garantizados de la OT."""
        valores = []
        fecha_entrega = fields.Date.to_date(fecha)

        def agregar(producto):
            plantilla = producto.product_tmpl_id
            if plantilla.tllr_fc_garantia_dias > 0:
                valores.append({
                    'ot_id': ot.id,
                    'product_id': producto.id,
                    'fecha_entrega': fecha_entrega,
                    'dias': plantilla.tllr_fc_garantia_dias,
                    'km': plantilla.tllr_fc_garantia_km,
                    'fecha_limite': fecha_entrega + timedelta(days=plantilla.tllr_fc_garantia_dias),
                    'km_limite': (km_salida + plantilla.tllr_fc_garantia_km)
                    if plantilla.tllr_fc_garantia_km else 0,
                })
        for servicio in ot.servicio_ids.filtered(lambda s: s.estado == 'terminado' and s.facturable):
            agregar(servicio.product_id)
        for linea in ot.producto_ids.filtered(
                lambda p: p.uso in ('repuesto', 'insumo_facturable', 'accesorio')
                and not p.provisto_cliente and p.cantidad_utilizada > 0):
            agregar(linea.product_id)
        return self.sudo().create(valores)
