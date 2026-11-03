# -*- coding: utf-8 -*-
from odoo import api, fields, models

from .l10n_py_licencia import (
    l10n_py_decodificar_licencia,
    l10n_py_version_odoo_instalada,
)


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_py_licencia_uuid = fields.Char(
        string="Código de la base", compute='_compute_l10n_py_licencia_uuid',
        help="Versión de Odoo del módulo y identificador único de esta base de datos, "
             "separados por «|». Es lo que FC_Py necesita para emitir o renovar la "
             "licencia: copielo y envíeselo tal cual, sin separarlo.")
    l10n_py_licencia_codigo = fields.Text(
        string="Código de licencia",
        help="Código entregado por FC_Py para esta base de datos. Péguelo tal cual lo "
             "recibió, sin agregar ni quitar espacios o saltos de línea.")
    l10n_py_licencia_cliente = fields.Char(
        string="Licencia emitida a", compute='_compute_l10n_py_licencia')
    l10n_py_licencia_vencimiento = fields.Date(
        string="Vencimiento de la licencia", compute='_compute_l10n_py_licencia')
    l10n_py_licencia_estado = fields.Selection([
        ('sin_licencia', "Sin licencia"),
        ('valida', "Válida"),
        ('vencida', "Vencida"),
        ('invalida', "Código inválido"),
        ('otra_version', "No corresponde a esta versión"),
    ], string="Estado de la licencia", compute='_compute_l10n_py_licencia')

    def _l10n_py_licencia_uuid_actual(self):
        return self.env['ir.config_parameter'].sudo().get_param('database.uuid') or ''

    def _compute_l10n_py_licencia_uuid(self):
        uuid_actual = self._l10n_py_licencia_uuid_actual()
        version_actual = l10n_py_version_odoo_instalada()
        texto_version = str(version_actual) if version_actual is not None else '?'
        for company in self:
            company.l10n_py_licencia_uuid = "%s|%s" % (texto_version, uuid_actual)

    @api.depends('l10n_py_licencia_codigo')
    def _compute_l10n_py_licencia(self):
        uuid_actual = self._l10n_py_licencia_uuid_actual()
        version_actual = l10n_py_version_odoo_instalada()
        hoy = fields.Date.context_today(self)
        for company in self:
            cliente = False
            vencimiento = False
            codigo = company.l10n_py_licencia_codigo
            if not codigo or not codigo.strip():
                estado = 'sin_licencia'
            else:
                try:
                    datos = l10n_py_decodificar_licencia(codigo)
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
            company.l10n_py_licencia_cliente = cliente
            company.l10n_py_licencia_vencimiento = vencimiento
            company.l10n_py_licencia_estado = estado

    def _l10n_py_licencia_valida(self):
        """True si la compañía tiene una licencia vigente para esta base y versión."""
        self.ensure_one()
        return self.l10n_py_licencia_estado == 'valida'

    def install_l10n_modules(self):
        """La carga automática del paquete al crear/editar una compañía con país no
        debe fallar si todavía no hay licencia: se marca el contexto para que el
        control de `try_loading` omita la carga en silencio en ese caso (el paquete
        queda sin asignar hasta que el usuario lo seleccione con licencia válida)."""
        return super(ResCompany, self.with_context(l10n_py_licencia_auto=True)).install_l10n_modules()
