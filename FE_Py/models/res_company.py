# -*- coding: utf-8 -*-
"""Espejo técnico de la Configuración FEPy sobre res.company.

La configuración de Facturación Electrónica ya NO vive en la Compañía:
vive en fe_py.configuracion (Localización Paraguay > Facturación
Electrónica Py > Configuraciones Generales FEPy). En Ajustes > Empresas
queda únicamente lo nativo de Odoo.

Estos campos son de SOLO LECTURA y no se muestran en ninguna vista. Son
un atajo interno para que el resto del módulo pueda seguir escribiendo
`company.fe_py_ambiente` sin tener que buscar la configuración en cada
lugar. El dato real, el editable, está siempre en fe_py.configuracion.

La excepción son los campos de licencia del producto (`fe_py_licencia_*`),
que SÍ viven en la Compañía y SÍ se editan: se exponen en Ajustes >
Configuración FE_Py y en el menú Licencia FE_Py. Están acá a propósito, y
no en fe_py.configuracion, porque ese modelo tiene la edición bloqueada
cuando no hay licencia válida: si el código estuviera ahí, no habría forma
de cargarlo ni de renovarlo.
"""

from odoo import api, fields, models

from .fe_py_licencia import (
    fe_py_decodificar_licencia,
    fe_py_version_odoo_instalada,
)


class ResCompany(models.Model):
    _inherit = 'res.company'

    fe_py_configuracion_id = fields.Many2one(
        'fe_py.configuracion', string='Configuración FEPy',
        compute='_compute_fe_py_configuracion', store=False,
    )

    # -- Espejo de solo lectura, para uso interno del módulo -------------
    fe_py_habilitado = fields.Boolean(
        related='fe_py_configuracion_id.habilitado', readonly=True)
    fe_py_ambiente = fields.Selection(
        related='fe_py_configuracion_id.ambiente', readonly=True)
    fe_py_cert_path = fields.Char(
        related='fe_py_configuracion_id.cert_path', readonly=True)
    fe_py_private_key_path = fields.Char(
        related='fe_py_configuracion_id.private_key_path', readonly=True)
    fe_py_public_key_path = fields.Char(
        related='fe_py_configuracion_id.public_key_path', readonly=True)
    fe_py_idcsc = fields.Char(
        related='fe_py_configuracion_id.idcsc', readonly=True)
    fe_py_csc = fields.Char(
        related='fe_py_configuracion_id.csc', readonly=True)
    fe_py_envio_automatico = fields.Boolean(
        related='fe_py_configuracion_id.envio_automatico', readonly=True)
    fe_py_kude_automatico = fields.Boolean(
        related='fe_py_configuracion_id.kude_automatico', readonly=True)
    fe_py_email_automatico = fields.Boolean(
        related='fe_py_configuracion_id.email_automatico', readonly=True)
    fe_py_reintento_automatico = fields.Boolean(
        related='fe_py_configuracion_id.reintento_automatico', readonly=True)

    @api.depends_context('company')
    def _compute_fe_py_configuracion(self):
        Config = self.env['fe_py.configuracion'].sudo()
        for company in self:
            company.fe_py_configuracion_id = Config.search(
                [('company_id', '=', company.id)], limit=1,
            )

    # -- Licencia del producto (OPL-1) --------------------------------------
    # Independiente de la licencia de local_py: cada módulo exige su propio
    # código (campo `p` del payload), aunque el «Código de la base» que el
    # cliente copia sea el mismo valor en los dos.
    fe_py_licencia_uuid = fields.Char(
        string="Código de la base", compute='_compute_fe_py_licencia_uuid',
        help="Versión de Odoo del módulo e identificador único de esta base de "
             "datos, separados por «|». Es lo que FC_Py necesita para emitir o "
             "renovar la licencia: cópielo y envíeselo tal cual, sin separarlo.")
    fe_py_licencia_codigo = fields.Text(
        string="Código de licencia",
        help="Código entregado por FC_Py para esta base de datos. Péguelo tal cual "
             "lo recibió, sin agregar ni quitar espacios o saltos de línea. El "
             "código de local_py no sirve acá: son licencias independientes.")
    fe_py_licencia_cliente = fields.Char(
        string="Licencia emitida a", compute='_compute_fe_py_licencia')
    fe_py_licencia_vencimiento = fields.Date(
        string="Vencimiento de la licencia", compute='_compute_fe_py_licencia')
    fe_py_licencia_estado = fields.Selection([
        ('sin_licencia', "Sin licencia"),
        ('valida', "Válida"),
        ('vencida', "Vencida"),
        ('invalida', "Código inválido"),
        ('otra_version', "No corresponde a esta versión"),
    ], string="Estado de la licencia", compute='_compute_fe_py_licencia')

    def _fe_py_licencia_uuid_actual(self):
        return self.env['ir.config_parameter'].sudo().get_param('database.uuid') or ''

    def _compute_fe_py_licencia_uuid(self):
        uuid_actual = self._fe_py_licencia_uuid_actual()
        version_actual = fe_py_version_odoo_instalada()
        texto_version = str(version_actual) if version_actual is not None else '?'
        for company in self:
            company.fe_py_licencia_uuid = "%s|%s" % (texto_version, uuid_actual)

    @api.depends('fe_py_licencia_codigo')
    def _compute_fe_py_licencia(self):
        uuid_actual = self._fe_py_licencia_uuid_actual()
        version_actual = fe_py_version_odoo_instalada()
        hoy = fields.Date.context_today(self)
        for company in self:
            cliente = False
            vencimiento = False
            codigo = company.fe_py_licencia_codigo
            if not codigo or not codigo.strip():
                estado = 'sin_licencia'
            else:
                try:
                    datos = fe_py_decodificar_licencia(codigo)
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
            company.fe_py_licencia_cliente = cliente
            company.fe_py_licencia_vencimiento = vencimiento
            company.fe_py_licencia_estado = estado

    def _fe_py_licencia_valida(self):
        """True si la compañía tiene una licencia vigente de FE_Py para esta base
        y esta versión. No mira la licencia de local_py: son independientes."""
        self.ensure_one()
        return self.fe_py_licencia_estado == 'valida'
