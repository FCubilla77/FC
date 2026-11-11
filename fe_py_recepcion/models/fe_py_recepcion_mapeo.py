# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from . import utilidades

DESTINOS = [
    ('cabecera', 'Cabecera de la factura'),
    ('linea', 'Línea de la factura'),
    ('proveedor', 'Contacto (proveedor nuevo)'),
]
MODELO_DESTINO = {
    'cabecera': 'account.move',
    'linea': 'account.move.line',
    'proveedor': 'res.partner',
}
MODELO_ORIGEN = {
    'cabecera': 'fe_py_recepcion.documento',
    'linea': 'fe_py_recepcion.documento.linea',
    'proveedor': 'fe_py_recepcion.documento',
}

# Mapeo sugerido para local_py (>= 2026.19.017). Cada fila:
# (destino, tipo_documento, campo de la recepción o None, valor fijo o None, campo destino)
SUGERIDO_LOCAL_PY = [
    ('cabecera', 'todos', 'cdc', None, 'l10n_py_cdc'),
    ('cabecera', 'todos', 'cdc_asociado', None, 'l10n_py_cdc_asociado'),
    ('cabecera', 'todos', 'timbrado', None, 'l10n_py_timbrado'),
    ('cabecera', 'todos', 'nro_documento', None, 'l10n_py_nro_documento'),
    ('cabecera', '1', None, 'local_py.tipo_fiscal_factura_electronica', 'local_py_tipo_fiscal_id'),
    ('cabecera', '5', None, 'local_py.tipo_fiscal_nota_credito', 'local_py_tipo_fiscal_id'),
    ('cabecera', '6', None, 'local_py.tipo_fiscal_nota_debito', 'local_py_tipo_fiscal_id'),
    ('proveedor', 'todos', None, 'local_py.tipo_identificacion_ruc',
     'l10n_py_tipo_identificacion_fiscal_id'),
]


