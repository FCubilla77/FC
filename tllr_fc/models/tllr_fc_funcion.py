# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .utils import escapar_ilike


class TllrFcFuncion(models.Model):
    _name = 'tllr_fc.funcion'
    _description = "Función de taller"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'
    _check_company_auto = True

    name = fields.Char(string="Función", required=True, tracking=True)
    active = fields.Boolean(string="Activo", default=True)
    # Vacío = compartida por todas las compañías (datos iniciales del módulo).
    company_id = fields.Many2one(
        'res.company', string="Compañía", default=lambda self: self.env.company,
        help="Si se deja vacío, la función se comparte entre todas las compañías.")
    currency_id = fields.Many2one(
        'res.currency', string="Moneda", compute='_compute_currency_id')
    costo_ids = fields.One2many(
        'tllr_fc.funcion.costo', 'funcion_id', string="Costo por hora",
        groups='tllr_fc.group_supervisor')
    costo_actual = fields.Monetary(
        string="Costo por hora vigente", compute='_compute_costo_actual',
        currency_field='currency_id', groups='tllr_fc.group_supervisor')

    @api.depends('company_id')
    def _compute_currency_id(self):
        for funcion in self:
            funcion.currency_id = (funcion.company_id or self.env.company).currency_id

    @api.depends('costo_ids.fecha_desde', 'costo_ids.costo_hora')
    def _compute_costo_actual(self):
        hoy = fields.Date.context_today(self)
        for funcion in self:
            funcion.costo_actual = funcion._costo_a_fecha(hoy)

    def _costo_a_fecha(self, fecha):
        """Costo por hora vigente en `fecha`.

        Devuelve el costo de la línea con mayor `fecha_desde <= fecha`; si no hay
        ninguna, devuelve 0. Se lee con sudo: la valorización de horas la usan
        también los usuarios que no ven los costos.
        """
        self.ensure_one()
        lineas = self.sudo().costo_ids.filtered(lambda linea: linea.fecha_desde <= fecha)
        if not lineas:
            return 0.0
        return max(lineas, key=lambda linea: linea.fecha_desde).costo_hora

    def _tiene_costo_a_fecha(self, fecha):
        """True si existe al menos una vigencia con fecha_desde <= fecha."""
        self.ensure_one()
        return any(linea.fecha_desde <= fecha for linea in self.sudo().costo_ids)

    @api.constrains('name', 'company_id')
    def _check_nombre_unico(self):
        for funcion in self:
            repetida = self.with_context(active_test=False).search_count([
                ('id', '!=', funcion.id),
                ('company_id', '=', funcion.company_id.id),
                ('name', '=ilike', escapar_ilike((funcion.name or '').strip())),
            ])
            if repetida:
                raise ValidationError(
                    "Ya existe la función «%s»." % funcion.name)


class TllrFcFuncionCosto(models.Model):
    _name = 'tllr_fc.funcion.costo'
    _description = "Vigencia de costo por hora de una función"
    _order = 'funcion_id, fecha_desde desc'

    funcion_id = fields.Many2one(
        'tllr_fc.funcion', string="Función", required=True, ondelete='cascade', index=True)
    fecha_desde = fields.Date(
        string="Vigente desde", required=True, default=fields.Date.context_today)
    costo_hora = fields.Monetary(
        string="Costo por hora", required=True, currency_field='currency_id',
        groups='tllr_fc.group_supervisor')
    company_id = fields.Many2one(
        related='funcion_id.company_id', string="Compañía", store=True)
    currency_id = fields.Many2one(
        'res.currency', string="Moneda", compute='_compute_currency_id')

    @api.depends('funcion_id.company_id')
    def _compute_currency_id(self):
        for linea in self:
            linea.currency_id = (linea.funcion_id.company_id or self.env.company).currency_id

    @api.constrains('funcion_id', 'fecha_desde')
    def _check_fecha_unica(self):
        for linea in self:
            repetida = self.search_count([
                ('id', '!=', linea.id),
                ('funcion_id', '=', linea.funcion_id.id),
                ('fecha_desde', '=', linea.fecha_desde),
            ])
            if repetida:
                raise ValidationError(
                    "Ya existe un costo vigente desde el %s para la función %s." % (
                        linea.fecha_desde, linea.funcion_id.display_name))

    @api.constrains('costo_hora')
    def _check_costo_positivo(self):
        for linea in self:
            if linea.costo_hora < 0:
                raise ValidationError("El costo por hora no puede ser negativo.")

    def write(self, vals):
        raise UserError(
            "Las vigencias de costo no se modifican: para cambiar el costo agregue "
            "una nueva línea con su fecha de vigencia.")

    @api.ondelete(at_uninstall=False)
    def _unlink_bloqueado(self):
        raise UserError(
            "Las vigencias de costo no se eliminan: el historial de costos debe "
            "conservarse.")
