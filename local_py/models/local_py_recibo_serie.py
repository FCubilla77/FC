# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LocalPyReciboSerie(models.Model):
    _name = 'local_py.recibo.serie'
    _description = 'Serie de Recibo'
    _order = 'id desc'

    name = fields.Char(string='Serie', required=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company,
    )
    user_id = fields.Many2one('res.users', string='Usuario', required=True)
    numero_inicial = fields.Integer(string='Número Inicial')
    numero_final = fields.Integer(string='Número Final')
    ultimo_numero_utilizado = fields.Integer(string='Último Número Utilizado', readonly=True, copy=False)
    siguiente_numero = fields.Integer(
        string='Siguiente Número', compute='_compute_siguiente_numero', store=True,
        help='Calculado como Último Número Utilizado + 1 — no es un dato editable, para que '
             'nunca pueda desincronizarse del control real de numeración.',
    )
    active = fields.Boolean(string='Activo', default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('ultimo_numero_utilizado', (vals.get('numero_inicial') or 1) - 1)
        return super().create(vals_list)

    @api.depends('ultimo_numero_utilizado')
    def _compute_siguiente_numero(self):
        for serie in self:
            serie.siguiente_numero = serie.ultimo_numero_utilizado + 1

    @api.constrains('numero_inicial', 'numero_final')
    def _check_numeros_no_vacios(self):
        """"required=True" en un campo Integer no alcanza para bloquear
        un valor en 0 (Odoo solo lo trata como "vacío" si queda en
        Nulo, no en cero) — se agrega esta validación explícita, desde
        el principio (mismo hueco ya encontrado y corregido en
        Chequera)."""
        for serie in self:
            if not serie.numero_inicial or not serie.numero_final:
                raise ValidationError('Complete el Número Inicial y el Número Final antes de guardar.')

    @api.constrains('numero_inicial', 'numero_final')
    def _check_rango(self):
        for serie in self:
            if serie.numero_inicial > serie.numero_final:
                raise ValidationError('El Número Inicial no puede ser mayor al Número Final.')

    @api.constrains('numero_final', 'ultimo_numero_utilizado')
    def _check_numero_final(self):
        for serie in self:
            if serie.numero_final < serie.ultimo_numero_utilizado:
                raise ValidationError(
                    'El Número Final no puede ser menor al Último Número Utilizado (%s).'
                    % serie.ultimo_numero_utilizado
                )

    def _asignar_siguiente_numero(self):
        self.ensure_one()
        if self.siguiente_numero > self.numero_final:
            raise ValidationError(
                'La Serie "%s" ya llegó a su Número Final (%s) — no quedan números '
                'disponibles. Active o cree una Serie nueva.' % (self.name, self.numero_final)
            )
        numero = self.siguiente_numero
        self.ultimo_numero_utilizado = numero
        return numero