class FePyRecepcionMapeo(models.Model):
    """Qué dato leído del XML se copia a qué campo de la factura, de su línea o del proveedor.

    El módulo guarda siempre todo lo que lee en sus propios modelos. Este mapeo es opcional:
    solo si está configurado y activado en Ajustes, al generar la factura se copian los datos
    a los campos indicados (por ejemplo, los de una localización o un módulo de terceros).
    Sin mapeo, la factura se genera con los datos estándar de Odoo."""
    _name = 'fe_py_recepcion.mapeo'
    _description = 'Mapeo de campos de la recepción'
    _order = 'company_id, destino, sequence, id'

    company_id = fields.Many2one('res.company', string='Compañía', required=True, index=True,
                                 default=lambda self: self.env.company)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    destino = fields.Selection(DESTINOS, string='Se copia a', required=True, default='cabecera')
    tipo_documento = fields.Selection(
        [('todos', 'Todos'), ('1', 'Factura'), ('5', 'Nota de crédito'), ('6', 'Nota de débito')],
        string='Tipo de documento', required=True, default='todos',
        help='Tipo de documento del XML al que se aplica. Un mapeo específico se aplica después '
             'de los de «Todos» y los reemplaza para ese campo.')
    origen = fields.Selection(
        [('campo', 'Campo leído del XML'), ('fijo', 'Valor fijo')],
        string='Origen del dato', required=True, default='campo')
    campo_origen_id = fields.Many2one(
        'ir.model.fields', string='Campo de la recepción', ondelete='cascade',
        help='Campo del modelo de recepción donde quedó guardado el dato leído del XML.')
    valor_fijo = fields.Char(
        string='Valor fijo',
        help='Valor que se copia siempre. Para un campo relacional, el identificador externo '
             '(por ejemplo, modulo.nombre) o el nombre exacto del registro.')
    campo_destino_id = fields.Many2one(
        'ir.model.fields', string='Campo de destino', required=True, ondelete='cascade')
    modelo_origen = fields.Char(compute='_compute_modelos')
    modelo_destino = fields.Char(compute='_compute_modelos')
    descripcion = fields.Char(string='Mapeo', compute='_compute_descripcion')

    _unico = models.Constraint(
        'unique(company_id, destino, tipo_documento, campo_destino_id)',
        'Ese campo de destino ya está mapeado para ese tipo de documento.')

    @api.depends('destino')
    def _compute_modelos(self):
        for mapeo in self:
            mapeo.modelo_origen = MODELO_ORIGEN.get(mapeo.destino, False)
            mapeo.modelo_destino = MODELO_DESTINO.get(mapeo.destino, False)

    @api.depends('origen', 'campo_origen_id', 'valor_fijo', 'campo_destino_id')
    def _compute_descripcion(self):
        for mapeo in self:
            if mapeo.origen == 'fijo':
                desde = '"%s"' % (mapeo.valor_fijo or '')
            else:
                desde = mapeo.campo_origen_id.field_description or ''
            mapeo.descripcion = '%s → %s' % (desde, mapeo.campo_destino_id.field_description or '')

    @api.onchange('destino')
    def _onchange_destino(self):
        self.campo_origen_id = False
        self.campo_destino_id = False

    @api.onchange('origen')
    def _onchange_origen(self):
        if self.origen == 'fijo':
            self.campo_origen_id = False
        else:
            self.valor_fijo = False

    @api.constrains('destino', 'origen', 'campo_origen_id', 'valor_fijo', 'campo_destino_id')
    def _check_mapeo(self):
        for mapeo in self:
            destino = mapeo.campo_destino_id
            if destino.model != MODELO_DESTINO[mapeo.destino]:
                raise ValidationError(_(
                    'El campo de destino debe ser un campo de «%s».', MODELO_DESTINO[mapeo.destino]))
            if destino.name in utilidades.CAMPOS_RESERVADOS.get(destino.model, ()):
                raise ValidationError(_(
                    'El campo «%s» lo completa siempre el módulo y no se puede mapear.',
                    destino.field_description))
            if destino.ttype not in utilidades.TIPOS_DESTINO or not destino.store:
                raise ValidationError(_(
                    'El campo «%s» no se puede usar como destino (tipo %s).',
                    destino.field_description, destino.ttype))
            if mapeo.origen == 'fijo':
                if not (mapeo.valor_fijo or '').strip():
                    raise ValidationError(_('Indique el valor fijo.'))
                tipo_origen = 'char'
            else:
                origen = mapeo.campo_origen_id
                if not origen:
                    raise ValidationError(_('Elija el campo de la recepción.'))
                if origen.model != MODELO_ORIGEN[mapeo.destino]:
                    raise ValidationError(_(
                        'El campo de origen debe ser un campo de «%s».', MODELO_ORIGEN[mapeo.destino]))
                tipo_origen = origen.ttype
                if tipo_origen not in utilidades.TIPOS_ORIGEN:
                    raise ValidationError(_(
                        'El campo «%s» no se puede usar como origen (tipo %s).',
                        origen.field_description, origen.ttype))
            if not utilidades.tipos_compatibles(tipo_origen, destino.ttype):
                raise ValidationError(_(
                    'Un dato de tipo «%(origen)s» no se puede copiar a «%(campo)s» (tipo %(destino)s).',
                    origen=tipo_origen, campo=destino.field_description, destino=destino.ttype))

    # ------------------------------------------------------------------
    # Aplicación
    # ------------------------------------------------------------------
    @api.model
    def _mapeos_de(self, company, destino, itide):
        mapeos = self.sudo().search([('company_id', '=', company.id), ('destino', '=', destino),
                              ('tipo_documento', 'in', ['todos', str(itide or '')])])
        return mapeos.sorted(lambda m: (m.tipo_documento != 'todos', m.sequence, m.id))

    @api.model
    def valores(self, company, destino, itide, origen):
        """(vals, avisos): lo que hay que copiar desde el registro `origen` (recepción o línea)
        al destino. Un dato vacío no se copia, para no pisar lo que Odoo ya completó."""
        vals, avisos = {}, []
        for mapeo in self._mapeos_de(company, destino, itide):
            campo = mapeo.campo_destino_id
            try:
                valor, tipo_origen = mapeo._valor_de(origen)
                ok, convertido = self._convertir(campo, valor, tipo_origen)
            except Exception as error:  # un mapeo mal armado no debe frenar la factura
                ok, convertido = False, None
                avisos.append(_('Mapeo «%(mapeo)s»: %(error)s', mapeo=mapeo.descripcion, error=error))
                continue
            if ok:
                vals[campo.name] = convertido
            elif valor not in (None, False, ''):
                avisos.append(_(
                    'Mapeo «%(mapeo)s»: no se pudo copiar el valor «%(valor)s».',
                    mapeo=mapeo.descripcion, valor=valor))
        return vals, avisos

    def _valor_de(self, origen):
        self.ensure_one()
        if self.origen == 'fijo':
            return (self.valor_fijo or '').strip(), 'char'
        return origen[self.campo_origen_id.name], self.campo_origen_id.ttype

    def _convertir(self, campo, valor, tipo_origen):
        """(ok, valor) listo para escribir en el campo destino."""
        if campo.ttype == 'many2one':
            return self._resolver_relacion(campo, valor)
        if campo.ttype == 'selection':
            return self._resolver_seleccion(campo, valor)
        return utilidades.convertir_valor(valor, campo.ttype)

    def _resolver_relacion(self, campo, valor):
        Comodelo = self.env[campo.relation]
        if isinstance(valor, models.BaseModel):
            if not valor:
                return False, None
            if valor._name == campo.relation:
                return True, valor.id
            valor = valor.display_name
        texto = str(valor or '').strip()
        if not texto:
            return False, None
        if '.' in texto and ' ' not in texto:
            registro = self.env.ref(texto, raise_if_not_found=False)
            if registro and registro._name == campo.relation:
                return True, registro.id
        nombre = Comodelo._rec_name or 'name'
        if nombre not in Comodelo._fields:
            return False, None
        registros = Comodelo.search([(nombre, '=', texto)], limit=2)
        if len(registros) == 1:
            return True, registros.id
        return False, None

    def _resolver_seleccion(self, campo, valor):
        texto = str(valor or '').strip()
        if not texto:
            return False, None
        modelo = self.env[campo.model]
        opciones = modelo._fields[campo.name]._description_selection(self.env)
        for clave, etiqueta in opciones:
            if texto.lower() in (str(clave).lower(), str(etiqueta).lower()):
                return True, clave
        return False, None

    # ------------------------------------------------------------------
    # Mapeo sugerido para local_py
    # ------------------------------------------------------------------
    def cargar_sugerido_local_py(self):
        """Carga el mapeo sugerido para local_py (CDC, timbrado, número, tipo fiscal y tipo de
        identificación del proveedor) en la compañía actual. No pisa ni duplica lo ya cargado y
        omite lo que local_py (o la versión instalada) no tenga."""
        Campos = self.env['ir.model.fields'].sudo()
        company = self.env.company
        creados, omitidos = 0, 0
        for destino, tipo_doc, campo_origen, fijo, campo_destino in SUGERIDO_LOCAL_PY:
            f_destino = Campos.search([('model', '=', MODELO_DESTINO[destino]),
                                       ('name', '=', campo_destino)], limit=1)
            f_origen = Campos.search([('model', '=', MODELO_ORIGEN[destino]),
                                      ('name', '=', campo_origen)], limit=1) if campo_origen \
                else Campos.browse()
            if not f_destino or (campo_origen and not f_origen) or \
                    (fijo and not self.env.ref(fijo, raise_if_not_found=False)):
                omitidos += 1
                continue
            if self.with_context(active_test=False).search_count([
                    ('company_id', '=', company.id), ('destino', '=', destino),
                    ('tipo_documento', '=', tipo_doc), ('campo_destino_id', '=', f_destino.id)]):
                continue
            self.create({
                'company_id': company.id, 'destino': destino, 'tipo_documento': tipo_doc,
                'origen': 'campo' if campo_origen else 'fijo',
                'campo_origen_id': f_origen.id or False, 'valor_fijo': fijo or False,
                'campo_destino_id': f_destino.id,
            })
            creados += 1
        if omitidos and not creados:
            mensaje = _('No se encontraron los campos de local_py (se requiere 2026.19.017 o '
                        'posterior instalado).')
            tipo = 'warning'
        else:
            mensaje = _('Mapeo sugerido cargado: %(creados)s fila(s) nueva(s)%(omitidos)s.',
                        creados=creados,
                        omitidos=_(', %s omitida(s) por no existir el campo en local_py', omitidos)
                        % omitidos if omitidos else '')
            tipo = 'success'
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'title': _('Mapeo de campos'), 'message': mensaje, 'type': tipo,
                       'sticky': False, 'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'}},
        }
