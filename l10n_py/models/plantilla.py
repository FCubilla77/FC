# -*- coding: utf-8 -*-
import base64
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.modules.module import get_module_path

from . import plantilla_excel as excel


class L10nPyPlantilla(models.Model):
    """Archivo Excel del plan de cuentas del cliente, ya leído y validado.

    Guarda el archivo original, el resultado de la validación (errores y avisos) y,
    si no hubo errores, los datos listos para cargar. La plantilla se usa SOLO para la
    carga inicial del plan: una vez cargada queda en estado «Cargada»."""
    _name = 'l10n_py.plantilla'
    _description = 'Plantilla del plan de cuentas del cliente (Excel)'
    _order = 'fecha desc, id desc'

    company_id = fields.Many2one('res.company', string='Compañía', required=True, readonly=True)
    nombre_archivo = fields.Char(string='Archivo', readonly=True)
    archivo = fields.Binary(string='Archivo Excel', attachment=True, readonly=True)
    fecha = fields.Datetime(string='Fecha', default=fields.Datetime.now, readonly=True)
    usuario_id = fields.Many2one('res.users', string='Cargado por', default=lambda self: self.env.user,
                                 readonly=True)
    state = fields.Selection([
        ('error', 'Con errores'),
        ('validada', 'Validada, lista para cargar'),
        ('cargada', 'Cargada'),
    ], string='Estado', required=True, readonly=True)
    cantidad_errores = fields.Integer(string='Errores', readonly=True)
    cantidad_avisos = fields.Integer(string='Avisos', readonly=True)
    log = fields.Text(string='Resultado de la validación', readonly=True)
    datos = fields.Text(string='Datos validados (JSON)', readonly=True)
    active = fields.Boolean(default=True)

    # -- Plantilla Excel descargable con el plan estándar ------------------------------

    @api.model
    def _contenido_plantilla_estandar(self):
        return excel.generar_libro(excel.datos_estandar(get_module_path('l10n_py')))

    # -- Lectura y validación -------------------------------------------------------------

    @api.model
    def _validar_y_guardar(self, company, nombre_archivo, contenido):
        """Lee y valida el Excel; guarda el resultado. Devuelve el registro creado."""
        if company.parent_id:
            raise UserError(_(
                "El plan de cuentas se carga en la compañía principal (%s); las "
                "subsidiarias lo comparten.", company.root_id.name))
        if company.chart_template == 'py':
            raise UserError(_(
                "%s ya tiene el plan de cuentas Paraguay cargado. La plantilla del cliente "
                "solo sirve para la carga inicial; los cambios posteriores se hacen en el "
                "sistema.", company.name))
        monedas = set(self.env['res.currency'].with_context(active_test=False).search([]).mapped('name'))
        datos, errores, avisos = excel.leer_libro(contenido, monedas)

        lineas = []
        if datos is not None and not errores:
            lineas.append(_(
                "Resumen: %(g)s grupos, %(c)s cuentas, %(i)s impuestos, %(p)s posiciones "
                "fiscales, %(t)s plazos de pago.",
                g=len(datos['grupos']), c=len(datos['cuentas']), i=len(datos['impuestos']),
                p=len(datos['posiciones_fiscales']), t=len(datos['plazos_pago'])))
        if errores:
            lineas.append(_("ERRORES (hay que corregirlos para poder cargar la plantilla):"))
            lineas += ['  • %s' % e for e in errores]
        if avisos:
            lineas.append(_("AVISOS (no impiden la carga):"))
            lineas += ['  • %s' % a for a in avisos]
        if not errores:
            lineas.append(_("La plantilla es válida. Ya puede cargarla desde Ajustes > Facturación > "
                            "Localización Fiscal, seleccionando el paquete «Paraguay»."))

        plantilla = self.sudo().create({
            'company_id': company.id,
            'nombre_archivo': nombre_archivo,
            'archivo': base64.b64encode(contenido),
            'state': 'error' if errores else 'validada',
            'cantidad_errores': len(errores),
            'cantidad_avisos': len(avisos),
            'log': '\n'.join(lineas),
            'datos': json.dumps(datos) if not errores else False,
        })
        if not errores:
            self.sudo().search([
                ('company_id', '=', company.id), ('id', '!=', plantilla.id),
                ('state', '!=', 'cargada')]).write({'active': False})
            company.sudo().l10n_py_plantilla_id = plantilla
        return plantilla

    def _datos(self):
        self.ensure_one()
        return json.loads(self.datos) if self.datos else None
