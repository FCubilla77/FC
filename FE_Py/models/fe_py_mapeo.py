# -*- coding: utf-8 -*-
"""Mapeo de Datos: de dónde saca FE_Py los datos que no son suyos.

FE_Py no depende de ninguna localización. Los datos que SÍ son suyos
—los códigos de SIFEN— los define en sus propios catálogos. Pero hay
cinco datos fiscales que no le pertenecen y que no tiene por qué
duplicar, porque cualquier localización paraguaya ya los administra: el
timbrado del Diario, su rango de numeración, la vigencia del timbrado,
el número del comprobante y la marca de receptor del exterior.

Este modelo es donde el usuario le dice a FE_Py en qué campo están, sea
cual sea el módulo que los provea. Si mañana el cliente cambia de
localización, se reapunta el mapeo y FE_Py sigue funcionando sin tocar
una línea de código.

Dirección: casi todas las necesidades son de LECTURA. La única de
lectura y escritura es el número del comprobante, porque FE_Py se hace
cargo de numerar los Diarios electrónicos (con su propia tabla de
Documentos Anulados) y escribe el resultado en el campo de la
localización — que es el mismo que leen Marangatu y los demás informes.
Así no hay dos números para el mismo comprobante.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Tipos de campo que FE_Py sabe leer.
TIPOS_COMPATIBLES = {
    'char': {'char', 'text', 'integer', 'selection'},
    'integer': {'integer', 'char', 'float'},
    'date': {'date', 'datetime'},
    'boolean': {'boolean'},
}

# Catálogo fijo de necesidades. No es configurable: son exactamente los
# datos que FE_Py necesita y no produce.
#   modelo       : de qué modelo se lee
#   tipo         : tipo lógico esperado (ver TIPOS_COMPATIBLES)
#   escribe      : FE_Py además escribe en este campo
#   obligatoria  : sin este mapeo no se puede emitir
NECESIDADES = {
    'journal_timbrado': {
        'etiqueta': 'Timbrado del Diario',
        'modelo': 'account.journal',
        'tipo': 'integer',
        'escribe': False,
        'obligatoria': True,
        'ayuda': 'Número de timbrado autorizado por la DNIT. Se informa como dNumTim.',
    },
    'journal_nro_documento': {
        'etiqueta': 'Nro. Documento inicial del Diario',
        'modelo': 'account.journal',
        'tipo': 'char',
        'escribe': False,
        'obligatoria': True,
        'ayuda': 'Primer número del rango autorizado, en formato 001-001-0000001. '
                 'De acá salen el Establecimiento y el Punto de Expedición.',
    },
    'journal_nro_documento_final': {
        'etiqueta': 'Nro. Documento final del Diario',
        'modelo': 'account.journal',
        'tipo': 'char',
        'escribe': False,
        'obligatoria': False,
        'ayuda': 'Último número del rango autorizado. Si se mapea, FE_Py avisa '
                 'cuando la numeración se pasa del rango.',
    },
    'journal_inicio_vigencia': {
        'etiqueta': 'Inicio de vigencia del Timbrado',
        'modelo': 'account.journal',
        'tipo': 'date',
        'escribe': False,
        'obligatoria': True,
        'ayuda': 'Fecha desde la que rige el timbrado. Se informa como dFeIniT.',
    },
    'move_nro_documento': {
        'etiqueta': 'Nro. Documento del Comprobante',
        'modelo': 'account.move',
        'tipo': 'char',
        'escribe': True,
        'obligatoria': True,
        'ayuda': 'Número asignado al comprobante, en formato 001-001-0000001.\n\n'
                 'Único mapeo de escritura: en los Diarios electrónicos FE_Py '
                 'calcula el siguiente número —salteando su propia tabla de '
                 'Documentos Anulados— y lo escribe acá, para que los informes '
                 'de la localización sigan leyendo el mismo valor.',
    },
    'partner_es_exterior': {
        'etiqueta': 'Posición Fiscal del Exterior',
        'modelo': 'account.fiscal.position',
        'tipo': 'boolean',
        'escribe': False,
        'obligatoria': False,
        'ayuda': 'Marca de la Posición Fiscal que identifica a un receptor del '
                 'exterior. Si no se mapea, FE_Py considera del exterior al '
                 'Contacto cuyo País no sea Paraguay.',
    },
}

# Nombres que FE_Py prueba al cargar el mapeo sugerido. Se buscan en orden
# y se toma el primero que exista: así el botón sirve con local_py y con
# cualquier módulo que use nombres parecidos, sin que FE_Py dependa de
# ninguno — si no encuentra nada, deja la fila vacía y no falla.
SUGERIDOS = {
    'journal_timbrado': ('local_py_timbrado', 'l10n_py_timbrado', 'timbrado'),
    'journal_nro_documento': ('local_py_nro_documento', 'l10n_py_nro_documento',
                              'nro_documento'),
    'journal_nro_documento_final': ('local_py_nro_documento_final',
                                    'nro_documento_final'),
    'journal_inicio_vigencia': ('local_py_inicio_vigencia_timbrado',
                                'l10n_py_inicio_vigencia_timbrado',
                                'inicio_vigencia_timbrado'),
    'move_nro_documento': ('local_py_nro_documento', 'l10n_py_nro_documento',
                           'nro_documento'),
    'partner_es_exterior': ('local_py_es_exterior', 'es_exterior'),
}


class FePyMapeo(models.Model):
    _name = 'fe_py.mapeo'
    _inherit = ['fe_py.mixin.licencia', 'fe_py.mixin.licencia.edicion']
    _description = 'FEPy Mapeo de Datos'
    _order = 'modelo_origen, necesidad'
    _rec_name = 'necesidad'

    necesidad = fields.Selection(
        selection=[(k, v['etiqueta']) for k, v in NECESIDADES.items()],
        string='Dato que FE_Py necesita', required=True, index=True,
    )
    campo_id = fields.Many2one(
        'ir.model.fields', string='Campo donde está el dato',
        ondelete='cascade', domain="[('id', 'in', campo_posible_ids)]",
        help='Campo del que FE_Py va a leer (y, en el número del '
             'comprobante, también escribir). Puede ser de cualquier '
             'módulo: nativo de Odoo, de una localización o propio.',
    )
    campo_posible_ids = fields.Many2many(
        'ir.model.fields', string='Campos compatibles',
        compute='_compute_campo_posible_ids',
    )
    modelo_origen = fields.Char(
        string='Modelo', compute='_compute_descriptivos', store=True)
    escribe = fields.Boolean(
        string='FE_Py también escribe', compute='_compute_descriptivos', store=True)
    obligatoria = fields.Boolean(
        string='Obligatorio', compute='_compute_descriptivos', store=True)
    ayuda = fields.Text(string='Para qué se usa', compute='_compute_descriptivos')
    tipo_campo = fields.Selection(related='campo_id.ttype', string='Tipo del campo')
    active = fields.Boolean(string='Activo', default=True)

    _necesidad_uniq = models.Constraint(
        'unique(necesidad)',
        'Ya existe un mapeo para ese dato. Cada dato se mapea una sola vez.',
    )

    # ------------------------------------------------------------------
    # Descriptivos
    # ------------------------------------------------------------------
    @api.depends('necesidad')
    def _compute_descriptivos(self):
        for mapeo in self:
            spec = NECESIDADES.get(mapeo.necesidad) or {}
            mapeo.modelo_origen = spec.get('modelo') or False
            mapeo.escribe = spec.get('escribe', False)
            mapeo.obligatoria = spec.get('obligatoria', False)
            mapeo.ayuda = spec.get('ayuda') or False

    @api.depends('necesidad')
    def _compute_campo_posible_ids(self):
        Campo = self.env['ir.model.fields']
        for mapeo in self:
            spec = NECESIDADES.get(mapeo.necesidad)
            if not spec:
                mapeo.campo_posible_ids = Campo
                continue
            dominio = [
                ('model', '=', spec['modelo']),
                ('ttype', 'in', list(TIPOS_COMPATIBLES[spec['tipo']])),
                ('store', '=', True),
            ]
            mapeo.campo_posible_ids = Campo.search(dominio)

    @api.onchange('necesidad')
    def _onchange_necesidad(self):
        """Al cambiar el dato, el campo elegido deja de tener sentido."""
        if self.campo_id and self.campo_id.model != (
                NECESIDADES.get(self.necesidad) or {}).get('modelo'):
            self.campo_id = False

    # ------------------------------------------------------------------
    # Validaciones
    # ------------------------------------------------------------------
    @api.constrains('necesidad', 'campo_id')
    def _check_fe_py_campo(self):
        for mapeo in self:
            if not mapeo.campo_id:
                continue
            spec = NECESIDADES.get(mapeo.necesidad)
            if not spec:
                continue
            campo = mapeo.campo_id
            if campo.model != spec['modelo']:
                raise ValidationError(_(
                    'El dato "%(dato)s" se lee de %(modelo)s, pero el campo '
                    'elegido pertenece a %(otro)s.',
                    dato=spec['etiqueta'], modelo=spec['modelo'], otro=campo.model))
            if campo.ttype not in TIPOS_COMPATIBLES[spec['tipo']]:
                raise ValidationError(_(
                    'El campo "%(campo)s" es de tipo %(tipo)s y no sirve para '
                    '"%(dato)s", que necesita un valor de tipo %(esperado)s.',
                    campo=campo.field_description, tipo=campo.ttype,
                    dato=spec['etiqueta'], esperado=spec['tipo']))
            if not campo.store:
                raise ValidationError(_(
                    'El campo "%(campo)s" no se almacena en la base de datos, '
                    'así que no se puede usar en el mapeo.',
                    campo=campo.field_description))
            if spec['escribe'] and campo.readonly:
                raise ValidationError(_(
                    'FE_Py tiene que poder ESCRIBIR en "%(campo)s" para '
                    'asignar el número del comprobante, y ese campo es de '
                    'solo lectura.', campo=campo.field_description))

    # ------------------------------------------------------------------
    # API que usa el resto del módulo
    # ------------------------------------------------------------------
    @api.model
    def _mapa(self):
        """{necesidad: nombre_de_campo} con los mapeos cargados.

        Se arma de una sola consulta: quien necesite varios datos del mismo
        documento lo pide una vez y los resuelve todos contra el dict.
        """
        return {
            m.necesidad: m.campo_id.name
            for m in self.sudo().search([('campo_id', '!=', False)])
        }

    @api.model
    def _leer(self, registro, necesidad, mapa=None):
        """Valor de `necesidad` leído de `registro`, o False si no hay
        mapeo, no hay registro o el campo ya no existe en el modelo."""
        if not registro:
            return False
        campo = (mapa if mapa is not None else self._mapa()).get(necesidad)
        if not campo or campo not in registro._fields:
            return False
        return registro[campo]

    @api.model
    def _escribir(self, registro, necesidad, valor):
        """Escribe `valor` en el campo mapeado. Devuelve True si escribió."""
        spec = NECESIDADES.get(necesidad) or {}
        if not spec.get('escribe'):
            raise UserError(_(
                'El dato "%s" es de solo lectura: FE_Py no escribe ahí.',
                spec.get('etiqueta') or necesidad))
        campo = self._mapa().get(necesidad)
        if not campo or not registro or campo not in registro._fields:
            return False
        registro[campo] = valor
        return True

    @api.model
    def _faltantes(self):
        """Necesidades obligatorias todavía sin mapear, por su etiqueta."""
        mapa = self._mapa()
        return [spec['etiqueta'] for clave, spec in NECESIDADES.items()
                if spec['obligatoria'] and not mapa.get(clave)]

    # ------------------------------------------------------------------
    # Carga inicial
    # ------------------------------------------------------------------
    @api.model
    def _crear_filas_faltantes(self):
        """Deja una fila por necesidad, vacía si no se puede sugerir nada.
        Así el usuario ve la lista completa de lo que FE_Py necesita."""
        existentes = set(self.search([]).mapped('necesidad'))
        nuevas = [{'necesidad': clave} for clave in NECESIDADES
                  if clave not in existentes]
        if nuevas:
            self.create(nuevas)
        return len(nuevas)

    def action_fe_py_cargar_sugeridos(self):
        """Completa los mapeos vacíos buscando campos con nombres conocidos.

        No falla ni avisa si no encuentra: deja la fila vacía para que el
        usuario la complete a mano. FE_Py no sabe ni le importa de qué
        módulo viene el campo que encuentra.
        """
        self._crear_filas_faltantes()
        Campo = self.env['ir.model.fields']
        completados = 0
        for mapeo in self.search([('campo_id', '=', False)]):
            spec = NECESIDADES.get(mapeo.necesidad)
            if not spec:
                continue
            for nombre in SUGERIDOS.get(mapeo.necesidad, ()):
                campo = Campo.search([
                    ('model', '=', spec['modelo']),
                    ('name', '=', nombre),
                    ('ttype', 'in', list(TIPOS_COMPATIBLES[spec['tipo']])),
                    ('store', '=', True),
                ], limit=1)
                if campo:
                    mapeo.campo_id = campo
                    completados += 1
                    break
        faltan = self._faltantes()
        if faltan:
            mensaje = _(
                'Se completaron %(n)s mapeos. Todavía faltan, y sin ellos no '
                'se puede emitir: %(faltan)s.',
                n=completados, faltan=', '.join(faltan))
        else:
            mensaje = _('Se completaron %s mapeos. No falta ninguno obligatorio.',
                        completados)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Mapeo de Datos'),
                'message': mensaje,
                'type': 'warning' if faltan else 'success',
                'sticky': bool(faltan),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
