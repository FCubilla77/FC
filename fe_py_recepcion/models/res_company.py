# -*- coding: utf-8 -*-
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .fe_py_recepcion_licencia import (
    fe_py_recepcion_decodificar_licencia, fe_py_recepcion_version_odoo_instalada)


class ResCompany(models.Model):
    """Configuración de la recepción de facturas electrónicas y su licencia.

    Los campos viven en la compañía y se muestran en Ajustes (res.config.settings),
    igual que la licencia de local_py y l10n_py."""
    _inherit = 'res.company'

    # ------------------------------------------------------------------
    # Recepción por correo
    # ------------------------------------------------------------------
    fe_py_recepcion_fetchmail_id = fields.Many2one(
        'fetchmail.server', string='Cuenta de correo de recepción', copy=False, ondelete='set null',
        groups='base.group_system',
        domain="[('object_id.model', '=', 'fe_py_recepcion.documento')]",
        help='Servidor de correo entrante (IMAP/POP) del que se leen las facturas electrónicas '
             'recibidas. Debe ser una casilla exclusiva de esta compañía, distinta de las que '
             'usa el resto del sistema: solo se leen los correos no leídos.')

    _fe_py_recepcion_fetchmail_uniq = models.Constraint(
        'unique(fe_py_recepcion_fetchmail_id)',
        'Una cuenta de correo de recepción solo puede pertenecer a una compañía.')

    @api.constrains('fe_py_recepcion_fetchmail_id')
    def _check_fe_py_recepcion_fetchmail(self):
        for company in self.sudo():
            servidor = company.fe_py_recepcion_fetchmail_id
            if servidor and servidor.object_id.model != 'fe_py_recepcion.documento':
                raise ValidationError(_(
                    'La cuenta "%s" no es una cuenta de recepción de FE_Py: debe crear un nuevo '
                    'registro con el botón "Configurar cuenta de correo" de Ajustes.', servidor.name))

    def fe_py_recepcion_abrir_cuenta_correo(self):
        """Abre la cuenta de correo de la compañía; si todavía no tiene, crea una propia."""
        self.ensure_one()
        servidor = self.sudo().fe_py_recepcion_fetchmail_id
        if not servidor:
            # reutiliza una cuenta de recepción que haya quedado sin compañía, antes de crear otra
            Company = self.env['res.company'].sudo()
            libres = self.env['fetchmail.server'].sudo().search(
                [('object_id.model', '=', 'fe_py_recepcion.documento')]).filtered(
                lambda s: not Company.search_count([('fe_py_recepcion_fetchmail_id', '=', s.id)]))
            if len(libres) == 1:
                servidor = libres
                self.sudo().fe_py_recepcion_fetchmail_id = servidor
        if not servidor:
            servidor = self.env['fetchmail.server'].sudo().create({
                'name': _('FE_Py Recepción - %s', self.name),
                'object_id': self.env['ir.model']._get('fe_py_recepcion.documento').id,
                'server_type': 'imap', 'is_ssl': True, 'port': 993,
                'attach': True, 'original': False,
            })
            self.sudo().fe_py_recepcion_fetchmail_id = servidor
        return {
            'type': 'ir.actions.act_window', 'name': _('Cuenta de correo de recepción'),
            'res_model': 'fetchmail.server', 'res_id': servidor.id,
            'view_mode': 'form', 'target': 'current',
        }

    # ------------------------------------------------------------------
    # Diarios e impuestos
    # ------------------------------------------------------------------
    fe_py_recepcion_diario_id = fields.Many2one(
        'account.journal', string='Diario para facturas recibidas',
        domain="[('type', '=', 'purchase'), ('company_id', '=', id)]",
        help='Diario de compra con el que se generan las facturas de proveedor. Se puede '
             'cambiar en cada recepción. La factura toma el Tipo Fiscal de su diario.')
    fe_py_recepcion_diario_nc_id = fields.Many2one(
        'account.journal', string='Diario para notas de crédito recibidas',
        domain="[('type', '=', 'purchase'), ('company_id', '=', id)]",
        help='Diario de compra con el que se generan las notas de crédito de proveedor.')
    fe_py_recepcion_diario_nd_id = fields.Many2one(
        'account.journal', string='Diario para notas de débito recibidas',
        domain="[('type', '=', 'purchase'), ('company_id', '=', id)]",
        help='Diario de compra con el que se generan las notas de débito de proveedor.')
    fe_py_recepcion_impuesto_iva10_id = fields.Many2one(
        'account.tax', string='Impuesto IVA 10%',
        domain="[('type_tax_use', '=', 'purchase'), ('company_id', '=', id)]",
        help='Impuesto de compra para las líneas con IVA 10%. Los precios del XML '
             'ya incluyen el IVA, así que debe tener "Incluido en el precio".')
    fe_py_recepcion_impuesto_iva5_id = fields.Many2one(
        'account.tax', string='Impuesto IVA 5%',
        domain="[('type_tax_use', '=', 'purchase'), ('company_id', '=', id)]",
        help='Impuesto de compra para las líneas con IVA 5% (con IVA incluido en el precio).')
    fe_py_recepcion_impuesto_exento_id = fields.Many2one(
        'account.tax', string='Impuesto Exento',
        domain="[('type_tax_use', '=', 'purchase'), ('company_id', '=', id)]",
        help='Impuesto de compra (0%) para las líneas exentas.')

    # ------------------------------------------------------------------
    # Licencia
    # ------------------------------------------------------------------
    fe_py_recepcion_licencia_uuid = fields.Char(
        string='Código de la base', compute='_compute_fe_py_recepcion_licencia_uuid')
    fe_py_recepcion_licencia_codigo = fields.Text(string='Código de licencia', copy=False)
    fe_py_recepcion_licencia_cliente = fields.Char(
        string='Cliente', compute='_compute_fe_py_recepcion_licencia')
    fe_py_recepcion_licencia_vencimiento = fields.Date(
        string='Vencimiento', compute='_compute_fe_py_recepcion_licencia')
    fe_py_recepcion_licencia_estado = fields.Selection(
        [('sin_licencia', 'Sin licencia'), ('valida', 'Válida'), ('vencida', 'Vencida'),
         ('invalida', 'Inválida'), ('otra_version', 'Otra versión')],
        string='Estado de la licencia', compute='_compute_fe_py_recepcion_licencia')

    @api.model
    def _fe_py_recepcion_licencia_uuid_actual(self):
        return self.env['ir.config_parameter'].sudo().get_param('database.uuid') or ''

    def _compute_fe_py_recepcion_licencia_uuid(self):
        """«versión|uuid»: lo que el cliente le envía a FC_Py para pedir la licencia."""
        uuid = self._fe_py_recepcion_licencia_uuid_actual()
        version = fe_py_recepcion_version_odoo_instalada()
        for company in self:
            company.fe_py_recepcion_licencia_uuid = '%s|%s' % (
                version if version is not None else 0, uuid)

    @api.depends('fe_py_recepcion_licencia_codigo')
    def _compute_fe_py_recepcion_licencia(self):
        uuid_actual = self._fe_py_recepcion_licencia_uuid_actual()
        version_instalada = fe_py_recepcion_version_odoo_instalada()
        hoy = date.today()
        for company in self:
            company.fe_py_recepcion_licencia_cliente = False
            company.fe_py_recepcion_licencia_vencimiento = False
            codigo = company.fe_py_recepcion_licencia_codigo
            if not codigo or not codigo.strip():
                company.fe_py_recepcion_licencia_estado = 'sin_licencia'
                continue
            try:
                datos = fe_py_recepcion_decodificar_licencia(codigo)
            except ValueError:
                company.fe_py_recepcion_licencia_estado = 'invalida'
                continue
            vence = date.fromisoformat(datos['vence'])
            company.fe_py_recepcion_licencia_cliente = datos['cliente']
            company.fe_py_recepcion_licencia_vencimiento = vence
            if datos['uuid'] != uuid_actual:
                company.fe_py_recepcion_licencia_estado = 'invalida'
            elif version_instalada is None or datos['version_odoo'] != version_instalada:
                company.fe_py_recepcion_licencia_estado = 'otra_version'
            elif vence < hoy:
                company.fe_py_recepcion_licencia_estado = 'vencida'
            else:
                company.fe_py_recepcion_licencia_estado = 'valida'

    def _fe_py_recepcion_licencia_valida(self):
        self.ensure_one()
        return self.fe_py_recepcion_licencia_estado == 'valida'

    # ------------------------------------------------------------------
    # Diario según el tipo de documento recibido
    # ------------------------------------------------------------------
    def _fe_py_recepcion_diario_por_itide(self, itide):
        """Diario configurado para el tipo de documento del XML (iTiDE 1, 5 o 6)."""
        self.ensure_one()
        return {
            '1': self.fe_py_recepcion_diario_id,
            '5': self.fe_py_recepcion_diario_nc_id,
            '6': self.fe_py_recepcion_diario_nd_id,
        }.get(str(itide), self.env['account.journal'])
