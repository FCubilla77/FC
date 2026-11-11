# -*- coding: utf-8 -*-
import base64
import logging
from decimal import Decimal

from markupsafe import Markup, escape

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from . import utilidades, xml_parser
from .fe_py_recepcion_licencia import fe_py_recepcion_licencia_verificar
from .xml_parser import XmlRecepcionError, XmlTipoNoSoportado

_logger = logging.getLogger(__name__)

# Origen del producto de una línea que lo sugirió el sistema y que ninguna persona confirmó.
PRODUCTO_ORIGEN_SUGERIDO = ('gtin', 'referencia', 'descripcion')


class _DescartarSimulacion(Exception):
    """Fuerza el rollback del savepoint de la simulación."""


class RecepcionNA(UserError):
    """El archivo se leyó bien pero no corresponde cargarlo (por ejemplo, un tipo de documento
    que no se recibe). Queda como registro N/A, no como error."""


class FePyRecepcionDocumento(models.Model):
    """Factura electrónica recibida de un proveedor (cabecera).

    SOLO LECTURA del XML: se guardan los datos que el proveedor informó, CDC
    incluido. No se genera ni valida CDC, firma ni esquema, y no se consulta
    a SIFEN.
    """
    _name = 'fe_py_recepcion.documento'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'fe_py_recepcion.mixin.licencia',
                'fe_py_recepcion.mixin.licencia.edicion']
    _description = 'Factura Electrónica Recibida'
    _order = 'fecha_emision desc, id desc'

    name = fields.Char(string='Documento', compute='_compute_name', store=True)
    state = fields.Selection(
        [('cargado', 'Cargado'), ('verificado', 'Verificado'), ('borrador', 'Borrador'),
         ('confirmado', 'Confirmado'), ('cancelado', 'Cancelado'), ('error', 'Error'),
         ('na', 'N/A')],
        string='Estado', default='cargado', required=True, copy=False, tracking=True, index=True,
        help='Cargado: se leyó el XML, todavía no hay factura. Verificado: totales controlados, '
             'todavía no hay factura. Borrador: la factura, nota de crédito o nota de débito de '
             'proveedor está generada pero sin publicar. Confirmado: la factura está publicada. '
             'N/A: el correo o el archivo no corresponde cargarlo (sin XML, tipo no soportado o '
             'duplicado). Error: el archivo no se pudo leer.')
    company_id = fields.Many2one('res.company', string='Compañía', required=True, index=True,
                                 default=lambda self: self.env.company, readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)

    # -- Datos del XML (solo lectura) ----------------------------------------
    cdc = fields.Char(string='CDC', size=44, readonly=True, copy=False, index=True,
                      help='Código de Control del DE, tal como lo informó el proveedor en el XML. '
                           'Es obligatorio salvo en los registros con error.')
    itide = fields.Selection(
        [('1', 'Factura electrónica'), ('5', 'Nota de crédito electrónica'),
         ('6', 'Nota de débito electrónica')],
        string='Tipo de documento', readonly=True)
    move_type = fields.Selection(
        [('in_invoice', 'Factura de proveedor'), ('in_refund', 'Nota de crédito de proveedor')],
        string='Tipo de comprobante', compute='_compute_move_type', store=True)
    timbrado = fields.Char(string='Timbrado', readonly=True)
    nro_documento = fields.Char(string='Nro. Documento', size=15, readonly=True, index=True)
    fecha_emision = fields.Date(string='Fecha de emisión', readonly=True)
    tipo_transaccion = fields.Char(string='Tipo de transacción', readonly=True)
    moneda_codigo = fields.Char(string='Moneda del XML', readonly=True)
    tipo_cambio = fields.Float(string='Tipo de cambio del XML', digits=(16, 4), readonly=True)

    emisor_ruc = fields.Char(string='RUC del proveedor', readonly=True)
    emisor_nombre = fields.Char(string='Razón social del proveedor', readonly=True)
    emisor_fantasia = fields.Char(string='Nombre de fantasía', readonly=True)
    emisor_direccion = fields.Char(string='Dirección', readonly=True)
    emisor_telefono = fields.Char(string='Teléfono', readonly=True)
    emisor_email = fields.Char(string='Correo', readonly=True)
    emisor_ciudad = fields.Char(string='Ciudad', readonly=True)
    receptor_ruc = fields.Char(string='RUC del receptor', readonly=True)
    receptor_nombre = fields.Char(string='Nombre del receptor', readonly=True)

    condicion = fields.Selection([('1', 'Contado'), ('2', 'Crédito')], string='Condición del XML',
                                 readonly=True)
    condicion_detalle = fields.Char(string='Detalle de la condición del XML', readonly=True)
    entrega_inicial = fields.Monetary(string='Entrega inicial', currency_field='currency_id',
                                      readonly=True)

    motivo_desc = fields.Char(string='Motivo de emisión', readonly=True)
    asociado_texto = fields.Char(string='Documento asociado (XML)', readonly=True)
    cdc_asociado = fields.Char(string='CDC del documento asociado', size=44, readonly=True, copy=False,
                               index=True, help='CDC de la factura que afecta la nota, tal como lo informa el XML.')

    # -- Datos adicionales del XML (pestaña "Datos adicionales del XML") ------------------
    # Solo se guardan para consulta; no intervienen en la generación de la factura.
    xml_version = fields.Char(string='Versión del formato', readonly=True)
    emision_xml = fields.Char(string='Fecha y hora de emisión (XML)', readonly=True)
    timbrado_inicio = fields.Date(string='Inicio de vigencia del timbrado', readonly=True)
    emisor_tipo_contribuyente = fields.Selection(
        [('1', 'Persona física'), ('2', 'Persona jurídica')], string='Tipo de contribuyente',
        readonly=True)
    credito_tipo = fields.Selection([('1', 'Plazo'), ('2', 'Cuotas')], string='Tipo de crédito',
                                    readonly=True)
    credito_plazo = fields.Char(string='Plazo del crédito', readonly=True)
    credito_cuotas = fields.Integer(string='Cantidad de cuotas', readonly=True)
    subtotal_exonerado = fields.Monetary(string='Exonerado (XML)', currency_field='currency_id',
                                         readonly=True)
    descuento_total = fields.Monetary(string='Descuento total (XML)', currency_field='currency_id',
                                      readonly=True)
    descuento_global = fields.Monetary(string='Descuento global (XML)', currency_field='currency_id',
                                       readonly=True)
    anticipo = fields.Monetary(string='Anticipo (XML)', currency_field='currency_id', readonly=True)
    redondeo = fields.Monetary(string='Redondeo (XML)', currency_field='currency_id', readonly=True)
    total_gs = fields.Float(string='Total en guaraníes (XML)', digits=(16, 2), readonly=True)
    motivo_codigo = fields.Char(string='Código del motivo de emisión', readonly=True)
    asociado_tipo = fields.Selection(
        [('1', 'Electrónico'), ('2', 'Impreso'), ('3', 'Constancia electrónica')],
        string='Tipo de documento asociado', readonly=True)
    asociado_timbrado = fields.Char(string='Timbrado del asociado', readonly=True)
    asociado_establecimiento = fields.Char(string='Establecimiento del asociado', readonly=True)
    asociado_punto = fields.Char(string='Punto de expedición del asociado', readonly=True)
    asociado_numero = fields.Char(string='Número del asociado', readonly=True)
    asociado_fecha = fields.Date(string='Fecha de emisión del asociado', readonly=True)

    total_general = fields.Monetary(string='Total del XML', currency_field='currency_id', readonly=True)
    total_iva = fields.Monetary(string='IVA del XML', currency_field='currency_id', readonly=True)
    subtotal_10 = fields.Monetary(string='Gravado 10% (XML)', currency_field='currency_id', readonly=True)
    subtotal_5 = fields.Monetary(string='Gravado 5% (XML)', currency_field='currency_id', readonly=True)
    subtotal_exento = fields.Monetary(string='Exento (XML)', currency_field='currency_id', readonly=True)
    total_odoo = fields.Monetary(string='Total calculado por Odoo', currency_field='currency_id',
                                 readonly=True, copy=False)
    iva_odoo = fields.Monetary(string='IVA calculado por Odoo', currency_field='currency_id',
                               readonly=True, copy=False)
    control_hecho = fields.Boolean(copy=False, readonly=True)
    confirmacion_auto_motivo = fields.Text(
        string='Pendiente de revisión', copy=False, readonly=True,
        help='Por qué el proceso automático se detuvo: la recepción quedó en Cargado, o la '
             'factura quedó en borrador sin publicarse, para que el usuario la revise.')
    na_motivo = fields.Text(
        string='Motivo N/A', copy=False, readonly=True,
        help='Por qué este correo o archivo no se cargó como factura (sin XML, tipo de documento '
             'no soportado o CDC duplicado).')
    documento_original_id = fields.Many2one(
        'fe_py_recepcion.documento', string='Registro original', copy=False, readonly=True,
        ondelete='set null', help='Si es un duplicado, el registro que ya tenía ese CDC.')

    error_detalle = fields.Text(
        string='Motivo del error', copy=False, readonly=True,
        help='Por qué no se pudo cargar el archivo. El registro conserva el XML recibido.')
    origen = fields.Selection(
        [('manual', 'Carga manual'), ('correo', 'Correo')], string='Origen', default='manual',
        required=True, readonly=True, copy=False, index=True)
    correo_remitente = fields.Char(string='Remitente del correo', readonly=True, copy=False)
    correo_asunto = fields.Char(string='Asunto del correo', readonly=True, copy=False)
    correo_fecha = fields.Datetime(string='Fecha del correo', readonly=True, copy=False)
    correo_message_id = fields.Char(string='Message-Id del correo', readonly=True, copy=False)

    xml_attachment_id = fields.Many2one('ir.attachment', string='XML original', readonly=True,
                                        copy=False, ondelete='set null')

    # -- Datos que completa el usuario ---------------------------------------
    partner_id = fields.Many2one(
        'res.partner', string='Proveedor', tracking=True, index=True,
        domain="[('is_company', '=', True)]",
        help='Contacto con el mismo RUC que informa el XML.')
    journal_id = fields.Many2one(
        'account.journal', string='Diario', tracking=True,
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id)]",
        help='Diario de compra con el que se genera la factura de proveedor. Se propone el '
             'configurado en Ajustes para este tipo de documento.')
    payment_term_id = fields.Many2one(
        'account.payment.term', string='Término de pago', tracking=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        help='Se propone el término de Odoo más cercano a la condición del XML. '
             'Odoo calcula las cuotas y vencimientos con el término elegido.')
    termino_aviso = fields.Char(string='Aviso del término de pago', readonly=True)
    reversed_move_id = fields.Many2one(
        'account.move', string='Factura asociada', tracking=True,
        domain="[('move_type', '=', 'in_invoice'), ('partner_id', '=', partner_id), "
               "('company_id', '=', company_id)]",
        help='Factura de proveedor a la que afecta la nota de crédito.')

    move_id = fields.Many2one('account.move', string='Factura de proveedor', readonly=True,
                              copy=False, index=True, ondelete='set null')
    move_state = fields.Selection(related='move_id.state', string='Estado de la factura')

    line_ids = fields.One2many('fe_py_recepcion.documento.linea', 'documento_id', string='Líneas',
                               copy=False)
    cuota_ids = fields.One2many('fe_py_recepcion.documento.cuota', 'documento_id',
                                string='Cuotas del XML', copy=False)

    bloqueos = fields.Text(string='Impedimentos', compute='_compute_diagnostico')
    avisos = fields.Text(string='Avisos', compute='_compute_diagnostico')
    hay_bloqueos = fields.Boolean(compute='_compute_diagnostico')
    hay_productos_sugeridos = fields.Boolean(
        compute='_compute_hay_productos_sugeridos',
        help='Hay líneas con un producto sugerido por el sistema que ninguna persona confirmó.')

    _cdc_company_uniq = models.Constraint(
        'unique(cdc, company_id)',
        'Ya existe una recepción con ese CDC en la compañía.',
    )

    # ------------------------------------------------------------------
    # Campos calculados
    # ------------------------------------------------------------------
    @api.depends('nro_documento', 'emisor_nombre', 'correo_asunto')
    def _compute_name(self):
        for doc in self:
            doc.name = ' - '.join(filter(None, [doc.nro_documento, doc.emisor_nombre])) \
                or doc.correo_asunto or _('Nueva')

    @api.constrains('state', 'cdc', 'itide')
    def _check_datos_del_xml(self):
        for doc in self:
            if doc.state not in ('error', 'na') and not (doc.cdc and doc.itide):
                raise ValidationError(_(
                    'Solo los registros con error o N/A pueden quedar sin CDC o sin tipo de documento.'))

    @api.depends('line_ids.producto_id', 'line_ids.producto_origen')
    def _compute_hay_productos_sugeridos(self):
        for doc in self:
            doc.hay_productos_sugeridos = any(
                l.producto_id and l.producto_origen in PRODUCTO_ORIGEN_SUGERIDO for l in doc.line_ids)

    @api.depends('itide')
    def _compute_move_type(self):
        for doc in self:
            doc.move_type = 'in_refund' if doc.itide == '5' else 'in_invoice'

    @api.depends(
        'partner_id', 'partner_id.vat', 'journal_id', 'currency_id', 'company_id', 'emisor_ruc',
        'receptor_ruc', 'total_general', 'total_iva', 'total_odoo', 'iva_odoo', 'control_hecho',
        'reversed_move_id', 'itide', 'payment_term_id', 'termino_aviso',
        'line_ids.producto_id', 'line_ids.cuenta_id', 'line_ids.impuesto_id',
        'line_ids.afectacion', 'line_ids.tasa', 'line_ids.aviso')
    def _compute_diagnostico(self):
        for doc in self:
            bloqueos, avisos = doc._diagnostico()
            doc.bloqueos = '\n'.join('• %s' % b for b in bloqueos)
            doc.avisos = '\n'.join('• %s' % a for a in avisos)
            doc.hay_bloqueos = bool(bloqueos)

    # ------------------------------------------------------------------
    # Carga del XML
    # ------------------------------------------------------------------
    @api.model
    def crear_desde_xml(self, nombre, contenido, company=None, extra_vals=None):
        """Crea una recepción desde el contenido (bytes) de un XML.

        Devuelve (recepción, creada). Si el CDC ya fue recibido no se vuelve a
        crear: devuelve la existente y creada=False. Lanza UserError si el
        archivo no se puede leer.
        """
        company = company or self.env.company
        try:
            datos = xml_parser.parsear(contenido)
        except XmlTipoNoSoportado as error:
            raise RecepcionNA(_('%(archivo)s: %(error)s', archivo=nombre, error=error)) from error
        except XmlRecepcionError as error:
            raise UserError(_('%(archivo)s: %(error)s', archivo=nombre, error=error)) from error

        existente = self.search([('cdc', '=', datos['cdc']), ('company_id', '=', company.id)], limit=1)
        if existente:
            return existente, False

        moneda = self.env['res.currency'].with_context(active_test=False).search(
            [('name', '=', datos['moneda'])], limit=1)
        totales = datos['totales']
        emisor, receptor = datos['emisor'], datos['receptor']
        credito = datos['credito'] or {}
        asociados = datos['asociados']

        vals = {
            'company_id': company.id,
            'currency_id': moneda.id or False,
            'cdc': datos['cdc'],
            'itide': str(datos['itide']),
            'timbrado': datos['timbrado'],
            'nro_documento': datos['nro_documento'],
            'fecha_emision': datos['fecha_emision'],
            'tipo_transaccion': datos['tipo_transaccion'],
            'moneda_codigo': datos['moneda'],
            'tipo_cambio': float(datos['tipo_cambio'] or 0),
            'emisor_ruc': emisor['ruc_dv'],
            'emisor_nombre': emisor['nombre'],
            'emisor_fantasia': emisor['fantasia'],
            'emisor_direccion': emisor['direccion'],
            'emisor_telefono': emisor['telefono'],
            'emisor_email': emisor['email'],
            'emisor_ciudad': emisor['ciudad'],
            'receptor_ruc': receptor['ruc_dv'],
            'receptor_nombre': receptor['nombre'],
            'condicion': str(datos['condicion']),
            'condicion_detalle': self._detalle_condicion(datos),
            'entrega_inicial': float(credito.get('entrega_inicial') or 0),
            'motivo_desc': datos['motivo_desc'],
            'asociado_texto': ', '.join(self._texto_asociado(a) for a in asociados),
            'cdc_asociado': self._cdc_de_asociados(asociados),
            'total_general': float(totales['total_general']),
            'total_iva': float(totales['iva']),
            'subtotal_10': float(totales['sub10']),
            'subtotal_5': float(totales['sub5']),
            'subtotal_exento': float(totales['exento']),
            **self._vals_datos_adicionales(datos),
            'journal_id': company._fe_py_recepcion_diario_por_itide(datos['itide']).id or False,
        }
        redondeo = Decimal(str(moneda.rounding)) if moneda and moneda.rounding else Decimal('1')
        vals['line_ids'] = [Command.create(self._vals_linea_desde_item(item, redondeo))
                            for item in datos['items']]
        vals['cuota_ids'] = [
            Command.create({'numero': n, 'monto': float(c['monto']), 'vencimiento': c['vencimiento']})
            for n, c in enumerate(credito.get('cuotas') or [], start=1)]

        vals.update(extra_vals or {})
        doc = self.create(vals)
        # las asignaciones iniciales no disparan el proceso automático: se ejecuta al final
        carga = doc.with_context(fe_py_recepcion_carga_inicial=True)
        carga._asignar_proveedor()
        carga._asignar_producto_sugerido()
        carga._asignar_termino_pago(datos)
        carga._asignar_asociado(asociados)
        doc._adjuntar_xml(nombre, contenido)
        doc.message_post(body=_('Recepción creada desde el archivo %s.', nombre))
        doc._procesar_automatico()
        return doc, True

    @api.model
    def _vals_linea_desde_item(self, item, redondeo):
        precio, descuento = utilidades.calcular_precio_descuento(
            item['precio'], item['cantidad'], item['total'], item['descuento_pct'] or None, redondeo)
        return {
            'orden': item['orden'],
            'codigo': item['codigo'],
            'descripcion': item['descripcion'],
            'unidad_desc': item['unidad_desc'],
            'cantidad': float(item['cantidad']),
            'precio_xml': float(item['precio']),
            'precio': float(precio),
            'descuento': float(descuento),
            'total_xml': float(item['total']),
            'afectacion': item['afectacion'],
            'tasa': item['tasa'] or 0,
            'iva_xml': float(item['liq_iva']),
            'unidad_codigo': item.get('unidad_codigo') or False,
            'gtin': item.get('gtin') or False,
            'gtin_paquete': item.get('gtin_paquete') or False,
            'lote': item.get('lote') or False,
            'vencimiento_lote': item.get('vencimiento') or False,
            'serie': item.get('serie') or False,
            'info_item': item.get('info_item') or False,
        }

    @api.model
    def _vals_datos_adicionales(self, datos):
        """Valores de la pestaña "Datos adicionales del XML" (cabecera). Solo lectura del XML."""
        totales, emisor = datos['totales'], datos['emisor']
        credito = datos['credito'] or {}
        asociados = datos['asociados']
        # con varios asociados se guarda el detalle del primero (el texto completo está en
        # "Documento asociado (XML)")
        asociado = next((a for a in asociados if a.get('cdc')), asociados[0] if asociados else {})
        tipo_aso = asociado.get('tipo')
        tipo_contribuyente = emisor.get('tipo_contribuyente')
        return {
            'xml_version': datos.get('version') or False,
            'emision_xml': datos.get('fecha_emision_xml') or False,
            'timbrado_inicio': datos.get('timbrado_inicio') or False,
            'emisor_tipo_contribuyente': str(tipo_contribuyente) if tipo_contribuyente in (1, 2) else False,
            'credito_tipo': str(credito['tipo']) if credito.get('tipo') in (1, 2) else False,
            'credito_plazo': credito.get('plazo') or False,
            'credito_cuotas': credito.get('cantidad_cuotas') or 0,
            'subtotal_exonerado': float(totales.get('exonerado') or 0),
            'descuento_total': float(totales.get('descuento') or 0),
            'descuento_global': float(totales.get('descuento_global') or 0),
            'anticipo': float(totales.get('anticipo') or 0),
            'redondeo': float(totales.get('redondeo') or 0),
            'total_gs': float(totales.get('total_gs') or 0),
            'motivo_codigo': str(datos['motivo_codigo']) if datos.get('motivo_codigo') is not None else False,
            'asociado_tipo': str(tipo_aso) if tipo_aso in (1, 2, 3) else False,
            'asociado_timbrado': asociado.get('timbrado') or False,
            'asociado_establecimiento': asociado.get('establecimiento') or False,
            'asociado_punto': asociado.get('punto') or False,
            'asociado_numero': asociado.get('numero') or False,
            'asociado_fecha': asociado.get('fecha') or False,
        }

    @staticmethod
    def _texto_asociado(asociado):
        if asociado.get('cdc'):
            return 'CDC %s' % asociado['cdc']
        partes = [asociado.get('establecimiento'), asociado.get('punto'), asociado.get('numero')]
        return '-'.join(p for p in partes if p) or _('(sin datos)')

    @staticmethod
    def _detalle_condicion(datos):
        if datos['condicion'] != 2:
            return datos.get('condicion_desc') or 'Contado'
        credito = datos['credito'] or {}
        if credito.get('cuotas'):
            return _('Crédito en %s cuotas', len(credito['cuotas']))
        return _('Crédito a plazo %s', credito.get('plazo') or '')

    def _adjuntar_xml(self, nombre, contenido):
        self.ensure_one()
        adjunto = self.env['ir.attachment'].create({
            'name': nombre or ('%s.xml' % self.cdc),
            'raw': contenido,
            'mimetype': 'application/xml',
            'res_model': self._name,
            'res_id': self.id,
        })
        self.xml_attachment_id = adjunto

    # ------------------------------------------------------------------
    # Asignaciones automáticas al cargar
    # ------------------------------------------------------------------
    def _buscar_proveedor(self):
        """Contacto cuyo RUC coincide con el del XML, o vacío si no hay uno solo."""
        self.ensure_one()
        base, dv = xml_parser.normalizar_vat(self.emisor_ruc)
        Partner = self.env['res.partner']
        if not base:
            return Partner
        coincidentes = Partner
        for partner in Partner.search([('vat', 'ilike', base)], limit=200):
            p_base, p_dv = xml_parser.normalizar_vat(partner.vat)
            if p_base == base and (not dv or not p_dv or dv == p_dv):
                coincidentes |= partner
        comerciales = coincidentes.mapped('commercial_partner_id')
        return comerciales if len(comerciales) == 1 else Partner

    def _asignar_proveedor(self):
        for doc in self:
            doc.partner_id = doc._buscar_proveedor()

    def _asignar_producto_sugerido(self):
        """Sugiere el producto de cada línea sin producto.

        1) Equivalencia ya confirmada con ese proveedor (la usada más recientemente).
        2) Si no hay equivalencia (por ejemplo, la primera vez), el GTIN del ítem contra el
           código de barras del producto o de sus unidades/paquetes.
        3) Coincidencia exacta del código del XML con la referencia de la ficha del producto
           o, si no, de la descripción con el nombre. Estas búsquedas no necesitan al proveedor.
        Solo se sugiere cuando hay un único candidato. Se pueden recalcular las líneas
        con producto sugerido por el sistema (por ejemplo, al cambiar el proveedor); nunca
        se pisa un producto elegido a mano.
        """
        Equivalencia = self.env['fe_py_recepcion.equivalencia']
        for doc in self:
            for linea in doc.line_ids.filtered(
                    lambda l: not l.producto_id or l.producto_origen in ('equivalencia', 'gtin', 'referencia', 'descripcion')):
                producto, origen = self.env['product.product'], False
                if doc.partner_id:
                    producto = Equivalencia.buscar_producto(
                        doc.partner_id, linea.codigo, linea.descripcion, doc.company_id)
                    origen = 'equivalencia' if producto else False
                if not producto:
                    producto = doc._buscar_producto_por_gtin(linea.gtin, linea.gtin_paquete)
                    origen = 'gtin' if producto else False
                if not producto:
                    producto, origen = doc._buscar_producto_en_ficha(linea.codigo, linea.descripcion)
                if producto:
                    if producto != linea.producto_id or origen != linea.producto_origen:
                        linea.write({'producto_id': producto.id, 'producto_origen': origen})
                elif linea.producto_origen == 'equivalencia':
                    # la equivalencia era de otro proveedor: ya no corresponde
                    linea.write({'producto_id': False, 'producto_origen': False})

    def write(self, vals):
        res = super().write(vals)
        if 'partner_id' in vals and not self.env.context.get('fe_py_recepcion_carga_inicial'):
            cargados = self.filtered(lambda d: d.state == 'cargado')
            cargados._asignar_producto_sugerido()
            cargados._asignar_asociado()
            if vals.get('partner_id'):
                # asignar el proveedor a un XML que quedó en Cargado vuelve a ejecutar el proceso
                for doc in cargados:
                    doc._procesar_automatico()
        return res

    def _buscar_producto_por_gtin(self, gtin, gtin_paquete):
        """Producto cuyo código de barras coincide con el GTIN del ítem (o el de su paquete).

        Se compara con el código de barras del producto y con el de sus unidades de medida
        (en Odoo 19 los paquetes son `product.uom`). Solo se sugiere cuando todas las
        coincidencias son del mismo producto; vacío si no hay ninguna o hay dudas."""
        self.ensure_one()
        Producto = self.env['product.product']
        codigos = list({c.strip() for c in (gtin, gtin_paquete) if c and c.strip()})
        if not codigos:
            return Producto
        base = [('purchase_ok', '=', True), '|', ('company_id', '=', False),
                ('company_id', '=', self.company_id.id)]
        productos = Producto.search(base + [('barcode', 'in', codigos)])
        if 'product.uom' in self.env:
            unidades = self.env['product.uom'].sudo().search([('barcode', 'in', codigos)])
            productos |= Producto.search(base + [('id', 'in', unidades.product_id.ids)])
        return productos if len(productos) == 1 else Producto

    def _buscar_producto_en_ficha(self, codigo, descripcion):
        """(producto, origen) por coincidencia exacta (sin distinguir mayúsculas ni espacios
        sobrantes) del código con la referencia del producto o de la descripción con su
        nombre. Productos activos y que se pueden comprar. Vacío si no hay un único candidato."""
        self.ensure_one()
        Producto = self.env['product.product']
        base = [('purchase_ok', '=', True), '|', ('company_id', '=', False),
                ('company_id', '=', self.company_id.id)]
        codigo_n = utilidades.normalizar_clave(codigo)
        if codigo_n:
            candidatos = Producto.search(base + [('default_code', 'ilike', codigo.strip())], limit=50)
            exactos = candidatos.filtered(
                lambda p: utilidades.normalizar_clave(p.default_code) == codigo_n)
            if len(exactos) == 1:
                return exactos, 'referencia'
        descripcion_n = utilidades.normalizar_clave(descripcion)
        if descripcion_n:
            candidatos = Producto.search(base + [('name', 'ilike', descripcion.strip())], limit=50)
            exactos = candidatos.filtered(lambda p: utilidades.normalizar_clave(p.name) == descripcion_n)
            if len(exactos) == 1:
                return exactos, 'descripcion'
        return Producto, False

    def _terminos_de_pago(self):
        """[(id, [días de cada línea])] de los términos de pago de la compañía."""
        terminos = self.env['account.payment.term'].search(
            ['|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)])
        resultado = []
        for termino in terminos:
            dias = [getattr(linea, 'nb_days', 0) or 0 for linea in termino.line_ids]
            resultado.append((termino.id, dias or [0]))
        return resultado

    def _asignar_termino_pago(self, datos):
        """Propone el término de pago de Odoo más cercano a la condición del XML."""
        self.ensure_one()
        credito = datos['credito'] or {}
        cuotas = credito.get('cuotas') or []
        perfil = utilidades.perfil_xml(
            datos['condicion'], credito.get('plazo'), cuotas, datos['fecha_emision'])
        terminos = self._terminos_de_pago()
        elegido = utilidades.elegir_termino(perfil, terminos)
        texto_xml = utilidades.describir_perfil(perfil)
        if not elegido:
            self.termino_aviso = _(
                'El XML informa %s y no hay un término de pago de Odoo equivalente; elija uno.', texto_xml)
            return
        self.payment_term_id = elegido
        dias = dict(terminos)[elegido]
        if dias != perfil:
            self.termino_aviso = _(
                'El XML informa %(xml)s; se propuso "%(termino)s" (%(odoo)s), que no es exacto. '
                'Revíselo.', xml=texto_xml, termino=self.payment_term_id.name,
                odoo=utilidades.describir_perfil(dias))

    def _asignar_asociado(self, asociados=None):
        """Busca la factura que afecta una nota de crédito (mismo proveedor siempre).

        1) CDC del documento asociado contra el CDC de la factura de proveedor.
        2) Si no hay coincidencia, se desglosa el CDC (o los datos sueltos del XML) en
           establecimiento-punto-número y se busca por el número de documento.
        """
        for doc in self:
            if doc.itide != '5' or doc.reversed_move_id or not doc.partner_id:
                continue
            encontrada = doc._buscar_factura_asociada(asociados)
            if encontrada:
                doc.reversed_move_id = encontrada

    def _buscar_factura_asociada(self, asociados=None):
        self.ensure_one()
        Move = self.env['account.move']
        comercial = self.partner_id.commercial_partner_id
        base = [('move_type', '=', 'in_invoice'), ('company_id', '=', self.company_id.id),
                ('state', '!=', 'cancel'), ('commercial_partner_id', '=', comercial.id)]
        if self.cdc_asociado:
            encontrada = Move.search(
                base + [('id', 'in', self._moves_por_dato('cdc', self.cdc_asociado, base).ids)],
                limit=1)
            if encontrada:
                return encontrada
        candidatos = list(asociados or [])
        if not candidatos and self.cdc_asociado:
            candidatos = [{'cdc': self.cdc_asociado}]
        for asociado in candidatos:
            partes = self._partes_asociado(asociado)
            if not partes:
                continue
            numero = '%s-%s-%s' % partes
            recepcion = self.search([
                ('company_id', '=', self.company_id.id), ('itide', '=', '1'),
                ('partner_id.commercial_partner_id', '=', comercial.id),
                ('nro_documento', '=', numero), ('move_id', '!=', False),
                ('move_id.state', '!=', 'cancel')], limit=1)
            encontrada = recepcion.move_id or Move.search(
                base + [('id', 'in', self._moves_por_dato('nro_documento', numero, base).ids)],
                limit=1)
            if encontrada:
                return encontrada
        return Move

    def _campo_mapeado(self, campo_recepcion):
        """Campo de account.move donde el mapeo (si está activo) copia un dato de la recepción,
        o False. Permite reconocer también comprobantes que no vinieron de una recepción."""
        self.ensure_one()
        if not self.company_id._fe_py_recepcion_mapeo_activo():
            return False
        mapeo = self.env['fe_py_recepcion.mapeo'].sudo().search([
            ('company_id', '=', self.company_id.id), ('destino', '=', 'cabecera'),
            ('origen', '=', 'campo'), ('campo_origen_id.name', '=', campo_recepcion),
            ('campo_destino_id.ttype', '=', 'char')], limit=1)
        return mapeo.campo_destino_id.name or False

    def _moves_por_dato(self, campo_recepcion, valor, dominio_base=None):
        """Comprobantes (no cancelados) de la compañía con ese dato (CDC o número): los que
        generó una recepción y, si hay un mapeo activo del dato, también los que lo tengan
        en el campo mapeado."""
        self.ensure_one()
        Move = self.env['account.move'].sudo()
        recepciones = self.sudo().search([
            ('company_id', '=', self.company_id.id), (campo_recepcion, '=', valor),
            ('move_id', '!=', False), ('move_id.state', '!=', 'cancel')])
        moves = recepciones.move_id
        campo = self._campo_mapeado(campo_recepcion)
        if campo and campo in Move._fields:
            moves |= Move.search(list(dominio_base or [
                ('company_id', '=', self.company_id.id), ('state', '!=', 'cancel')])
                + [(campo, '=', valor)])
        return moves

    @staticmethod
    def _cdc_de_asociados(asociados):
        for asociado in (asociados or []):
            cdc = (asociado.get('cdc') or '').strip()
            if len(cdc) == 44 and cdc.isdigit():
                return cdc
        return False

    @staticmethod
    def _partes_asociado(asociado):
        if asociado.get('cdc'):
            partes = xml_parser.componentes_cdc(asociado['cdc'])
            if partes:
                return partes['establecimiento'], partes['punto'], partes['numero']
        if asociado.get('establecimiento') and asociado.get('punto') and asociado.get('numero'):
            return (asociado['establecimiento'].zfill(3), asociado['punto'].zfill(3),
                    asociado['numero'].zfill(7))
        return None

    # ------------------------------------------------------------------
    # Diagnóstico (impedimentos y avisos)
    # ------------------------------------------------------------------
    def _diagnostico(self):
        """(impedimentos, avisos) de la recepción. No simula la factura."""
        self.ensure_one()
        if self.state in ('error', 'na'):
            return [], []
        bloqueos, avisos = [], []
        company = self.company_id

        if not self.partner_id:
            bloqueos.append(_(
                'No hay un proveedor con RUC %s. Use "Crear proveedor" o elija el contacto.',
                self.emisor_ruc))
        else:
            base, dv = xml_parser.normalizar_vat(self.partner_id.vat)
            xml_base, xml_dv = xml_parser.normalizar_vat(self.emisor_ruc)
            if base != xml_base or (dv and xml_dv and dv != xml_dv):
                bloqueos.append(_(
                    'El RUC del contacto elegido (%(contacto)s) no coincide con el del XML (%(xml)s).',
                    contacto=self.partner_id.vat or _('sin RUC'), xml=self.emisor_ruc))

        compania_vat = company.vat or company.partner_id.vat
        if not compania_vat:
            avisos.append(_('La compañía no tiene RUC cargado: no se pudo controlar el receptor del XML.'))
        else:
            c_base, c_dv = xml_parser.normalizar_vat(compania_vat)
            r_base, r_dv = xml_parser.normalizar_vat(self.receptor_ruc)
            if c_base != r_base or (c_dv and r_dv and c_dv != r_dv):
                bloqueos.append(_(
                    'El receptor del XML (%(receptor)s) no es esta compañía (%(compania)s).',
                    receptor=self.receptor_ruc or _('sin RUC'), compania=compania_vat))

        if not self.journal_id:
            bloqueos.append(_(
                'Falta el diario de compra. Configúrelo en Ajustes › Configuración FE_Py '
                'Recepción o elíjalo en la recepción.'))
        if not self.currency_id:
            bloqueos.append(_('La moneda %s del XML no existe en Odoo.', self.moneda_codigo))
        elif not self.currency_id.active:
            bloqueos.append(_('La moneda %s está desactivada en Odoo.', self.currency_id.name))

        for linea in self.line_ids:
            etiqueta = _('Línea %s', linea.orden)
            if not linea.producto_id and not linea.cuenta_id:
                bloqueos.append(_('%s: elija un producto o una cuenta.', etiqueta))
            if linea.afectacion not in ('1', '3'):
                bloqueos.append(_(
                    '%(linea)s: la afectación de IVA "%(afectacion)s" no está soportada.',
                    linea=etiqueta, afectacion=linea.afectacion_texto))
            elif not linea.impuesto_id:
                bloqueos.append(_(
                    '%(linea)s: falta configurar el impuesto para %(tasa)s.',
                    linea=etiqueta, tasa=linea.tasa_texto))
            elif linea.tasa and not linea.impuesto_id.price_include:
                bloqueos.append(_(
                    '%(linea)s: el impuesto "%(impuesto)s" debe tener "Incluido en el precio", '
                    'porque los precios del XML ya incluyen el IVA.',
                    linea=etiqueta, impuesto=linea.impuesto_id.name))
            if linea.aviso:
                avisos.append('%s: %s' % (etiqueta, linea.aviso))

        bloqueos += self._mensajes_diferencias()

        if self.cdc and self.state in ('cargado', 'verificado'):
            # Un comprobante ya existente con el mismo CDC (de otra recepción o, con el mapeo
            # activo, cargado a mano): se avisa antes de generar un duplicado.
            duplicada = self._moves_por_dato('cdc', self.cdc).filtered(
                lambda m: m != self.move_id)[:1]
            if duplicada:
                bloqueos.append(_(
                    'Ya existe un comprobante con este CDC (%s). Revíselo: si es el mismo '
                    'documento, cancélelo o elimínelo antes de continuar.', duplicada.display_name))
        if self.descuento_global or self.anticipo:
            avisos.append(_(
                'El XML informa descuento global o anticipo (descuento global %(desc)s, anticipo '
                '%(ant)s); el módulo no los trata por separado y los totales pueden no coincidir.',
                desc=self.descuento_global, ant=self.anticipo))

        if self.termino_aviso:
            avisos.append(self.termino_aviso)
        if self._usa_cotizacion_xml() and not utilidades.tasa_odoo_desde_xml(self.tipo_cambio):
            avisos.append(_(
                'El XML está en %s pero no informa un tipo de cambio en la cabecera (o lo informa por '
                'ítem): se usa la cotización del sistema.', self.moneda_codigo or self.currency_id.name))
        if self.itide == '5' and not self.reversed_move_id:
            otra = self._moves_por_dato('cdc', self.cdc_asociado).filtered(
                lambda m: m.move_type == 'in_invoice')[:1] if self.cdc_asociado \
                else self.env['account.move']
            if otra and self.partner_id and \
                    otra.commercial_partner_id != self.partner_id.commercial_partner_id:
                avisos.append(_(
                    'La factura con el CDC asociado existe (%(factura)s) pero es de otro proveedor '
                    '(%(proveedor)s), por eso no se vinculó. Elija la factura correcta.',
                    factura=otra.display_name, proveedor=otra.commercial_partner_id.display_name))
            else:
                avisos.append(_(
                    'No se encontró la factura que afecta esta nota de crédito (%s). Elíjala; '
                    'sin ella no se podrá confirmar la nota en contabilidad.', self.asociado_texto or '-'))
        return bloqueos, avisos

    def _mensajes_diferencias(self):
        """Diferencias de total e IVA entre el XML y lo que calcula Odoo, más allá de la
        tolerancia de la compañía. Vacío si todavía no se controlaron los totales."""
        self.ensure_one()
        if not (self.control_hecho and self.currency_id):
            return []
        tolerancia = self.company_id._fe_py_recepcion_tolerancia_en(self.currency_id)
        mensajes = []
        if not utilidades.dentro_de_tolerancia(self.total_odoo - self.total_general, tolerancia):
            mensajes.append(_(
                'El total calculado por Odoo (%(odoo)s) difiere del XML (%(xml)s).',
                odoo=self.total_odoo, xml=self.total_general))
        if not utilidades.dentro_de_tolerancia(self.iva_odoo - self.total_iva, tolerancia):
            mensajes.append(_(
                'El IVA calculado por Odoo (%(odoo)s) difiere del XML (%(xml)s).',
                odoo=self.iva_odoo, xml=self.total_iva))
        return mensajes

    def _exigir_sin_bloqueos(self, tolerar_diferencias=False):
        """Simula la factura, actualiza el control de totales y corta si hay impedimentos.

        Con `tolerar_diferencias` una diferencia de total o IVA no corta: el proceso automático
        genera igual la factura en borrador y la deja para revisión."""
        for doc in self:
            doc._asignar_proveedor_si_falta()
            bloqueos, _avisos = doc._diagnostico()
            if not bloqueos:
                doc._controlar_totales()
                bloqueos, _avisos = doc._diagnostico()
            if tolerar_diferencias:
                diferencias = doc._mensajes_diferencias()
                bloqueos = [b for b in bloqueos if b not in diferencias]
            if bloqueos:
                raise UserError(_('%(doc)s no se puede continuar:\n%(lista)s',
                                  doc=doc.name, lista='\n'.join('• %s' % b for b in bloqueos)))

    def _asignar_proveedor_si_falta(self):
        for doc in self.filtered(lambda d: not d.partner_id):
            doc.partner_id = doc._buscar_proveedor()

    # ------------------------------------------------------------------
    # Factura de proveedor
    # ------------------------------------------------------------------
    def _es_moneda_extranjera(self):
        self.ensure_one()
        return bool(self.currency_id) and self.currency_id != self.company_id.currency_id

    def _usa_cotizacion_xml(self):
        """True si la compañía pide la cotización del XML y el documento está en moneda extranjera."""
        self.ensure_one()
        return self.company_id.fe_py_recepcion_cotizacion == 'xml' and self._es_moneda_extranjera()

    def _vals_factura(self, avisos=None):
        """Valores de la factura. Solo datos estándar de Odoo; si el mapeo de campos está
        activo se agregan los campos mapeados. `avisos` (lista) recibe lo que no se pudo copiar."""
        self.ensure_one()
        vals = {
            'move_type': self.move_type,
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
            'journal_id': self.journal_id.id,
            'currency_id': self.currency_id.id,
            'invoice_date': self.fecha_emision,
            'ref': self.nro_documento,
            'invoice_payment_term_id': self.payment_term_id.id or False,
            'invoice_line_ids': [Command.create(self._vals_linea_factura(linea, avisos))
                                 for linea in self.line_ids.sorted('orden')],
        }
        if self.reversed_move_id:
            vals['reversed_entry_id'] = self.reversed_move_id.id
        if self._usa_cotizacion_xml():
            tasa = utilidades.tasa_odoo_desde_xml(self.tipo_cambio)
            if tasa:
                vals['invoice_currency_rate'] = tasa
        if self.company_id._fe_py_recepcion_mapeo_activo():
            mapeados, avisos_mapeo = self.env['fe_py_recepcion.mapeo'].valores(
                self.company_id, 'cabecera', self.itide, self)
            vals.update(mapeados)
            if avisos is not None:
                avisos.extend(avisos_mapeo)
        return vals

    def _vals_linea_factura(self, linea, avisos=None):
        """Valores de una línea de la factura. Punto de extensión (módulo puente)."""
        vals = {
            'sequence': linea.orden * 10,
            'name': linea.descripcion or (linea.producto_id.display_name or '/'),
            'quantity': linea.cantidad,
            'price_unit': linea.precio,
            'discount': linea.descuento,
            'tax_ids': [Command.set(linea.impuesto_id.ids)],
        }
        if linea.producto_id:
            vals['product_id'] = linea.producto_id.id
        if linea.cuenta_id:
            vals['account_id'] = linea.cuenta_id.id
        if self.company_id._fe_py_recepcion_mapeo_activo():
            mapeados, avisos_mapeo = self.env['fe_py_recepcion.mapeo'].valores(
                self.company_id, 'linea', self.itide, linea)
            vals.update(mapeados)
            if avisos is not None:
                avisos.extend('%s %s: %s' % (_('Línea'), linea.orden, a) for a in avisos_mapeo)
        return vals

    def _simular_totales(self):
        """Total e IVA que calcularía Odoo, creando la factura en un savepoint
        que se descarta. Devuelve (total, iva)."""
        self.ensure_one()
        resultado = {}
        try:
            with self.env.cr.savepoint():
                Move = self.env['account.move'].with_context(
                    tracking_disable=True, mail_notrack=True, mail_create_nolog=True)
                move = Move.with_company(self.company_id).create(self._vals_factura())
                resultado['total'] = move.amount_total
                resultado['iva'] = move.amount_tax
                raise _DescartarSimulacion()
        except _DescartarSimulacion:
            pass
        except UserError as error:
            raise UserError(_('Odoo no pudo preparar la factura: %s', error)) from error
        return resultado['total'], resultado['iva']

    def _controlar_totales(self):
        for doc in self:
            total, iva = doc._simular_totales()
            doc.write({'total_odoo': total, 'iva_odoo': iva, 'control_hecho': True})

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_controlar(self):
        self._asignar_proveedor_si_falta()
        for doc in self:
            if not doc._diagnostico()[0]:
                doc._controlar_totales()
        return True

    def action_buscar_proveedor(self):
        for doc in self:
            doc.partner_id = doc._buscar_proveedor()
            if not doc.partner_id:
                raise UserError(_(
                    'No se encontró un único contacto con RUC %s.', doc.emisor_ruc))
        return True

    def action_crear_proveedor(self):
        """Abre el formulario completo de Contactos con los datos del XML."""
        self.ensure_one()
        contexto = {
            'default_name': self.emisor_nombre,
            'default_company_type': 'company',
            'default_is_company': True,
            'default_vat': self.emisor_ruc,
            'default_email': self.emisor_email,
            'default_phone': self.emisor_telefono,
            'default_street': self.emisor_direccion,
            'default_city': self.emisor_ciudad,
            'fe_py_recepcion_proveedor_nuevo': True,
        }
        if self.company_id._fe_py_recepcion_mapeo_activo():
            mapeados, _avisos = self.env['fe_py_recepcion.mapeo'].valores(
                self.company_id, 'proveedor', self.itide, self)
            for campo, valor in mapeados.items():
                contexto['default_%s' % campo] = valor
        return {
            'type': 'ir.actions.act_window',
            'name': _('Nuevo proveedor'),
            'res_model': 'res.partner',
            'view_mode': 'form',
            'target': 'current',
            'context': contexto,
        }

    def action_verificar(self):
        for doc in self:
            if doc.state != 'cargado':
                raise UserError(_('Solo se puede verificar una recepción en estado Cargado.'))
        self._exigir_sin_bloqueos()
        self.write({'state': 'verificado', 'confirmacion_auto_motivo': False})
        for doc in self:
            doc.message_post(body=_('Recepción verificada por %s.', self.env.user.name))
        return True

    def action_volver_cargado(self):
        for doc in self:
            if doc.state != 'verificado':
                raise UserError(_('Solo se puede volver a Cargado una recepción Verificada.'))
        self.write({'state': 'cargado', 'control_hecho': False})
        return True

    def action_confirmar(self):
        """Genera la factura (o nota) de proveedor. Queda publicada si la compañía deja las
        facturas leídas en «Confirmado» y el proveedor tiene la confirmación automática; si no,
        queda en borrador. El usuario ya revisó el registro: no se vuelven a exigir los criterios
        automáticos, solo los impedimentos y la regla de recepción de mercadería pendiente."""
        for doc in self:
            if doc.state != 'verificado':
                raise UserError(_('Solo se puede confirmar una recepción Verificada.'))
        self._exigir_sin_bloqueos()
        self.write({'confirmacion_auto_motivo': False})
        for doc in self:
            doc._generar_factura()
            doc._intentar_publicar(manual=True)
            doc._enlazar_notas_pendientes()
        return True

    def _generar_factura(self, registrar_equivalencias=True):
        """Crea la factura de proveedor en borrador y deja el registro en estado Borrador."""
        self.ensure_one()
        Move = self.env['account.move'].with_context(mail_create_nolog=True)
        avisos = []
        move = Move.with_company(self.company_id).create(self._vals_factura(avisos))
        self.write({'move_id': move.id, 'state': 'borrador'})
        self._copiar_xml_a(move)
        if registrar_equivalencias:
            self._registrar_equivalencias()
        self._post_confirmar(move)
        self.message_post(body=_('Factura de proveedor %s generada en borrador.', move.display_name))
        move.message_post(body=_('Generada desde la factura electrónica recibida %s.', self.name))
        self._avisar_mapeo(move, avisos)
        self._avisar_cotizacion(move)
        return move

    def _avisar_cotizacion(self, move):
        """Nota informativa (no impide publicar) sobre la cotización aplicada a una factura en
        moneda extranjera cuando la del XML y la del sistema difieren."""
        self.ensure_one()
        if not self._es_moneda_extranjera():
            return
        tasa_xml = utilidades.tasa_odoo_desde_xml(self.tipo_cambio)
        tasa_sistema = move._get_expected_currency_rate_at(move._get_invoice_currency_rate_date())
        if not (tasa_xml and tasa_sistema) or not utilidades.cotizaciones_difieren(tasa_xml, tasa_sistema):
            return
        moneda, base = self.currency_id.name, self.company_id.currency_id.name
        por_unidad = lambda tasa: '%s %s' % (format(1.0 / tasa, ',.4f'), base)
        if move.invoice_currency_rate and not utilidades.cotizaciones_difieren(
                move.invoice_currency_rate, tasa_xml):
            texto = _('Se aplicó la cotización del XML: 1 %(moneda)s = %(xml)s. La cotización del '
                      'sistema a la fecha de emisión es 1 %(moneda)s = %(sistema)s.',
                      moneda=moneda, xml=por_unidad(tasa_xml), sistema=por_unidad(tasa_sistema))
        else:
            texto = _('Se aplicó la cotización del sistema: 1 %(moneda)s = %(sistema)s. El XML '
                      'informa 1 %(moneda)s = %(xml)s.',
                      moneda=moneda, xml=por_unidad(tasa_xml), sistema=por_unidad(tasa_sistema))
        move.message_post(body=texto)
        self.message_post(body=texto)

    def _avisar_mapeo(self, move, avisos):
        """Deja en el chatter de la factura si se copiaron datos a otros campos o por qué no."""
        estado = self.company_id.fe_py_recepcion_mapeo_estado
        if estado == 'activo':
            if avisos:
                texto = _('Mapeo de campos: algunos datos no se copiaron:') + '<ul>%s</ul>' % ''.join(
                    '<li>%s</li>' % escape(a) for a in avisos)
                move.message_post(body=Markup(texto))
                self.message_post(body=Markup(texto))
            return
        motivo = _('no hay un mapeo de campos configurado') if estado == 'sin_mapeo' else \
            _('el mapeo de campos está apagado en Ajustes')
        move.message_post(body=_(
            'Generada solo con datos estándar de Odoo (%(motivo)s). El CDC, el timbrado y los demás '
            'datos del XML quedan en la recepción %(doc)s.', motivo=motivo, doc=self.name))

    def _post_confirmar(self, move):
        """Punto de extensión después de generar la factura (módulo puente)."""

    def _copiar_xml_a(self, move):
        self.ensure_one()
        if self.xml_attachment_id:
            self.xml_attachment_id.copy({'res_model': 'account.move', 'res_id': move.id})

    def _registrar_equivalencias(self):
        Equivalencia = self.env['fe_py_recepcion.equivalencia']
        for linea in self.line_ids.filtered('producto_id'):
            Equivalencia.registrar(self.partner_id, linea.codigo, linea.descripcion,
                                   linea.producto_id, self.company_id)

    # ------------------------------------------------------------------
    # Carga con registro de errores (carga manual y correo)
    # ------------------------------------------------------------------
    @staticmethod
    def _vals_correo(correo):
        if not correo:
            return {}
        return {
            'origen': 'correo',
            'correo_remitente': correo.get('remitente') or False,
            'correo_asunto': correo.get('asunto') or False,
            'correo_fecha': correo.get('fecha') or False,
            'correo_message_id': correo.get('message_id') or False,
        }

    @api.model
    def cargar_xml_o_registrar_error(self, nombre, contenido, company=None, correo=None):
        """Como `crear_desde_xml`, pero un archivo que no se puede cargar no se pierde: queda
        un registro en estado Error con el XML y el motivo.

        Devuelve (recepción, creada). Un CDC ya recibido devuelve la existente y creada=False.
        La falta de licencia no genera registros: se propaga.
        """
        company = company or self.env.company
        fe_py_recepcion_licencia_verificar(self.env, company)
        contenido = utilidades.a_bytes(contenido)
        try:
            with self.env.cr.savepoint():
                doc, creado = self.crear_desde_xml(
                    nombre, contenido, company=company, extra_vals=self._vals_correo(correo))
        except RecepcionNA as error:
            motivo = str(error.args[0]) if error.args else str(error)
            return self._registrar_na(nombre, contenido, company, motivo, correo), True
        except Exception as error:  # el archivo no debe frenar la carga de los demás
            if isinstance(error, UserError):
                motivo = str(error.args[0]) if error.args else str(error)
            else:
                _logger.exception('FE_Py Recepción: error inesperado al cargar %s', nombre)
                motivo = _('%(archivo)s: error inesperado (%(error)s).', archivo=nombre, error=error)
            return self._registrar_error(nombre, contenido, company, motivo, correo), True
        if not creado and correo:
            doc.message_post(body=_(
                'El mismo documento llegó otra vez por correo (%(asunto)s, de %(remitente)s).',
                asunto=correo.get('asunto') or '-', remitente=correo.get('remitente') or '-'))
            duplicado = self._registrar_na(
                nombre, contenido, company,
                _('El CDC ya fue recibido en %s; este correo es un duplicado.', doc.name),
                correo, original=doc)
            return duplicado, True
        return doc, creado

    @api.model
    def _registrar_na(self, nombre, contenido, company, motivo, correo=None, original=None):
        """Registro N/A: el correo o archivo se leyó pero no corresponde cargarlo como factura.
        Conserva el XML (si hay) y el motivo para poder comprobar que se leyó."""
        vals = {'company_id': company.id, 'state': 'na', 'na_motivo': motivo}
        vals.update(self._vals_correo(correo))
        if original:
            vals['documento_original_id'] = original.id
        else:
            cdc = utilidades.extraer_cdc_aproximado(contenido) if contenido else False
            if cdc and not self.search_count([('cdc', '=', cdc), ('company_id', '=', company.id)]):
                vals['cdc'] = cdc
        doc = self.create(vals)
        if contenido:
            doc._adjuntar_xml(nombre, contenido)
        doc.message_post(body=_('Registro N/A: %s', motivo))
        return doc

    @api.model
    def _registrar_error(self, nombre, contenido, company, motivo, correo=None):
        vals = {'company_id': company.id, 'state': 'error', 'error_detalle': motivo}
        vals.update(self._vals_correo(correo))
        cdc = utilidades.extraer_cdc_aproximado(contenido) if contenido else False
        if cdc and not self.search_count([('cdc', '=', cdc), ('company_id', '=', company.id)]):
            vals['cdc'] = cdc
        doc = self.create(vals)
        if contenido:
            doc._adjuntar_xml(nombre, contenido)
        doc.message_post(body=_('No se pudo cargar: %s', motivo))
        return doc

    def action_reintentar(self):
        """Vuelve a leer el XML guardado; si ahora se puede cargar, reemplaza al registro con error."""
        self.ensure_one()
        if self.state != 'error' or not self.xml_attachment_id:
            raise UserError(_('Solo se puede reintentar un registro con error que tenga su XML.'))
        nombre, contenido = self.xml_attachment_id.name, self.xml_attachment_id.raw
        extra = {campo: self[campo] for campo in (
            'origen', 'correo_remitente', 'correo_asunto', 'correo_fecha', 'correo_message_id')}
        try:
            with self.env.cr.savepoint():
                self.cdc = False  # libera el CDC para poder crear el registro definitivo
                doc, creado = self.crear_desde_xml(
                    nombre, contenido, company=self.company_id, extra_vals=extra)
        except RecepcionNA as error:
            motivo = str(error.args[0]) if error.args else str(error)
            self.write({'state': 'na', 'na_motivo': motivo, 'error_detalle': False})
            self.message_post(body=_('Pasó a N/A: %s', motivo))
            return True
        except UserError as error:
            motivo = str(error.args[0]) if error.args else str(error)
            self.write({'error_detalle': motivo})
            self.message_post(body=_('Reintento sin éxito: %s', motivo))
            return True
        if not creado:
            motivo = _('El CDC ya fue recibido en %s; este archivo es un duplicado.', doc.name)
            self.write({'state': 'na', 'cdc': False, 'na_motivo': motivo, 'error_detalle': False,
                        'documento_original_id': doc.id})
            self.message_post(body=_('Pasó a N/A: %s', motivo))
            return True
        doc.message_post(body=_('Cargada al reintentar la lectura de un registro con error.'))
        self.unlink()
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': doc.id,
            'view_mode': 'form', 'target': 'current',
        }

    def action_descartar(self):
        for doc in self:
            if doc.state != 'error':
                raise UserError(_('Solo se puede descartar un registro con error.'))
            doc.message_post(body=_('Registro con error descartado por %s.', self.env.user.name))
        self.write({'state': 'cancelado'})
        return True

    # ------------------------------------------------------------------
    # Recepción por correo (servidor de correo entrante propio de la compañía)
    # ------------------------------------------------------------------
    @api.model
    def message_new(self, msg_dict, custom_values=None):
        """Cada correo recibido en la cuenta de la compañía crea un registro por cada XML
        adjunto. Odoo necesita un registro donde guardar el correo: se devuelve el primero."""
        company, motivo = self._company_del_correo(msg_dict)
        nuevos, existentes = self._procesar_correo(msg_dict, company, motivo_previo=motivo)
        return (nuevos or existentes)[:1]

    @api.model
    def _company_del_correo(self, msg_dict):
        """(compañía, motivo). Identifica la cuenta de correo que recibió el mensaje: por el
        contexto de Odoo, por la dirección del destinatario o, si hay una sola cuenta de
        recepción, esa. Si no se puede saber a qué compañía pertenece, devuelve la compañía
        actual y el motivo: el correo queda como registro con error, no se pierde."""
        Servidor = self.env['fetchmail.server'].sudo()
        servidor = Servidor.browse(self.env.context.get('default_fetchmail_server_id') or 0).exists()
        if not servidor:
            propios = Servidor.search([('object_id.model', '=', self._name)])
            recibido = ' '.join(filter(None, [
                msg_dict.get('to'), msg_dict.get('recipients'), msg_dict.get('cc')])).lower()
            coincide = propios.filtered(lambda s: s.user and s.user.lower() in recibido)
            servidor = coincide if len(coincide) == 1 else (propios if len(propios) == 1 else Servidor)
        company = servidor._fe_py_recepcion_company() if servidor else self.env['res.company']
        if company:
            return company, False
        return self.env.company, _(
            'No se pudo saber a qué compañía pertenece la cuenta de correo que recibió este mensaje. '
            'Revise en Ajustes > Configuración FE_Py Recepción que la cuenta esté asignada a la '
            'compañía y use "Reintentar lectura".')

    @api.model
    def _correo_se_ignora(self, crudo):
        """True si el correo (sin procesar) no trae XML y la compañía eligió no registrar esos
        correos. Se consulta antes de procesar el mensaje, para no dejar ningún registro."""
        company, motivo = self._company_del_correo({})
        if motivo or not company or company.fe_py_recepcion_registrar_sin_xml:
            return False
        try:
            if hasattr(crudo, 'data'):
                crudo = bytes(crudo.data)
            return not utilidades.correo_trae_xml(crudo)
        except Exception:  # noqa: BLE001 - ante la duda, se procesa normalmente
            _logger.exception('FE_Py Recepción: no se pudo revisar el correo antes de procesarlo')
            return False

    @api.model
    def _procesar_correo(self, msg_dict, company, motivo_previo=False):
        adjuntos = [(a[0], a[1]) for a in (msg_dict.get('attachments') or [])]
        correo = {
            'remitente': msg_dict.get('email_from'), 'asunto': msg_dict.get('subject'),
            'fecha': msg_dict.get('date'), 'message_id': msg_dict.get('message_id'),
        }
        expandido = utilidades.expandir_adjuntos(adjuntos)   # abre los ZIP
        xmls, pdfs = expandido['xmls'], expandido['pdfs']
        nuevos, existentes = self.browse(), self.browse()
        if motivo_previo:
            for nombre, contenido in (xmls or [(None, None)]):
                doc = self._registrar_error(
                    nombre, utilidades.a_bytes(contenido) if contenido else None, company,
                    motivo_previo, correo)
                doc._adjuntar_pdfs(pdfs)
                nuevos |= doc
            return nuevos, existentes
        if not xmls:
            doc = self._registrar_na(None, None, company, utilidades.motivo_sin_xml(expandido), correo)
            doc._adjuntar_pdfs(pdfs)
            return doc, existentes
        for nombre, contenido in xmls:
            contenido = utilidades.a_bytes(contenido)
            doc, creado = self.cargar_xml_o_registrar_error(nombre, contenido, company, correo)
            if creado:
                nuevos |= doc
                indices = utilidades.emparejar_pdf(
                    nombre, doc.cdc, [p[0] for p in pdfs], len(xmls))
                doc._adjuntar_pdfs([pdfs[i] for i in indices])
            else:
                existentes |= doc
        return nuevos, existentes

    def _adjuntar_pdfs(self, pdfs):
        """Guarda los PDF (KuDE) que llegaron junto al XML."""
        self.ensure_one()
        for nombre, contenido in pdfs:
            self.env['ir.attachment'].create({
                'name': nombre, 'raw': utilidades.a_bytes(contenido),
                'mimetype': 'application/pdf', 'res_model': self._name, 'res_id': self.id,
            })

    # ------------------------------------------------------------------
    # Proceso automático: XML leído -> factura en borrador -> publicada
    # ------------------------------------------------------------------
    def _procesar_automatico(self):
        """Lleva el XML leído hasta la factura, nota de crédito o nota de débito de proveedor.

        1) Si falta algo imprescindible (proveedor, impuestos, cotización dudosa),
           el registro queda en Cargado con el motivo y no se genera nada.
        2) Si no, se controlan los totales (Verificado) y se genera la factura en Borrador.
        3) La factura se publica (Confirmado) solo si la compañía lo permite, el proveedor tiene
           la confirmación automática y se cumplen los criterios; si no, queda en borrador.
        """
        self.ensure_one()
        if self.state not in ('cargado', 'verificado'):
            return False
        if not self.partner_id:
            self._guardar_motivo(_(
                'No hay un proveedor con RUC %s. Elija o cree el contacto: al asignarlo el proceso '
                'continúa solo.', self.emisor_ruc))
            return False
        try:
            with self.env.cr.savepoint():
                self._preparar_factura_automatica()
        except Exception as error:  # una recepción no debe frenar la carga de las demás
            if not isinstance(error, UserError):
                _logger.exception('FE_Py Recepción: falló el proceso automático de %s', self.name)
            self.env.invalidate_all()
            self._guardar_motivo(error.args[0] if isinstance(error, UserError) and error.args
                                 else str(error))
            return False
        self._intentar_publicar()
        self._enlazar_notas_pendientes()
        return True

    def _preparar_factura_automatica(self):
        self.ensure_one()
        self._preparar_cotizacion_automatica()
        self._exigir_sin_bloqueos(tolerar_diferencias=True)
        self.write({'state': 'verificado', 'confirmacion_auto_motivo': False})
        # los productos sugeridos no se registran como equivalencia hasta que una persona los
        # confirme (al publicar o al usar «Confirmar»)
        self._generar_factura(registrar_equivalencias=False)

    def _guardar_motivo(self, motivo):
        self.ensure_one()
        self.write({'confirmacion_auto_motivo': motivo})
        self.message_post(body=_(
            'El proceso automático se detuvo. Revise el registro y use «Reprocesar» o continúe a '
            'mano. Motivo: %s', motivo))

    def _intentar_publicar(self, manual=False):
        """Publica la factura generada si corresponde. Devuelve True si quedó publicada.

        Publica solo con la compañía en «Confirmado» y el proveedor con la confirmación
        automática. Con `manual` (botón «Confirmar») solo se exige la regla de recepción
        de mercadería pendiente; en el proceso automático, todos los criterios."""
        self.ensure_one()
        if self.state != 'borrador' or not self.move_id or self.move_id.state != 'draft':
            return False
        if self.company_id.fe_py_recepcion_estado_facturas != 'confirmado':
            self.message_post(body=_(
                'Factura en borrador: la compañía deja las facturas leídas en borrador.'))
            return False
        if not self.partner_id.sudo().fe_py_recepcion_confirmar_auto:
            self.message_post(body=_(
                'Factura en borrador: el proveedor no tiene marcada la confirmación automática.'))
            return False
        if manual:
            motivos, cumplidos = self._motivos_recepcion_pendiente(), []
        else:
            motivos, cumplidos = self._evaluar_publicacion()
        if motivos:
            self.write({'confirmacion_auto_motivo': '\n'.join('• %s' % m for m in motivos)})
            self.message_post(body=_(
                'La factura quedó en borrador: no se publicó automáticamente. Motivos: %s',
                ' | '.join(motivos)))
            return False
        try:
            with self.env.cr.savepoint():
                self.move_id.with_context(
                    fe_py_recepcion_origen_publicacion='manual' if manual else 'automatico',
                    fe_py_recepcion_criterios='; '.join(cumplidos),
                ).action_post()
        except Exception as error:  # período bloqueado, número repetido, timbrado, etc.
            if not isinstance(error, UserError):
                _logger.exception('FE_Py Recepción: falló la publicación de %s', self.name)
            self.env.invalidate_all()
            motivo = error.args[0] if isinstance(error, UserError) and error.args else str(error)
            self.write({'confirmacion_auto_motivo': _('No se pudo publicar: %s', motivo)})
            self.message_post(body=_(
                'La factura quedó en borrador: no se pudo publicar. Motivo: %s', motivo))
            return False
        if self.state == 'borrador':
            self._marcar_confirmado('manual' if manual else 'automatico', '; '.join(cumplidos))
        return True

    def _evaluar_publicacion(self):
        """(motivos, criterios cumplidos) para publicar automáticamente."""
        self.ensure_one()
        motivos, cumplidos = [], []
        bloqueos, avisos = self._diagnostico()
        motivos += bloqueos
        motivos += [_('Aviso: %s', a) for a in avisos]
        if not bloqueos:
            tolerancia = self.company_id._fe_py_recepcion_tolerancia_en(self.currency_id)
            cumplidos.append(_('totales e IVA dentro de la tolerancia (%s)', tolerancia))
        if not avisos:
            cumplidos.append(_('sin avisos'))
        productos = self._motivos_productos()
        motivos += productos
        if not productos:
            cumplidos.append(_('productos de equivalencias confirmadas o confirmados por una persona'))
        for revisar, criterio in ((self._motivos_nota, _('factura asociada publicada')),
                                  (self._motivos_remitente, _('remitente validado')),
                                  (self._motivos_cotizacion, _('cotización coincide exacta')),
                                  (self._motivos_recepcion_pendiente, _('sin recepción pendiente'))):
            encontrados = revisar()
            motivos += encontrados
            if not encontrados:
                cumplidos.append(criterio)
        return motivos, cumplidos

    def _motivos_productos(self):
        """Los productos deben venir de una equivalencia ya confirmada con el proveedor o haber
        sido elegidos o confirmados por una persona (origen Manual). Un producto que solo
        sugirió el sistema (GTIN, referencia o nombre) no alcanza. Los de lote o serie solo se
        aceptan si el módulo de Compras los cubre."""
        self.ensure_one()
        motivos = []
        etiquetas = dict(self.env['fe_py_recepcion.documento.linea']._fields[
            'producto_origen']._description_selection(self.env))
        for linea in self.line_ids:
            etiqueta = _('Línea %s', linea.orden)
            if not linea.producto_id:
                motivos.append(_('%s: no tiene producto asignado.', etiqueta))
            elif linea.producto_origen not in ('equivalencia', 'manual'):
                motivos.append(_(
                    '%(linea)s: el producto lo sugirió el sistema (%(origen)s) y ninguna persona '
                    'lo confirmó. Use «Confirmar productos».',
                    linea=etiqueta,
                    origen=etiquetas.get(linea.producto_origen) or _('sin origen')))
            elif getattr(linea.producto_id, 'tracking', 'none') in ('lot', 'serial') \
                    and not self._linea_con_lote_cubierta(linea):
                motivos.append(_(
                    '%(linea)s: el producto "%(producto)s" lleva lote o serie y no está vinculado '
                    'a una cotización.', linea=etiqueta, producto=linea.producto_id.display_name))
        return motivos

    def action_confirmar_productos(self):
        """Una persona acepta los productos que sugirió el sistema (GTIN, referencia o nombre):
        pasan a origen Manual y desde entonces cuentan para la publicación automática. La
        equivalencia con el proveedor se registra recién al publicarse la factura."""
        confirmadas = 0
        for doc in self:
            if doc.state not in ('cargado', 'verificado', 'borrador'):
                raise UserError(_('Solo se pueden confirmar productos en una recepción abierta.'))
            lineas = doc.line_ids.filtered(
                lambda l: l.producto_id and l.producto_origen in PRODUCTO_ORIGEN_SUGERIDO)
            if lineas:
                lineas.write({'producto_origen': 'manual'})
                confirmadas += len(lineas)
                doc.message_post(body=_(
                    '%(usuario)s confirmó los productos sugeridos de las líneas: %(lineas)s.',
                    usuario=self.env.user.name,
                    lineas=', '.join(str(n) for n in lineas.sorted('orden').mapped('orden'))))
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Confirmar productos'), 'type': 'info', 'sticky': False,
                'message': _('%s línea(s) confirmada(s). Use «Reprocesar» para publicar la factura '
                             'si corresponde.', confirmadas),
            },
        }

    def _linea_con_lote_cubierta(self, linea):
        """Punto de extensión (módulo puente): un producto con lote o serie solo se publica solo
        si la línea está vinculada a una cotización, donde el lote se asigna al recibir."""
        return False

    def _motivos_nota(self):
        """Una nota de crédito se publica solo si su factura asociada ya está publicada."""
        self.ensure_one()
        if self.itide == '5' and self.reversed_move_id and self.reversed_move_id.state != 'posted':
            return [_('La factura asociada %s todavía no está publicada.',
                      self.reversed_move_id.display_name)]
        return []

    def _motivos_remitente(self):
        """El remitente del correo debe coincidir con un correo (o el dominio) del proveedor."""
        self.ensure_one()
        if self.origen != 'correo' or not self.company_id.fe_py_recepcion_validar_remitente:
            return []
        proveedor = self.partner_id.commercial_partner_id
        correos = proveedor.sudo().mapped('email') + proveedor.sudo().child_ids.mapped('email')
        coincide, motivo = utilidades.remitente_coincide(self.correo_remitente, correos)
        return [] if coincide else [motivo]

    def _motivos_cotizacion(self):
        """Punto de extensión (módulo puente): la cotización vinculada debe coincidir exacta."""
        return []

    def _motivos_recepcion_pendiente(self):
        """Punto de extensión (módulo puente): mercadería que debe recibirse antes de facturar."""
        return []

    def _marcar_confirmado(self, origen='factura', criterios=False):
        """La factura generada quedó publicada: el registro pasa a Confirmado."""
        for doc in self.with_context(fe_py_recepcion_licencia_omitir=True).filtered(
                lambda d: d.state == 'borrador'):
            doc.write({'state': 'confirmado', 'confirmacion_auto_motivo': False})
            doc._registrar_equivalencias()
            factura = doc.move_id.display_name
            if origen == 'automatico':
                doc.message_post(body=_(
                    'Publicada automáticamente: %(factura)s. Criterios cumplidos: %(criterios)s.',
                    factura=factura, criterios=criterios or '-'))
            elif origen == 'manual':
                doc.message_post(body=_(
                    'Factura %s publicada al confirmar la recepción.', factura))
            else:
                doc.message_post(body=_(
                    'La factura %s se publicó; la recepción pasó a Confirmado.', factura))
            doc._reevaluar_notas_asociadas()

    def _volver_a_borrador_por_factura(self):
        """La factura publicada volvió a borrador: el registro vuelve a Borrador."""
        for doc in self.with_context(fe_py_recepcion_licencia_omitir=True).filtered(
                lambda d: d.state == 'confirmado'):
            doc.write({'state': 'borrador'})
            doc.message_post(body=_('La factura volvió a borrador; la recepción volvió a Borrador.'))

    def _reevaluar_notas_asociadas(self):
        """Al publicarse una factura, las notas de crédito que la afectan se re-evalúan."""
        self.ensure_one()
        if self.itide == '5' or not self.move_id:
            return
        notas = self.sudo().search([
            ('itide', '=', '5'), ('state', '=', 'borrador'), ('reversed_move_id', '=', self.move_id.id)])
        for nota in notas.with_context(fe_py_recepcion_licencia_omitir=True):
            nota._intentar_publicar()

    def _enlazar_notas_pendientes(self):
        """Una nota de crédito que llegó antes que su factura queda sin factura asociada. Al
        generarse la factura se busca de nuevo: si ahora la encuentra, se completa el vínculo y
        se sigue con el proceso (la nota se publica sola si no tiene otra inconsistencia)."""
        self.ensure_one()
        if self.itide == '5' or not self.move_id or not self.partner_id:
            return
        pendientes = self.sudo().with_context(fe_py_recepcion_licencia_omitir=True).search([
            ('itide', '=', '5'), ('company_id', '=', self.company_id.id), ('reversed_move_id', '=', False),
            ('state', 'in', ('cargado', 'verificado', 'borrador')),
            ('partner_id.commercial_partner_id', '=', self.partner_id.commercial_partner_id.id)])
        for nota in pendientes:
            nota._asignar_asociado()
            if not nota.reversed_move_id:
                continue
            nota.message_post(body=_(
                'Se encontró la factura asociada %s.', nota.reversed_move_id.display_name))
            if nota.state == 'borrador':
                if nota.move_id.state == 'draft':
                    nota.move_id.write({'reversed_entry_id': nota.reversed_move_id.id})
                nota._intentar_publicar()
            else:
                nota._procesar_automatico()

    def _preparar_cotizacion_automatica(self):
        """Extensión para el módulo puente de Compras. Sin él no hay cotización que vincular."""
        self.ensure_one()

    def action_reprocesar(self):
        """Vuelve a ejecutar el proceso automático sobre los registros seleccionados, por
        ejemplo después de cargar una equivalencia, corregir un proveedor o completar el mapeo.

        Con la factura en Borrador, se elimina ese borrador y se genera de nuevo con la
        configuración actual (los cambios manuales hechos en el borrador se pierden). Si el
        borrador ya estuvo publicado una vez (tiene número) o no se puede eliminar, no se toca y solo
        se reintenta publicarlo."""
        procesados = 0
        for doc in self:
            if doc.state == 'borrador' and doc._regenerar_borrador():
                procesados += 1
            elif doc.state in ('cargado', 'verificado'):
                doc._procesar_automatico()
                procesados += 1
            elif doc.state == 'borrador':
                doc._intentar_publicar()
                procesados += 1
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'title': _('Reprocesar'), 'type': 'info', 'sticky': False,
                'message': _('%s registro(s) reprocesado(s).', procesados),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }

    def _regenerar_borrador(self):
        """Elimina la factura en borrador de la recepción y vuelve a ejecutar el proceso
        automático. Devuelve False si el borrador no se pudo eliminar."""
        self.ensure_one()
        move = self.move_id
        if not move or move.state != 'draft' or move.posted_before:
            # un borrador que ya estuvo publicado tiene número consumido: no se elimina
            return False
        nombre = move.display_name
        try:
            with self.env.cr.savepoint():
                move.with_context(fe_py_recepcion_licencia_omitir=True).sudo().unlink()
        except UserError as error:
            self.message_post(body=_(
                'No se pudo eliminar la factura en borrador %(factura)s para generarla de nuevo '
                '(%(motivo)s); solo se reintenta publicarla.', factura=nombre, motivo=error))
            return False
        self.message_post(body=_(
            'Reprocesar: se eliminó la factura en borrador %s para generarla de nuevo con la '
            'configuración actual.', nombre))
        if self.state in ('cargado', 'verificado'):
            self._procesar_automatico()
        return True

    def action_cancelar(self):
        for doc in self:
            if doc.state in ('borrador', 'confirmado'):
                raise UserError(_(
                    'Ya se generó la factura de proveedor. Para anular la recepción, cancele o '
                    'elimine esa factura: la recepción vuelve sola a Cargado y desde ahí se puede '
                    'cancelar.'))
        self.write({'state': 'cancelado'})
        return True

    def action_reabrir(self):
        for doc in self:
            if doc.state != 'cancelado':
                raise UserError(_('Solo se puede reabrir una recepción Cancelada.'))
        for doc in self:
            # un registro que nunca pudo leerse vuelve a Error, no a Cargado
            doc.write({'state': 'cargado' if doc.itide and doc.cdc else 'error', 'control_hecho': False})
        return True

    def action_ver_factura(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_ver_xml(self):
        self.ensure_one()
        if not self.xml_attachment_id:
            raise UserError(_('Esta recepción no tiene el XML adjunto.'))
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % self.xml_attachment_id.id,
            'target': 'self',
        }

    def _volver_a_cargado_por_factura(self):
        """La factura generada se eliminó o canceló: la recepción vuelve a Cargado."""
        for doc in self.with_context(fe_py_recepcion_licencia_omitir=True).filtered(
                lambda d: d.state in ('borrador', 'confirmado')):
            doc.write({'state': 'cargado', 'move_id': False, 'control_hecho': False})
            doc.message_post(body=_(
                'La factura de proveedor generada se eliminó o canceló; la recepción volvió a Cargado.'))

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    def unlink(self):
        for doc in self:
            if doc.state not in ('cargado', 'verificado', 'cancelado', 'error', 'na') or doc.move_id:
                raise UserError(_(
                    'Solo se pueden eliminar recepciones Cargadas, Verificadas, Canceladas, con '
                    'Error o N/A, sin factura generada.'))
        # primero se eliminan los adjuntos (XML, PDF y los del chatter) y después el registro
        adjuntos = self.env['ir.attachment'].sudo().search(
            [('res_model', '=', self._name), ('res_id', 'in', self.ids)])
        adjuntos |= self.mapped('xml_attachment_id').sudo()
        if adjuntos:
            self.with_context(fe_py_recepcion_licencia_omitir=True).write({'xml_attachment_id': False})
            adjuntos.unlink()
        return super().unlink()
