# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions

from .local_py_licencia import (
    local_py_decodificar_licencia,
    local_py_version_odoo_instalada,
)


class ResCompany(models.Model):
    _inherit = 'res.company'

    city_id = fields.Many2one(
        'res.city', string='Ciudad', domain="[('state_id', '=', state_id)]",
    )

    # -- Licencia del producto (OPL-1) --------------------------------------
    local_py_licencia_uuid = fields.Char(
        string="Código de la base", compute='_compute_local_py_licencia_uuid',
        help="Versión de Odoo del módulo e identificador único de esta base de "
             "datos, separados por «|». Es lo que FC_Py necesita para emitir o "
             "renovar la licencia: cópielo y envíeselo tal cual, sin separarlo.")
    local_py_licencia_codigo = fields.Text(
        string="Código de licencia",
        help="Código entregado por FC_Py para esta base de datos. Péguelo tal cual "
             "lo recibió, sin agregar ni quitar espacios o saltos de línea.")
    local_py_licencia_cliente = fields.Char(
        string="Licencia emitida a", compute='_compute_local_py_licencia')
    local_py_licencia_vencimiento = fields.Date(
        string="Vencimiento de la licencia", compute='_compute_local_py_licencia')
    local_py_licencia_estado = fields.Selection([
        ('sin_licencia', "Sin licencia"),
        ('valida', "Válida"),
        ('vencida', "Vencida"),
        ('invalida', "Código inválido"),
        ('otra_version', "No corresponde a esta versión"),
    ], string="Estado de la licencia", compute='_compute_local_py_licencia')

    def _local_py_licencia_uuid_actual(self):
        return self.env['ir.config_parameter'].sudo().get_param('database.uuid') or ''

    def _compute_local_py_licencia_uuid(self):
        uuid_actual = self._local_py_licencia_uuid_actual()
        version_actual = local_py_version_odoo_instalada()
        texto_version = str(version_actual) if version_actual is not None else '?'
        for company in self:
            company.local_py_licencia_uuid = "%s|%s" % (texto_version, uuid_actual)

    @api.depends('local_py_licencia_codigo')
    def _compute_local_py_licencia(self):
        uuid_actual = self._local_py_licencia_uuid_actual()
        version_actual = local_py_version_odoo_instalada()
        hoy = fields.Date.context_today(self)
        for company in self:
            cliente = False
            vencimiento = False
            codigo = company.local_py_licencia_codigo
            if not codigo or not codigo.strip():
                estado = 'sin_licencia'
            else:
                try:
                    datos = local_py_decodificar_licencia(codigo)
                except ValueError:
                    estado = 'invalida'
                else:
                    cliente = datos['cliente']
                    vencimiento = fields.Date.from_string(datos['vence'])
                    if datos['uuid'] != uuid_actual:
                        estado = 'invalida'
                    elif datos['version_odoo'] != version_actual:
                        estado = 'otra_version'
                    elif vencimiento < hoy:
                        estado = 'vencida'
                    else:
                        estado = 'valida'
            company.local_py_licencia_cliente = cliente
            company.local_py_licencia_vencimiento = vencimiento
            company.local_py_licencia_estado = estado

    def _local_py_licencia_valida(self):
        """True si la compañía tiene una licencia vigente para esta base y versión."""
        self.ensure_one()
        return self.local_py_licencia_estado == 'valida'

    l10n_py_imputacion_tributaria_ids = fields.Many2many(
        'local_py.imputacion_tributaria',
        string='Imputación Tributaria',
        help='Régimen(es) tributario(s) bajo el/los que opera la compañía '
             '(IVA, IRE, IRP-RSP). "No Imputa" no puede combinarse con las '
             'otras opciones.',
    )

    @api.onchange('l10n_py_imputacion_tributaria_ids')
    def _onchange_l10n_py_imputacion_tributaria_ids(self):
        no_imputa = self.env.ref('local_py.imputacion_no_imputa', raise_if_not_found=False)
        if not no_imputa:
            return
        for company in self:
            current = company.l10n_py_imputacion_tributaria_ids
            previous = company._origin.l10n_py_imputacion_tributaria_ids
            added = current - previous
            if no_imputa in added:
                company.l10n_py_imputacion_tributaria_ids = current.filtered(lambda t: t.id == no_imputa.id)
            elif no_imputa in current and (current - no_imputa):
                company.l10n_py_imputacion_tributaria_ids = current - no_imputa

    @api.constrains('l10n_py_imputacion_tributaria_ids')
    def _check_l10n_py_imputacion_tributaria_exclusiva(self):
        no_imputa = self.env.ref('local_py.imputacion_no_imputa', raise_if_not_found=False)
        if not no_imputa:
            return
        for company in self:
            tags = company.l10n_py_imputacion_tributaria_ids
            if no_imputa in tags and len(tags) > 1:
                raise exceptions.ValidationError(
                    '"No Imputa" no puede combinarse con IVA, IRE o IRP-RSP en la '
                    'imputación tributaria de la compañía.'
                )
