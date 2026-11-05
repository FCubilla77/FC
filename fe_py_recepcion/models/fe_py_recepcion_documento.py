# -*- coding: utf-8 -*-
import base64
import logging
from decimal import Decimal

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError

from . import utilidades, xml_parser
from .xml_parser import XmlRecepcionError

_logger = logging.getLogger(__name__)

# itiDE -> tipo fiscal de local_py (se usan los registros que ya trae local_py,
# sin depender de FE_Py)
TIPO_FISCAL_POR_ITIDE = {
    '1': 'local_py.tipo_fiscal_factura_electronica',
    '5': 'local_py.tipo_fiscal_nota_credito',
    '6': 'local_py.tipo_fiscal_nota_debito',
}


class _DescartarSimulacion(Exception):
    """Fuerza el rollback del savepoint de la simulación."""


class FePyRecepcionDocumento(models.Model):
    """Factura electrónica recibida de un proveedor (cabecera).

    SOLO LECTURA del XML: se guardan los datos que el proveedor informó, CDC
    incluido. No se genera ni valida CDC, firma ni esquema, y no se consulta
    a SIFEN.
    """
    _name = 'fe_py_recepcion.documento'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Factura Electrónica Recibida'
    _order = 'fecha_emision desc, id desc'

    name = fields.Char(string='Documento', compute='_compute_name', store=True)
    state = fields.Selection(
        [('cargado', 'Cargado'), ('verificado', 'Verificado'),
         ('confirmado', 'Confirmado'), ('cancelado', 'Cancelado')],
        string='Estado', default='cargado', required=True, copy=False, tracking=True, index=True)
    company_id = fields.Many2one('res.company', string='Compañía', required=True, index=True,
                                 default=lambda self: self.env.company, readonly=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', readonly=True)

    # -- Datos del XML (solo lectura) ----------------------------------------
    cdc = fields.Char(string='CDC', size=44, required=True, readonly=True, copy=False, index=True,
                      help='Código de Control del DE, tal como lo informó el proveedor en el XML.')
    itide = fields.Selection(
        [('1', 'Factura electrónica'), ('5', 'Nota de crédito electrónica'),
         ('6', 'Nota de débito electrónica')],
        string='Tipo de documento', required=True, readonly=True)
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

    xml_attachment_id = fields.Many2one('ir.attachment', string='XML original', readonly=True,
                                        copy=False, ondelete='set null')

    # -- Datos que completa el usuario ---------------------------------------
    partner_id = fields.Many2one(
        'res.partner', string='Proveedor', tracking=True, index=True,
        domain="[('is_company', '=', True)]",
        help='Contacto con el mismo RUC que informa el XML.')
    journal_id = fields.Many2one(
        'account.journal', string='Diario', tracking=True,
        domain="[('type', '=', 'purchase'), ('company_id', '=', company_id), "
               "('local_py_tipo_fiscal_id.code', '=', '109')]",
        help='Diario de compra con el que se genera la factura de proveedor.')
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

    _cdc_company_uniq = models.Constraint(
        'unique(cdc, company_id)',
        'Ya existe una recepción con ese CDC en la compañía.',
    )

    # ------------------------------------------------------------------
    # Campos calculados
    # ------------------------------------------------------------------
    @api.depends('nro_documento', 'emisor_nombre')
    def _compute_name(self):
        for doc in self:
            doc.name = ' - '.join(filter(None, [doc.nro_documento, doc.emisor_nombre])) or _('Nueva')

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
    def crear_desde_xml(self, nombre, contenido, company=None):
        """Crea una recepción desde el contenido (bytes) de un XML.

        Devuelve (recepción, creada). Si el CDC ya fue recibido no se vuelve a
        crear: devuelve la existente y creada=False. Lanza UserError si el
        archivo no se puede leer.
        """
        company = company or self.env.company
        try:
            datos = xml_parser.parsear(contenido)
        except XmlRecepcionError as error:
            raise UserError(_('%(archivo)s: %(error)s', archivo=nombre, error=error)) from error

        existente = self.search([('cdc', '=', datos['cdc']), ('company_id', '=', company.id)], limit=1)
        if existente:
            return existente, False

        moneda = self.env['res.currency'].with_context(active_test=False).search(
            [('name', '=', datos['moneda'])], limit=1)
        config = self.env['fe_py_recepcion.configuracion']._get_config(company)
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
            'total_general': float(totales['total_general']),
            'total_iva': float(totales['iva']),
            'subtotal_10': float(totales['sub10']),
            'subtotal_5': float(totales['sub5']),
            'subtotal_exento': float(totales['exento']),
            'journal_id': config.diario_id.id or False,
        }
        redondeo = Decimal(str(moneda.rounding)) if moneda and moneda.rounding else Decimal('1')
        vals['line_ids'] = [Command.create(self._vals_linea_desde_item(item, redondeo))
                            for item in datos['items']]
        vals['cuota_ids'] = [
            Command.create({'numero': n, 'monto': float(c['monto']), 'vencimiento': c['vencimiento']})
            for n, c in enumerate(credito.get('cuotas') or [], start=1)]

        doc = self.create(vals)
        doc._asignar_proveedor()
        doc._asignar_producto_sugerido()
        doc._asignar_termino_pago(datos)
        doc._asignar_asociado(asociados)
        doc._adjuntar_xml(nombre, contenido)
        doc.message_post(body=_('Recepción creada desde el archivo %s.', nombre))
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
        Equivalencia = self.env['fe_py_recepcion.equivalencia']
        for doc in self.filtered('partner_id'):
            for linea in doc.line_ids:
                producto = Equivalencia.buscar_producto(
                    doc.partner_id, linea.codigo, linea.descripcion, doc.company_id)
                if producto:
                    linea.producto_id = producto

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
        """Busca la factura que afecta una nota de crédito, por su número."""
        for doc in self:
            if doc.itide != '5' or doc.reversed_move_id or not doc.partner_id:
                continue
            Move = self.env['account.move']
            for asociado in (asociados or []):
                partes = self._partes_asociado(asociado)
                if not partes:
                    continue
                numero = '%s-%s-%s' % partes
                recepcion = self.search([
                    ('company_id', '=', doc.company_id.id), ('partner_id', '=', doc.partner_id.id),
                    ('nro_documento', '=', numero), ('move_id', '!=', False)], limit=1)
                encontrada = recepcion.move_id or Move.search([
                    ('move_type', '=', 'in_invoice'), ('company_id', '=', doc.company_id.id),
                    ('partner_id', '=', doc.partner_id.id), ('l10n_py_nro_documento', '=', numero),
                    ('state', '!=', 'cancel')], limit=1)
                if encontrada:
                    doc.reversed_move_id = encontrada
                    break

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
    def _tipo_fiscal(self):
        self.ensure_one()
        xmlid = TIPO_FISCAL_POR_ITIDE.get(self.itide)
        return self.env.ref(xmlid, raise_if_not_found=False) if xmlid else self.env['local_py.tipo_fiscal']

    def _diagnostico(self):
        """(impedimentos, avisos) de la recepción. No simula la factura."""
        self.ensure_one()
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
            bloqueos.append(_('Falta el diario de compra. Configúrelo o elíjalo en la recepción.'))
        if not self.currency_id:
            bloqueos.append(_('La moneda %s del XML no existe en Odoo.', self.moneda_codigo))
        elif not self.currency_id.active:
            bloqueos.append(_('La moneda %s está desactivada en Odoo.', self.currency_id.name))
        if not self._tipo_fiscal():
            bloqueos.append(_('No se encontró el Tipo Fiscal de local_py para este documento.'))

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

        if self.control_hecho and self.currency_id:
            tolerancia = self.currency_id.rounding
            if abs(self.total_odoo - self.total_general) > tolerancia:
                bloqueos.append(_(
                    'El total calculado por Odoo (%(odoo)s) difiere del XML (%(xml)s).',
                    odoo=self.total_odoo, xml=self.total_general))
            if abs(self.iva_odoo - self.total_iva) > tolerancia:
                bloqueos.append(_(
                    'El IVA calculado por Odoo (%(odoo)s) difiere del XML (%(xml)s).',
                    odoo=self.iva_odoo, xml=self.total_iva))

        if self.termino_aviso:
            avisos.append(self.termino_aviso)
        if self.itide == '5' and not self.reversed_move_id:
            avisos.append(_(
                'No se encontró la factura que afecta esta nota de crédito (%s). Elíjala; '
                'sin ella no se podrá confirmar la nota en contabilidad.', self.asociado_texto or '-'))
        return bloqueos, avisos

    def _exigir_sin_bloqueos(self):
        """Simula la factura, actualiza el control de totales y corta si hay impedimentos."""
        for doc in self:
            doc._asignar_proveedor_si_falta()
            bloqueos, _avisos = doc._diagnostico()
            if not bloqueos:
                doc._controlar_totales()
                bloqueos, _avisos = doc._diagnostico()
            if bloqueos:
                raise UserError(_('%(doc)s no se puede continuar:\n%(lista)s',
                                  doc=doc.name, lista='\n'.join('• %s' % b for b in bloqueos)))

    def _asignar_proveedor_si_falta(self):
        for doc in self.filtered(lambda d: not d.partner_id):
            doc.partner_id = doc._buscar_proveedor()

    # ------------------------------------------------------------------
    # Factura de proveedor
    # ------------------------------------------------------------------
    def _vals_factura(self):
        self.ensure_one()
        tipo_fiscal = self._tipo_fiscal()
        vals = {
            'move_type': self.move_type,
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
            'journal_id': self.journal_id.id,
            'currency_id': self.currency_id.id,
            'invoice_date': self.fecha_emision,
            'ref': self.nro_documento,
            'invoice_payment_term_id': self.payment_term_id.id or False,
            'local_py_tipo_fiscal_id': tipo_fiscal.id,
            'l10n_py_timbrado': int(self.timbrado) if (self.timbrado or '').isdigit() else 0,
            'l10n_py_nro_documento': self.nro_documento,
            'invoice_line_ids': [Command.create(self._vals_linea_factura(linea))
                                 for linea in self.line_ids.sorted('orden')],
        }
        if self.reversed_move_id:
            vals['reversed_entry_id'] = self.reversed_move_id.id
        return vals

    def _vals_linea_factura(self, linea):
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
        tipo_ruc = self.env.ref('local_py.tipo_identificacion_ruc', raise_if_not_found=False)
        contexto = {
            'default_name': self.emisor_nombre,
            'default_company_type': 'company',
            'default_is_company': True,
            'default_vat': self.emisor_ruc,
            'default_email': self.emisor_email,
            'default_phone': self.emisor_telefono,
            'default_street': self.emisor_direccion,
            'default_city': self.emisor_ciudad,
        }
        if tipo_ruc:
            contexto['default_l10n_py_tipo_identificacion_fiscal_id'] = tipo_ruc.id
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
        self.write({'state': 'verificado'})
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
        for doc in self:
            if doc.state != 'verificado':
                raise UserError(_('Solo se puede confirmar una recepción Verificada.'))
        self._exigir_sin_bloqueos()
        Move = self.env['account.move'].with_context(mail_create_nolog=True)
        for doc in self:
            move = Move.with_company(doc.company_id).create(doc._vals_factura())
            doc.write({'move_id': move.id, 'state': 'confirmado'})
            doc._copiar_xml_a(move)
            doc._registrar_equivalencias()
            doc._post_confirmar(move)
            doc.message_post(body=_('Factura de proveedor %s generada en borrador.', move.display_name))
            move.message_post(body=_('Generada desde la factura electrónica recibida %s.', doc.name))
        return True

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

    def action_cancelar(self):
        for doc in self:
            if doc.state == 'confirmado':
                raise UserError(_(
                    'La recepción está confirmada. Para anularla, elimine o cancele la factura '
                    'de proveedor generada: la recepción vuelve sola a Cargado.'))
        self.write({'state': 'cancelado'})
        return True

    def action_reabrir(self):
        for doc in self:
            if doc.state != 'cancelado':
                raise UserError(_('Solo se puede reabrir una recepción Cancelada.'))
        self.write({'state': 'cargado', 'control_hecho': False})
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
        for doc in self.filtered(lambda d: d.state == 'confirmado'):
            doc.write({'state': 'cargado', 'move_id': False, 'control_hecho': False})
            doc.message_post(body=_(
                'La factura de proveedor generada se eliminó o canceló; la recepción volvió a Cargado.'))

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    def unlink(self):
        for doc in self:
            if doc.state not in ('cargado', 'cancelado') or doc.move_id:
                raise UserError(_(
                    'Solo se pueden eliminar recepciones Cargadas o Canceladas sin factura generada.'))
        adjuntos = self.mapped('xml_attachment_id')
        resultado = super().unlink()
        adjuntos.unlink()
        return resultado
