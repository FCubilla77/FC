# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class TllrFcVehiculo(models.Model):
    _name = 'tllr_fc.vehiculo'
    _description = "Vehículo"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'chapa'
    _check_company_auto = True
    _rec_names_search = ['chapa', 'name', 'chasis', 'codigo']

    codigo = fields.Char(
        string="Código", required=True, readonly=True, copy=False, default="Nuevo")
    name = fields.Char(string="Descripción", required=True, tracking=True)
    marca_id = fields.Many2one(
        'tllr_fc.marca', string="Marca", required=True,
        ondelete='restrict', check_company=True, tracking=True)
    modelo_id = fields.Many2one(
        'tllr_fc.modelo', string="Modelo", required=True,
        ondelete='restrict', check_company=True, tracking=True,
        domain="[('marca_id', '=', marca_id)]")
    anio = fields.Integer(string="Año", required=True)
    tipo_id = fields.Many2one(
        'tllr_fc.tipo_vehiculo', string="Tipo", required=True,
        ondelete='restrict', check_company=True)
    partner_id = fields.Many2one(
        'res.partner', string="Propietario", required=True,
        ondelete='restrict', check_company=True, tracking=True, index=True)
    chapa = fields.Char(string="Chapa / Patente", required=True, tracking=True, index=True)
    chasis = fields.Char(string="Chasis / VIN")
    color = fields.Char(string="Color")
    combustible = fields.Selection([
        ('nafta', "Nafta"),
        ('diesel', "Diésel"),
        ('gas', "Gas"),
        ('hibrido', "Híbrido"),
        ('electrico', "Eléctrico"),
        ('otro', "Otro"),
    ], string="Combustible")
    kilometraje = fields.Integer(
        string="Kilometraje", readonly=True,
        help="Último kilometraje registrado. Se actualiza desde la recepción y la entrega.")
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True,
        default=lambda self: self.env.company)
    active = fields.Boolean(string="Activo", default=True)
    recepcion_count = fields.Integer(
        string="Recepciones", compute='_compute_conteos')
    ot_count = fields.Integer(
        string="Órdenes de trabajo", compute='_compute_conteos')

    # ------------------------------------------------------------------
    # Conteos y accesos
    # ------------------------------------------------------------------
    def _compute_conteos(self):
        recepciones = {}
        ordenes = {}
        if self.ids:
            for vehiculo, cantidad in self.env['tllr_fc.recepcion']._read_group(
                    [('vehiculo_id', 'in', self.ids)], ['vehiculo_id'], ['__count']):
                recepciones[vehiculo.id] = cantidad
            for vehiculo, cantidad in self.env['tllr_fc.ot']._read_group(
                    [('vehiculo_id', 'in', self.ids)], ['vehiculo_id'], ['__count']):
                ordenes[vehiculo.id] = cantidad
        for vehiculo in self:
            vehiculo.recepcion_count = recepciones.get(vehiculo.id, 0)
            vehiculo.ot_count = ordenes.get(vehiculo.id, 0)

    def action_ver_recepciones(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Recepciones",
            'res_model': 'tllr_fc.recepcion',
            'view_mode': 'list,form',
            'domain': [('vehiculo_id', '=', self.id)],
            'context': {'default_vehiculo_id': self.id, 'default_partner_id': self.partner_id.id},
        }

    def action_ver_ots(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': "Órdenes de trabajo",
            'res_model': 'tllr_fc.ot',
            'view_mode': 'list,form',
            'domain': [('vehiculo_id', '=', self.id)],
        }

    # ------------------------------------------------------------------
    # Normalización
    # ------------------------------------------------------------------
    @api.model
    def _normalizar_chapa(self, valor):
        return ''.join((valor or '').split()).upper()

    @api.model
    def _normalizar_vals(self, vals):
        if vals.get('chapa'):
            vals['chapa'] = self._normalizar_chapa(vals['chapa'])
        if 'chasis' in vals:
            vals['chasis'] = (vals['chasis'] or '').strip().upper() or False
        return vals

    @api.onchange('chapa')
    def _onchange_chapa(self):
        if self.chapa:
            self.chapa = self._normalizar_chapa(self.chapa)

    @api.onchange('chasis')
    def _onchange_chasis(self):
        if self.chasis:
            self.chasis = self.chasis.strip().upper()

    @api.onchange('marca_id')
    def _onchange_marca_id(self):
        if self.modelo_id and self.modelo_id.marca_id != self.marca_id:
            self.modelo_id = False

    # ------------------------------------------------------------------
    # Nombre visible: [chapa] descripción
    # ------------------------------------------------------------------
    @api.depends('chapa', 'name')
    def _compute_display_name(self):
        for vehiculo in self:
            vehiculo.display_name = (
                "[%s] %s" % (vehiculo.chapa, vehiculo.name)
                if vehiculo.chapa else (vehiculo.name or ''))

    # ------------------------------------------------------------------
    # Restricciones
    # ------------------------------------------------------------------
    @api.constrains('anio')
    def _check_anio(self):
        anio_maximo = fields.Date.context_today(self).year + 1
        for vehiculo in self:
            if not 1950 <= vehiculo.anio <= anio_maximo:
                raise ValidationError(
                    "El año del vehículo debe estar entre 1950 y %s." % anio_maximo)

    @api.constrains('chapa', 'company_id')
    def _check_chapa_unica(self):
        for vehiculo in self:
            repetido = self.with_context(active_test=False).search_count([
                ('id', '!=', vehiculo.id),
                ('company_id', '=', vehiculo.company_id.id),
                ('chapa', '=', vehiculo.chapa),
            ])
            if repetido:
                raise ValidationError(
                    "Ya existe un vehículo con la chapa %s en esta compañía "
                    "(puede estar archivado)." % vehiculo.chapa)

    @api.constrains('chasis', 'company_id')
    def _check_chasis_unico(self):
        for vehiculo in self.filtered('chasis'):
            repetido = self.with_context(active_test=False).search_count([
                ('id', '!=', vehiculo.id),
                ('company_id', '=', vehiculo.company_id.id),
                ('chasis', '=', vehiculo.chasis),
            ])
            if repetido:
                raise ValidationError(
                    "Ya existe un vehículo con el chasis %s en esta compañía "
                    "(puede estar archivado)." % vehiculo.chasis)

    @api.constrains('marca_id', 'modelo_id')
    def _check_modelo_de_la_marca(self):
        for vehiculo in self:
            if vehiculo.modelo_id.marca_id != vehiculo.marca_id:
                raise ValidationError(
                    "El modelo %s no pertenece a la marca %s." % (
                        vehiculo.modelo_id.display_name, vehiculo.marca_id.display_name))

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._normalizar_vals(vals)
            if not vals.get('codigo') or vals['codigo'] == "Nuevo":
                compania = self.env['res.company'].browse(
                    vals.get('company_id') or self.env.company.id)
                vals['codigo'] = compania._tllr_fc_siguiente_codigo('tllr_fc.vehiculo')
        return super().create(vals_list)

    def write(self, vals):
        self._normalizar_vals(vals)
        return super().write(vals)

    def copy_data(self, default=None):
        datos = super().copy_data(default)
        for vals in datos:
            # La chapa y el chasis son únicos: la copia debe completarlos a mano.
            vals['chapa'] = "%s-COPIA" % (vals.get('chapa') or '')
            vals['chasis'] = False
        return datos
