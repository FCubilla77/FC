# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

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

    l10n_py_cuenta_resultado_ejercicio_id = fields.Many2one(
        'account.account', string="Cuenta Resultado del Ejercicio", ondelete='restrict',
        domain="[('account_type', 'in', ('equity', 'equity_unaffected')), ('company_ids', 'in', id)]",
        help="Cuenta de Patrimonio donde el proceso de Cierre de Ejercicio deja el "
             "resultado (ganancia o pérdida) del año. Con el plan de cuentas Paraguay "
             "se asigna sola. Si queda vacía, se usa la cuenta de tipo «Ganancias del "
             "año actual» de la compañía.")

    @api.constrains('l10n_py_cuenta_resultado_ejercicio_id')
    def _check_l10n_py_cuenta_resultado_ejercicio(self):
        for company in self:
            cuenta = company.l10n_py_cuenta_resultado_ejercicio_id
            if not cuenta:
                continue
            if cuenta.account_type not in ('equity', 'equity_unaffected'):
                raise ValidationError(_(
                    "La cuenta Resultado del Ejercicio debe ser de tipo Patrimonio "
                    "(Capital o Ganancias del año actual)."))
            if company not in cuenta.company_ids:
                raise ValidationError(_(
                    "La cuenta Resultado del Ejercicio debe pertenecer a la compañía %s.",
                    company.name))

    def _l10n_py_cuenta_resultado_ejercicio(self):
        """Cuenta que recibe el resultado en el Cierre de Ejercicio: la configurada en
        la compañía o, si no hay, la cuenta de tipo «Ganancias del año actual»."""
        self.ensure_one()
        cuenta = self.l10n_py_cuenta_resultado_ejercicio_id
        if not cuenta:
            cuenta = self.env['account.account'].with_company(self).search([
                ('company_ids', 'in', self.id),
                ('account_type', '=', 'equity_unaffected'),
            ], limit=1)
        if not cuenta:
            raise UserError(_(
                "No hay una cuenta Resultado del Ejercicio para %s. Defínala en "
                "Ajustes > Configuración l10n_py, o cree una cuenta de tipo «Ganancias "
                "del año actual».", self.name))
        return cuenta

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
