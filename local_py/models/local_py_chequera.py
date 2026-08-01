# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class LocalPyChequera(models.Model):
    _name = 'local_py.chequera'
    _description = 'Chequera'
    _order = 'id desc'

    name = fields.Char(string='Número de Chequera', required=True)
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company,
    )
    bank_id = fields.Many2one('res.bank', string='Banco', required=True)
    cuenta_bancaria_id = fields.Many2one(
        'res.partner.bank', string='Cuenta Bancaria', required=True,
        domain="[('bank_id', '=', bank_id), ('company_id', 'in', (company_id, False))]",
    )
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', required=True,
        default=lambda self: self.env.company.currency_id,
    )
    tipo = fields.Selection(
        [('al_dia', 'Al día'), ('diferido', 'Diferido')], string='Tipo', required=True, default='al_dia',
        help='Al día: la Fecha de Emisión y la Fecha de Vencimiento del cheque son la misma. '
             'Diferido: la Fecha de Vencimiento es posterior a la Fecha de Emisión.',
    )
    numero_inicial = fields.Integer(string='Número Inicial', required=True)
    numero_final = fields.Integer(string='Número Final', required=True)
    ultimo_numero_utilizado = fields.Integer(string='Último Número Utilizado', readonly=True, copy=False)
    siguiente_numero = fields.Integer(
        string='Siguiente Número', compute='_compute_siguiente_numero', store=True,
        help='Calculado como Último Número Utilizado + 1 — no es un dato editable, para que '
             'nunca pueda desincronizarse del control real de numeración.',
    )
    state = fields.Selection(
        [('activo', 'Activo'), ('finalizado', 'Finalizado'), ('cancelado', 'Cancelado')],
        string='Estado', default='activo', required=True, copy=False, tracking=True,
    )
    diario_id = fields.Many2one(
        'account.journal', string='Diario', required=True,
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
    )

    cheque_ids = fields.One2many('local_py.chequera.cheque', 'chequera_id', string='Cheques')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals.setdefault('ultimo_numero_utilizado', (vals.get('numero_inicial') or 1) - 1)
        return super().create(vals_list)

    @api.depends('ultimo_numero_utilizado')
    def _compute_siguiente_numero(self):
        for chequera in self:
            chequera.siguiente_numero = chequera.ultimo_numero_utilizado + 1

    @api.constrains('numero_inicial', 'numero_final')
    def _check_rango(self):
        for chequera in self:
            if chequera.numero_inicial > chequera.numero_final:
                raise ValidationError('El Número Inicial no puede ser mayor al Número Final.')

    @api.constrains('numero_final', 'ultimo_numero_utilizado')
    def _check_numero_final(self):
        for chequera in self:
            if chequera.numero_final < chequera.ultimo_numero_utilizado:
                raise ValidationError(
                    'El Número Final no puede ser menor al Último Número Utilizado (%s) — '
                    'reduciría el rango por debajo de cheques ya emitidos.'
                    % chequera.ultimo_numero_utilizado
                )

    def write(self, vals):
        if 'numero_inicial' in vals:
            for chequera in self:
                if chequera.cheque_ids and vals['numero_inicial'] != chequera.numero_inicial:
                    raise UserError(
                        'No se puede modificar el Número Inicial de "%s": ya tiene cheques '
                        'emitidos.' % chequera.name
                    )
        return super().write(vals)

    @api.constrains('diario_id', 'state')
    def _check_una_activa_por_diario(self):
        for chequera in self:
            if chequera.state != 'activo':
                continue
            otras = self.search([
                ('diario_id', '=', chequera.diario_id.id),
                ('state', '=', 'activo'),
                ('id', '!=', chequera.id),
            ])
            if otras:
                raise ValidationError(
                    'El Diario "%s" ya tiene otra Chequera activa. Solo puede haber una '
                    'Chequera activa por Diario a la vez.' % chequera.diario_id.name
                )

    def _asignar_siguiente_numero(self):
        """Asigna el próximo número disponible y avanza el contador. Si se
        agota el rango, la Chequera pasa sola a "Finalizado"."""
        self.ensure_one()
        if self.state != 'activo':
            raise UserError('La Chequera "%s" no está Activa.' % self.name)
        if self.siguiente_numero > self.numero_final:
            raise UserError(
                'La Chequera "%s" no tiene números disponibles (llegó a su Número Final). '
                'Active otra Chequera para este Diario.' % self.name
            )
        numero = self.siguiente_numero
        self.ultimo_numero_utilizado = numero
        if self.siguiente_numero > self.numero_final:
            self.state = 'finalizado'
        return numero
