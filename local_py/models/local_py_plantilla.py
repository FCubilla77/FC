# -*- coding: utf-8 -*-
"""Plantilla Excel de configuración de local_py: registro, validación y aplicación.

local_py no asume ningún plan de cuentas. En lugar de completar su configuración con
códigos fijos del plan estándar de Paraguay (que era lo que hacía `hooks.py`, y solo
funcionaba con ese plan), el usuario descarga una planilla, indica qué cuenta de SU
plan cumple cada función y la sube. Si la validación no encuentra errores, se aplica
toda la configuración de una sola vez.

Toda la lógica de formato y validación está en `local_py_plantilla_excel.py`, que no
usa el ORM. Este archivo hace dos cosas: armar el contexto de validación con los datos
de la base, y volcar los datos ya validados en registros de Odoo.
"""
import base64
import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from . import local_py_plantilla_excel as excel
from .local_py_licencia import local_py_licencia_verificar

_logger = logging.getLogger(__name__)


class LocalPyPlantilla(models.Model):
    """Archivo Excel de configuración de local_py, ya leído y validado.

    Guarda el archivo original, el resultado de la validación (errores y avisos) y, si
    no hubo errores, los datos listos para aplicar. Aplicar es idempotente y no
    invasivo: crea lo que falta y completa lo que está vacío, nunca pisa una elección
    hecha a mano ni borra nada."""
    _name = 'local_py.plantilla'
    _description = 'Plantilla de configuración de local_py (Excel)'
    _order = 'fecha desc, id desc'

    company_id = fields.Many2one('res.company', string='Empresa', required=True, readonly=True)
    nombre_archivo = fields.Char(string='Archivo', readonly=True)
    archivo = fields.Binary(string='Archivo Excel', attachment=True, readonly=True)
    fecha = fields.Datetime(string='Fecha', default=fields.Datetime.now, readonly=True)
    usuario_id = fields.Many2one('res.users', string='Cargado por', readonly=True,
                                 default=lambda self: self.env.user)
    state = fields.Selection([
        ('error', 'Con errores'),
        ('validada', 'Validada, lista para aplicar'),
        ('aplicada', 'Aplicada'),
    ], string='Estado', required=True, readonly=True)
    cantidad_errores = fields.Integer(string='Errores', readonly=True)
    cantidad_avisos = fields.Integer(string='Avisos', readonly=True)
    log = fields.Text(string='Resultado de la validación', readonly=True)
    datos = fields.Text(string='Datos validados (JSON)', readonly=True)
    active = fields.Boolean(default=True)

    # ------------------------------------------------------------------
    # Contexto de validación: lo que hay en la base
    # ------------------------------------------------------------------
    @api.model
    def _contexto(self, company):
        """Datos de la base contra los que `local_py_plantilla_excel` valida la planilla.

        Cada clave que se omite desactiva esa validación, así que se arman todas: es
        mejor que el usuario vea el error en el informe de la planilla que al aplicarla.
        """
        company = company.sudo()
        cuentas = self.env['account.account'].sudo().search([('company_ids', 'in', company.id)])
        diarios = self.env['account.journal'].sudo().search([('company_id', '=', company.id)])
        bancos_propios = self.env['res.partner.bank'].sudo().search([
            ('partner_id', '=', company.partner_id.id)])
        return {
            'cuentas': {c.code: c.account_type for c in cuentas if c.code},
            'diarios': {d.code: d.type for d in diarios if d.code},
            'diarios_banco': [d.code for d in diarios if d.type == 'bank' and d.code],
            'tipos_fiscales': self.env['local_py.tipo_fiscal'].sudo().search([]).mapped('name'),
            'conceptos_iva': self.env['local_py.concepto_iva'].sudo().search([]).mapped('codigo'),
            'imputaciones': self.env['local_py.imputacion_tributaria'].sudo().search([]).mapped('name'),
            'monedas': self.env['res.currency'].sudo().with_context(
                active_test=False).search([]).mapped('name'),
            'bancos': self.env['res.bank'].sudo().search([]).mapped('name'),
            'cuentas_bancarias': bancos_propios.mapped('acc_number'),
            'usuarios': self.env['res.users'].sudo().with_context(
                active_test=False).search([]).mapped('login'),
            'rucs': [p for p in self.env['res.partner'].sudo().search(
                [('vat', '!=', False)]).mapped('vat') if p],
            'codigos_inr': self.env['local_py.concepto_renta_no_residente'].sudo().with_context(
                active_test=False).search([]).mapped('codigo'),
        }

    # ------------------------------------------------------------------
    # Plantilla descargable
    # ------------------------------------------------------------------
    @api.model
    def _contenido_plantilla_ejemplo(self, company=None):
        """Contenido (bytes) del .xlsx que se descarga: valores del plan estándar de
        Paraguay como ejemplo en las hojas de clave/valor, filas de ejemplo marcadas con
        «#» en las hojas de lista, y los conceptos de Renta No Residente reales de la
        base (son un catálogo que trae local_py: no se agregan desde la planilla)."""
        company = company or self.env.company
        datos = excel.datos_ejemplo()
        conceptos = self.env['local_py.concepto_renta_no_residente'].sudo().search([])
        datos['conceptos_inr'] = [{
            'codigo': c.codigo, 'nombre': c.name,
            'porcentaje_imputacion': c.porcentaje_imputacion,
            'porcentaje': c.porcentaje,
            'porcentaje_absorcion': c.porcentaje_absorcion,
        } for c in conceptos]
        return excel.generar_libro(datos, self._contexto(company))

    # ------------------------------------------------------------------
    # Lectura y validación
    # ------------------------------------------------------------------
    @api.model
    def _validar_y_guardar(self, company, nombre_archivo, contenido):
        """Lee y valida el Excel; guarda el resultado. Devuelve el registro creado."""
        if company.parent_id:
            raise UserError(_(
                "La configuración de local_py se carga en la empresa principal (%s).",
                company.root_id.name))
        datos, errores, avisos = excel.leer_libro(contenido, self._contexto(company))

        lineas = []
        if datos is not None and not errores:
            lineas.append(_("Resumen: %s", excel.resumen(datos)))
        if errores:
            lineas.append(_("La plantilla tiene errores y NO se guardó como válida: no se puede "
                            "aplicar hasta corregirlos. Corrija el Excel y vuelva a subirlo."))
            lineas.append(_("ERRORES:"))
            lineas += ['  • %s' % e for e in errores]
        if avisos:
            lineas.append(_("AVISOS (no impiden aplicar la configuración):"))
            lineas += ['  • %s' % a for a in avisos]
        if not errores:
            lineas.append(_("La plantilla es válida. Ya puede aplicarla desde Ajustes > "
                            "Configuración local_py > Configuración por plantilla."))

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
            # Solo una plantilla pendiente por empresa: la anterior se archiva.
            self.sudo().search([
                ('company_id', '=', company.id), ('id', '!=', plantilla.id),
                ('state', '!=', 'aplicada')]).write({'active': False})
            company.sudo().local_py_plantilla_id = plantilla
        return plantilla

    def _datos(self):
        self.ensure_one()
        return json.loads(self.datos) if self.datos else None

    # ------------------------------------------------------------------
    # Aplicación
    # ------------------------------------------------------------------
    def aplicar(self):
        """Aplica la configuración de la plantilla. Devuelve el texto del informe.

        Todo en una sola transacción: si algo falla (una constraint del propio módulo,
        por ejemplo), no queda nada aplicado a medias. Idempotente: se puede volver a
        aplicar sin duplicar nada."""
        self.ensure_one()
        local_py_licencia_verificar(self.env, self.company_id)
        if self.state == 'error':
            raise UserError(_("La plantilla tiene errores: corríjalos y vuelva a subirla."))
        datos = self._datos()
        if not datos:
            raise UserError(_("La plantilla no tiene datos validados. Vuelva a subirla."))

        company = self.company_id
        hechos = []
        config = self._config(company)
        cuentas = self._mapa_cuentas(company)

        hechos += self._aplicar_diarios(company, config, cuentas, datos)
        hechos += self._aplicar_cuentas(config, cuentas, datos)
        hechos += self._aplicar_parametros(company, config, datos)
        hechos += self._aplicar_diarios_fiscales(company, datos)
        hechos += self._aplicar_series(company, datos)
        hechos += self._aplicar_rubricas(company, datos)
        hechos += self._aplicar_chequeras(company, datos)
        hechos += self._aplicar_detalle_inventario(config, cuentas, datos)
        hechos += self._aplicar_renumeracion(config, datos)
        hechos += self._aplicar_no_retencion(config, datos)
        hechos += self._aplicar_conceptos_inr(datos)

        informe = '\n'.join('  • %s' % h for h in hechos) or _("  • No había nada para aplicar.")
        self.sudo().write({
            'state': 'aplicada',
            'log': '%s\n\n%s\n%s' % (self.log or '', _("CONFIGURACIÓN APLICADA:"), informe),
        })
        _logger.info("local_py: configuración aplicada desde la plantilla «%s» (%s acciones).",
                     self.nombre_archivo or '', len(hechos))
        return informe

    # -- helpers de aplicación ----------------------------------------
    def _config(self, company):
        """Configuraciones Localización Py de la empresa; la crea si no existe."""
        Config = self.env['local_py.configuracion_localizacion'].sudo()
        config = Config.search([('company_id', '=', company.id)], limit=1)
        return config or Config.create({'company_id': company.id})

    def _mapa_cuentas(self, company):
        cuentas = self.env['account.account'].sudo().search([('company_ids', 'in', company.id)])
        return {c.code: c for c in cuentas if c.code}

    def _aplicar_diarios(self, company, config, cuentas, datos):
        """Crea los diarios operativos que falten y los asigna en la Configuración.

        No modifica un diario que ya existe con ese código: se usa tal cual."""
        Journal = self.env['account.journal'].sudo()
        hechos = []
        for clave, valores in datos['diarios'].items():
            definicion = excel.DIARIOS_POR_CLAVE.get(clave)
            if not definicion:
                continue
            campo = definicion[6]
            diario = Journal.search([
                ('code', '=', valores['codigo']), ('company_id', '=', company.id)], limit=1)
            if not diario:
                vals = {'name': valores['nombre'], 'code': valores['codigo'],
                        'type': valores['tipo'], 'company_id': company.id}
                cuenta = cuentas.get(valores['cuenta'])
                if cuenta:
                    vals['default_account_id'] = cuenta.id
                diario = Journal.create(vals)
                hechos.append(_("Diario «%(nombre)s» (%(codigo)s) creado.",
                                nombre=valores['nombre'], codigo=valores['codigo']))
            if not config[campo]:
                config.write({campo: diario.id})
                hechos.append(_("%(descripcion)s: %(codigo)s.",
                                descripcion=definicion[1], codigo=valores['codigo']))
        return hechos

    def _aplicar_cuentas(self, config, cuentas, datos):
        hechos = []
        for clave, codigo in datos['cuentas'].items():
            definicion = excel.CUENTAS_POR_CLAVE.get(clave)
            cuenta = cuentas.get(codigo)
            if not definicion or not cuenta:
                continue
            campo = definicion[5]
            if not config[campo]:
                config.write({campo: cuenta.id})
                hechos.append(_("%(descripcion)s: %(codigo)s.",
                                descripcion=definicion[1], codigo=codigo))
        return hechos

    def _aplicar_parametros(self, company, config, datos):
        """Los parámetros SÍ se escriben aunque ya tengan valor: son la configuración
        que el usuario acaba de declarar en la planilla, no un dato que se complete
        «si falta» (a diferencia de las cuentas y los diarios, donde pisar una elección
        hecha a mano sería destructivo)."""
        hechos, vals = [], {}
        for clave, valor in datos['parametros'].items():
            definicion = excel.PARAMETROS_POR_CLAVE.get(clave)
            if not definicion:
                continue
            campo = definicion[4]
            if clave == 'imputacion_tributaria':
                if valor:
                    imputaciones = self.env['local_py.imputacion_tributaria'].sudo().search(
                        [('name', 'in', valor)])
                    company.sudo().local_py_imputacion_tributaria_ids = [(6, 0, imputaciones.ids)]
                    hechos.append(_("Imputación Tributaria: %s.", ', '.join(valor)))
                continue
            if clave == 'concepto_iva':
                concepto = self.env['local_py.concepto_iva'].sudo().search(
                    [('codigo', '=', valor)], limit=1) if valor else None
                if concepto:
                    vals[campo] = concepto.id
                    hechos.append(_("Concepto IVA predeterminado: %s.", valor))
                continue
            if not campo:
                continue
            vals[campo] = valor
        if vals:
            config.write(vals)
            hechos.append(_("%s parámetro(s) de la Configuración actualizados.", len(vals)))
        return hechos

    def _aplicar_diarios_fiscales(self, company, datos):
        """Diarios de VENTA con Timbrado. Si el diario ya existe se le completa la
        numeración fiscal; si no, se crea."""
        Journal = self.env['account.journal'].sudo()
        tipos = {t.name: t for t in self.env['local_py.tipo_fiscal'].sudo().search([])}
        hechos = []
        for d in datos['diarios_fiscales']:
            tipo_fiscal = tipos.get(d['tipo_fiscal'])
            numeracion = {
                'local_py_timbrado': d['timbrado'],
                'local_py_nro_documento': d['nro_documento'],
                'local_py_nro_documento_final': d['nro_documento_final'],
                'local_py_inicio_vigencia_timbrado': d['inicio_vigencia'] or False,
                'local_py_venc_timbrado': d['vencimiento'] or False,
                'local_py_tipo_fiscal_id': tipo_fiscal.id if tipo_fiscal else False,
            }
            diario = Journal.search([
                ('code', '=', d['codigo']), ('company_id', '=', company.id)], limit=1)
            if diario:
                diario.write(numeracion)
                hechos.append(_("Diario fiscal «%(nombre)s» (%(codigo)s): numeración actualizada.",
                                nombre=diario.name, codigo=d['codigo']))
            else:
                vals = dict(numeracion, name=d['nombre'], code=d['codigo'],
                            type='sale', company_id=company.id)
                Journal.create(vals)
                hechos.append(_("Diario fiscal «%(nombre)s» (%(codigo)s) creado con Timbrado "
                                "%(timbrado)s.", nombre=d['nombre'], codigo=d['codigo'],
                                timbrado=d['timbrado']))
        return hechos

    def _aplicar_series(self, company, datos):
        Serie = self.env['local_py.recibo.serie'].sudo()
        usuarios = {u.login: u for u in self.env['res.users'].sudo().with_context(
            active_test=False).search([])}
        hechos = []
        for s in datos['series_recibo']:
            usuario = usuarios.get(s['usuario'])
            if not usuario:
                continue
            if Serie.with_context(active_test=False).search([
                    ('name', '=', s['nombre']), ('user_id', '=', usuario.id),
                    ('company_id', '=', company.id)], limit=1):
                continue
            Serie.create({'name': s['nombre'], 'company_id': company.id, 'user_id': usuario.id,
                          'numero_inicial': s['numero_inicial'], 'numero_final': s['numero_final']})
            hechos.append(_("Serie de Recibo «%(serie)s» creada para %(usuario)s.",
                            serie=s['nombre'], usuario=s['usuario']))
        return hechos

    def _aplicar_rubricas(self, company, datos):
        """La imagen y la primera hoja de la Rúbrica no se pueden cargar por planilla
        (son archivos): se adjuntan después en la ficha de cada Rúbrica."""
        Rubrica = self.env['local_py.rubrica'].sudo()
        hechos = []
        for r in datos['rubricas']:
            if Rubrica.search([('idrubrica', '=', r['idrubrica']),
                               ('company_id', '=', company.id)], limit=1):
                continue
            Rubrica.create({
                'company_id': company.id, 'idrubrica': r['idrubrica'], 'fecha': r['fecha'],
                'uso': r['uso'], 'cantidad_hojas': r['cantidad_hojas'],
                'nro_entrada': r['nro_entrada'], 'fecha_entrada': r['fecha_entrada'],
                'numero_inicial': r['numero_inicial'], 'numero_final': r['numero_final']})
            hechos.append(_("Rúbrica «%s» creada (falta adjuntarle la imagen y la primera hoja).",
                            r['idrubrica']))
        return hechos

    def _aplicar_chequeras(self, company, datos):
        Chequera = self.env['local_py.chequera'].sudo()
        bancos = {b.name: b for b in self.env['res.bank'].sudo().search([])}
        cuentas_bancarias = {b.acc_number: b for b in self.env['res.partner.bank'].sudo().search(
            [('partner_id', '=', company.partner_id.id)])}
        monedas = {m.name: m for m in self.env['res.currency'].sudo().with_context(
            active_test=False).search([])}
        diarios = {d.code: d for d in self.env['account.journal'].sudo().search(
            [('company_id', '=', company.id), ('type', '=', 'bank')])}
        hechos = []
        for c in datos['chequeras']:
            banco = bancos.get(c['banco'])
            cuenta_bancaria = cuentas_bancarias.get(c['cuenta_bancaria'])
            moneda = monedas.get(c['moneda'])
            diario = diarios.get(c['diario'])
            if not (banco and cuenta_bancaria and moneda and diario):
                continue
            if Chequera.search([('name', '=', c['nombre']),
                                ('company_id', '=', company.id)], limit=1):
                continue
            Chequera.create({
                'name': c['nombre'], 'company_id': company.id, 'bank_id': banco.id,
                'cuenta_bancaria_id': cuenta_bancaria.id, 'currency_id': moneda.id,
                'tipo': c['tipo'], 'numero_inicial': c['numero_inicial'],
                'numero_final': c['numero_final'], 'diario_id': diario.id})
            hechos.append(_("Chequera «%s» creada.", c['nombre']))
        return hechos

    def _aplicar_detalle_inventario(self, config, cuentas, datos):
        Detalle = self.env['local_py.libro_inventario.detalle_cuenta'].sudo()
        ya_configuradas = config.libro_inventario_detalle_ids.mapped('account_id').ids
        hechos = []
        for d in datos['detalle_inventario']:
            cuenta = cuentas.get(d['cuenta'])
            if not cuenta or cuenta.id in ya_configuradas:
                continue
            Detalle.create({'config_id': config.id, 'account_id': cuenta.id,
                            'criterio': d['criterio'], 'nivel': d['nivel'],
                            'cantidad_top': d['cantidad']})
            hechos.append(_("Detalle de Libro Inventario para la cuenta %s.", d['cuenta']))
        return hechos

    def _aplicar_renumeracion(self, config, datos):
        Renumeracion = self.env['local_py.configuracion_localizacion.renumeracion'].sudo()
        existentes = config.renumeracion_ids.mapped('anio')
        hechos = []
        for r in datos['renumeracion']:
            if r['anio'] in existentes:
                continue
            Renumeracion.create({'config_id': config.id, 'anio': r['anio'],
                                 'numero_inicial': r['numero_inicial']})
            hechos.append(_("Renumeración de asientos del año %(anio)s desde %(numero)s.",
                            anio=r['anio'], numero=r['numero_inicial']))
        return hechos

    def _aplicar_no_retencion(self, config, datos):
        NoRetencion = self.env['local_py.no_retencion'].sudo()
        hechos = []
        for r in datos['no_retencion']:
            partner = self.env['res.partner'].sudo().search([('vat', '=', r['ruc'])], limit=1)
            if not partner:
                continue
            if NoRetencion.search([
                    ('config_id', '=', config.id), ('partner_id', '=', partner.id),
                    ('tipo_retencion', '=', r['tipo_retencion']),
                    ('nro_resolucion', '=', r['nro_resolucion'])], limit=1):
                continue
            NoRetencion.create({
                'config_id': config.id, 'partner_id': partner.id,
                'tipo_retencion': r['tipo_retencion'], 'nro_resolucion': r['nro_resolucion'],
                'fecha_desde': r['fecha_desde'], 'fecha_hasta': r['fecha_hasta']})
            hechos.append(_("Resolución de No Retención %(nro)s para %(partner)s.",
                            nro=r['nro_resolucion'], partner=partner.display_name))
        return hechos

    def _aplicar_conceptos_inr(self, datos):
        """Los conceptos de Renta No Residente vienen cargados con local_py; la planilla
        solo ajusta sus porcentajes."""
        Concepto = self.env['local_py.concepto_renta_no_residente'].sudo()
        hechos = []
        for c in datos['conceptos_inr']:
            concepto = Concepto.with_context(active_test=False).search(
                [('codigo', '=', c['codigo'])], limit=1)
            if not concepto:
                continue
            vals = {'porcentaje_imputacion': c['porcentaje_imputacion'],
                    'porcentaje': c['porcentaje'],
                    'porcentaje_absorcion': c['porcentaje_absorcion']}
            if any(concepto[campo] != valor for campo, valor in vals.items()):
                concepto.write(vals)
                hechos.append(_("Concepto Renta No Residente %s: porcentajes actualizados.",
                                c['codigo']))
        return hechos
