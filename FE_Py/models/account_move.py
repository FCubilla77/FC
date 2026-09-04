# -*- coding: utf-8 -*-
import logging

from odoo import api, exceptions, fields, models

from .res_partner import INDICADOR_PRESENCIA, TIPO_IMPUESTO

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ------------------------------------------------------------------
    # Puntero directo al Documento Electrónico (se completa una sola vez,
    # al crearlo en _post — evita tener que buscarlo cada vez que se abre
    # la factura).
    # ------------------------------------------------------------------
    fe_py_documento_id = fields.Many2one(
        'fe_py.documento_electronico', string='Documento Electrónico', copy=False, readonly=True,
    )
    fe_py_es_electronico = fields.Boolean(
        related='local_py_tipo_fiscal_id.fe_py_es_electronico', string='Es Electrónico',
    )
    fe_py_es_nc_nd = fields.Boolean(
        string='Es Nota de Crédito/Débito Electrónica', compute='_compute_fe_py_es_nc_nd',
    )
    fe_py_cdc_comprobante_asociado = fields.Char(
        string='CDC del Comprobante Asociado', compute='_compute_fe_py_cdc_comprobante_asociado',
        help='CDC de la Factura Electrónica original que esta Nota de '
             'Crédito referencia (gCamDEAsoc). Vacío si la factura '
             'original todavía no tiene su propio CDC generado.',
    )

    @api.depends('reversed_entry_id', 'reversed_entry_id.fe_py_documento_id.cdc')
    def _compute_fe_py_cdc_comprobante_asociado(self):
        for move in self:
            move.fe_py_cdc_comprobante_asociado = (
                move.reversed_entry_id.fe_py_documento_id.cdc if move.reversed_entry_id else False
            )

    @api.depends('local_py_tipo_fiscal_id')
    def _compute_fe_py_es_nc_nd(self):
        for move in self:
            move.fe_py_es_nc_nd = move.local_py_tipo_fiscal_id.name in (
                'Nota de Credito Electronica', 'Nota de Debito Electronica'
            )

    # -- Campos related, para poder mostrar todo embebido en la pestaña
    #    (Factura/NC/ND de Cliente) sin tener que navegar a otra pantalla.
    fe_py_estado = fields.Selection(related='fe_py_documento_id.estado', string='Estado FE')
    fe_py_cdc = fields.Char(related='fe_py_documento_id.cdc', string='CDC')
    fe_py_xml_generado = fields.Text(related='fe_py_documento_id.xml_generado', string='XML Generado')
    fe_py_xml_firmado = fields.Text(related='fe_py_documento_id.xml_firmado', string='XML Firmado')
    fe_py_codigo_respuesta = fields.Char(related='fe_py_documento_id.codigo_respuesta', string='Código de Respuesta')
    fe_py_mensaje_respuesta = fields.Text(related='fe_py_documento_id.mensaje_respuesta', string='Mensaje de Respuesta')
    fe_py_fecha_envio = fields.Datetime(related='fe_py_documento_id.fecha_envio', string='Fecha de Envío')
    fe_py_fecha_respuesta = fields.Datetime(related='fe_py_documento_id.fecha_respuesta', string='Fecha de Respuesta')
    fe_py_intentos = fields.Integer(related='fe_py_documento_id.intentos', string='Intentos de Envío')
    fe_py_simulado = fields.Boolean(related='fe_py_documento_id.simulado', string='Simulado')
    fe_py_email_enviado = fields.Boolean(related='fe_py_documento_id.email_enviado', string='Email Enviado')
    fe_py_kude_pdf = fields.Binary(related='fe_py_documento_id.kude_pdf', string='KuDE (PDF)')
    fe_py_kude_pdf_filename = fields.Char(related='fe_py_documento_id.kude_pdf_filename')
    fe_py_log_ids = fields.One2many(related='fe_py_documento_id.log_ids', string='Historial de Operaciones')
    fe_py_xml_final = fields.Text(related='fe_py_documento_id.xml_final', string='XML Final (documento fiscal)')
    fe_py_respuesta_sifen_raw = fields.Text(related='fe_py_documento_id.respuesta_sifen_raw', string='Respuesta SIFEN')
    fe_py_protocolo_autorizacion = fields.Char(related='fe_py_documento_id.protocolo_autorizacion', string='Protocolo de Autorización')
    fe_py_simular_resultado = fields.Selection(related='fe_py_documento_id.simular_resultado', string='Resultado a Simular', readonly=False)
    fe_py_simular_codigo_rechazo = fields.Char(related='fe_py_documento_id.simular_codigo_rechazo', string='Código a Simular (Rechazo)', readonly=False)
    fe_py_simular_mensaje_rechazo = fields.Char(related='fe_py_documento_id.simular_mensaje_rechazo', string='Mensaje a Simular (Rechazo)', readonly=False)

    # -- Ambiente y Automatización de la Compañía, para condicionar la
    #    visibilidad de botones y del bloque del Simulador en la pestaña.
    fe_py_ambiente = fields.Selection(related='company_id.fe_py_ambiente', string='Ambiente FE')
    fe_py_envio_automatico = fields.Boolean(related='company_id.fe_py_envio_automatico')
    fe_py_kude_automatico = fields.Boolean(related='company_id.fe_py_kude_automatico')
    fe_py_email_automatico = fields.Boolean(related='company_id.fe_py_email_automatico')

    # ------------------------------------------------------------------
    # Datos de la operación exigidos por SIFEN — viven en el comprobante
    # (no en el Documento Electrónico) porque tienen que poder cargarse
    # ANTES de Confirmar, momento en el que el DE todavía no existe.
    # ------------------------------------------------------------------
    fe_py_tipo_operacion_id = fields.Many2one(
        'fe_py.tipo_operacion', string='FEPy Tipo de Operación',
        compute='_compute_fe_py_tipo_operacion', store=True, readonly=False, copy=False,
        help='Se informa como iTiOpe. B2B = a empresa; B2C = a consumidor '
             'final; B2G = a Organismo del Estado; B2F = al exterior.\n\n'
             'Se propone automáticamente según el Cliente, pero queda '
             'editable. Atención: si el receptor es un Organismo del Estado '
             'registrado en SIFEN, el tipo DEBE ser B2G (Nota Técnica N° 20).',
    )
    fe_py_tipo_transaccion_id = fields.Many2one(
        'fe_py.tipo_transaccion', string='FEPy Tipo de Transacción',
        compute='_compute_fe_py_tipo_transaccion', store=True, readonly=False, copy=False,
        help='Se informa como iTipTra. Se propone según la composición de la '
             'operación (solo bienes, solo servicios o mixta), y queda '
             'editable para los demás casos de la tabla: venta de activo '
             'fijo, donación, anticipo, muestras médicas, etc.',
    )
    fe_py_indicador_presencia_id = fields.Many2one(
        'fe_py.indicador_presencia', string='FEPy Indicador de Presencia',
        compute='_compute_fe_py_datos_del_cliente', store=True, readonly=False, copy=False,
        help='Se informa como iIndPres. Se precarga desde la ficha del '
             'Cliente y queda editable por operación.',
    )
    fe_py_tipo_impuesto_id = fields.Many2one(
        'fe_py.tipo_impuesto', string='FEPy Tipo de Impuesto Afectado',
        compute='_compute_fe_py_datos_del_cliente', store=True, readonly=False, copy=False,
        help='Se informa como iTImp. Se precarga desde la ficha del Cliente.',
    )

    # -- Compras Públicas (gCompPub, E020-E029) — solo B2G ---------------
    fe_py_es_b2g = fields.Boolean(
        related='fe_py_tipo_operacion_id.es_b2g', string='Es B2G',
        help='Auxiliar para mostrar u ocultar el bloque de Compras Públicas.',
    )
    fe_py_venta_directa = fields.Boolean(
        string='FEPy Venta Directa (sin licitación)', copy=False,
        help='Tildar cuando la venta al Organismo del Estado NO pasó por un '
             'proceso de licitación. En ese caso los datos de Compras '
             'Públicas dejan de ser obligatorios.\n\n'
             'El Tipo de Operación sigue siendo B2G igual: SIFEN lo exige '
             'para todo receptor que sea un Organismo del Estado.',
    )
    fe_py_dmodcont = fields.Char(string='FEPy Modalidad del Contrato', copy=False)
    fe_py_dentcont = fields.Integer(string='FEPy Entidad Contratante', copy=False)
    fe_py_danocont = fields.Integer(string='FEPy Año del Contrato', copy=False)
    fe_py_dseccont = fields.Char(string='FEPy Secuencia / N° de Contrato', copy=False)
    fe_py_dfecodcont = fields.Date(string='FEPy Fecha del Código de Contratación', copy=False)
    fe_py_dcodcondncp = fields.Char(
        string='FEPy Código de Contratación DNCP', copy=False,
        help='Opcional (Nota Técnica N° 20). Código proveído por la DNCP.',
    )

    # -- Crédito por cuotas (gCuotas, E650-E659) -------------------------
    fe_py_condicion_credito = fields.Selection(
        related='invoice_payment_term_id.fe_py_condicion_credito',
        string='FEPy Condición del Crédito', readonly=True,
        help='Viene del Término de Pago. "Plazo" informa dPlazoCre; "Cuota" '
             'exige cargar el detalle de cada cuota.',
    )
    fe_py_cuota_ids = fields.One2many(
        'fe_py.cuota', 'move_id', string='FEPy Cuotas', copy=False,
    )

    @api.depends('partner_id', 'partner_id.fe_py_es_estado',
                 'partner_id.fe_py_es_exterior', 'partner_id.is_company')
    def _compute_fe_py_tipo_operacion(self):
        Tipo = self.env['fe_py.tipo_operacion']
        b2g = Tipo.search([('es_b2g', '=', True)], limit=1)
        b2f = Tipo.search([('es_b2f', '=', True)], limit=1)
        b2b = Tipo.search([('codigo', '=', '1')], limit=1)
        b2c = Tipo.search([('codigo', '=', '2')], limit=1)
        for move in self:
            partner = move.partner_id
            if not partner:
                continue
            if partner.fe_py_es_estado:
                move.fe_py_tipo_operacion_id = b2g
            elif partner.fe_py_es_exterior:
                move.fe_py_tipo_operacion_id = b2f
            elif partner.is_company:
                move.fe_py_tipo_operacion_id = b2b
            else:
                move.fe_py_tipo_operacion_id = b2c

    @api.depends('invoice_line_ids.product_id')
    def _compute_fe_py_tipo_transaccion(self):
        """Propone el Tipo de Transacción según la composición de la
        operación. El catálogo indica qué registro corresponde a cada
        composición, así que si la DNIT cambia los códigos, se ajusta en
        el catálogo y no acá."""
        Tipo = self.env['fe_py.tipo_transaccion']
        por_composicion = {
            comp: Tipo.search([('tipo_producto', '=', comp)], limit=1)
            for comp in ('bienes', 'servicios', 'mixto')
        }
        for move in self:
            lineas = move.invoice_line_ids.filtered(
                lambda l: l.display_type not in ('line_section', 'line_note')
            )
            tipos = set(lineas.mapped('product_id.type'))
            if tipos and tipos <= {'service'}:
                comp = 'servicios'
            elif tipos and 'service' not in tipos:
                comp = 'bienes'
            else:
                comp = 'mixto'
            move.fe_py_tipo_transaccion_id = por_composicion.get(comp)

    @api.depends('partner_id', 'partner_id.fe_py_indicador_presencia_id',
                 'partner_id.fe_py_tipo_impuesto_id')
    def _compute_fe_py_datos_del_cliente(self):
        for move in self:
            partner = move.partner_id
            move.fe_py_indicador_presencia_id = partner.fe_py_indicador_presencia_id if partner else False
            move.fe_py_tipo_impuesto_id = partner.fe_py_tipo_impuesto_id if partner else False

    fe_py_motivo_emision_id = fields.Many2one(
        'fe_py.motivo_emision', string='FEPy Motivo de Emisión', copy=False,
        help='Se informa como iMotEmi. Obligatorio en Nota de Crédito y Nota '
             'de Débito Electrónica — se exige al Confirmar.',
    )

    @api.model
    def _get_suitable_journal_ids(self, move_type, company=False):
        """local_py solo reconoce el Tipo Fiscal 'Factura Electronica' en su
        filtro de Diarios ofrecidos (era el único electrónico que existía al
        momento de escribirse ese método). Acá se agregan, sin modificar
        ningún archivo de local_py, los Diarios configurados con los nuevos
        Tipos Fiscales electrónicos de Nota de Crédito/Débito de Cliente."""
        journals = super()._get_suitable_journal_ids(move_type, company)
        if move_type in ('out_invoice', 'out_refund'):
            target_name = (
                'Nota de Debito Electronica' if move_type == 'out_invoice'
                else 'Nota de Credito Electronica'
            )
            company_id = (company or self.env.company).id
            extra = self.env['account.journal'].search([
                ('company_id', '=', company_id),
                ('type', '=', 'sale'),
                ('local_py_tipo_fiscal_id.name', '=', target_name),
            ])
            journals |= extra
        return journals

    def _fe_py_validar_datos_electronicos(self):
        """Devuelve la lista de datos y configuraciones que faltan para
        poder generar el Documento Electrónico de este comprobante.

        Se ejecuta al CONFIRMAR: si falta algo, la operación queda en
        Borrador y el mensaje indica exactamente qué completar y dónde.
        También se reutiliza al Generar/Regenerar XML, por si algo cambió
        después de confirmar — una sola fuente de verdad, para que
        validación y generación no puedan divergir.
        """
        self.ensure_one()
        company = self.company_id
        partner = self.partner_id
        journal = self.journal_id
        faltantes = []

        Config = self.env['fe_py.configuracion'].sudo()
        config = Config.search([('company_id', '=', company.id)], limit=1)
        if not config:
            return ['Configuración FEPy de la Compañía "%s" (Localización '
                    'Paraguay > Facturación Electrónica Py > Configuraciones '
                    'Generales FEPy)' % company.name]

        # -- Configuración general -------------------------------------
        if not config.fe_py_cert_path:
            faltantes.append('Certificado digital sin generar (Configuraciones Generales FEPy)')
        if not (config.fe_py_idcsc and config.fe_py_csc):
            faltantes.append('IdCSC / CSC (Configuraciones Generales FEPy)')
        if not config.fe_py_tipo_regimen_id:
            faltantes.append('FEPy Tipo de Régimen (Configuraciones Generales FEPy)')
        if not config.fe_py_actividad_economica_ids:
            faltantes.append('FEPy Actividades Económicas (Configuraciones Generales FEPy)')
        if not config.fe_py_sistema_facturacion_id:
            faltantes.append('FEPy Sistema de Facturación (Configuraciones Generales FEPy)')
        if not config.fe_py_tipo_emision_id:
            faltantes.append('FEPy Tipo de Emisión por Defecto (Configuraciones Generales FEPy)')

        # -- Emisor ----------------------------------------------------
        if not company.vat:
            faltantes.append('RUC de la Compañía (Ajustes > Empresas)')
        for campo, etiqueta in (('street', 'Dirección'), ('state_id', 'Departamento'),
                                ('city_id', 'Ciudad')):
            if not company[campo]:
                faltantes.append('%s de la Compañía (Ajustes > Empresas)' % etiqueta)

        # -- Diario y Timbrado -----------------------------------------
        if not journal.l10n_py_inicio_vigencia_timbrado:
            faltantes.append('Inicio de Vigencia del Timbrado (Diario "%s")' % journal.name)
        tipo_fiscal = journal.local_py_tipo_fiscal_id
        if not tipo_fiscal:
            faltantes.append('Tipo de Documento Fiscal del Diario "%s"' % journal.name)
        elif not tipo_fiscal.fe_py_itide:
            faltantes.append(
                'FEPy Código de Documento Electrónico del Tipo Fiscal "%s" '
                '(Localización Paraguay > Tipos de Documentos Fiscales)' % tipo_fiscal.name
            )

        # -- Receptor --------------------------------------------------
        tipo_ident = partner.l10n_py_tipo_identificacion_fiscal_id
        if not tipo_ident:
            faltantes.append('Tipo de Identificación Fiscal del Cliente "%s"' % partner.display_name)
        if not partner.vat:
            faltantes.append('RUT / Número de Identificación del Cliente "%s"' % partner.display_name)
        if tipo_ident and not partner.fe_py_es_contribuyente:
            if not tipo_ident.fe_py_itipidrec:
                faltantes.append(
                    'FEPy Código de Documento SIFEN del Tipo de Identificación '
                    '"%s" (Localización Paraguay > Tipos de Identificación Fiscal)'
                    % tipo_ident.name
                )
            elif tipo_ident.fe_py_itipidrec == '9' and not partner.fe_py_identificacion_texto:
                faltantes.append(
                    'FEPy Descripción de la Identificación del Cliente "%s" '
                    '(obligatoria cuando el tipo se informa como "Otro")' % partner.display_name
                )
        if partner.fe_py_es_contribuyente and not partner.fe_py_tipo_contribuyente_id:
            faltantes.append('FEPy Tipo de Contribuyente del Cliente "%s"' % partner.display_name)
        if not partner.country_id:
            faltantes.append('País del Cliente "%s"' % partner.display_name)
        if not partner.street:
            faltantes.append('Dirección del Cliente "%s"' % partner.display_name)
        # Departamento/Distrito/Ciudad no se informan en operaciones con el
        # exterior (regla D219, confirmada contra XML reales), así que
        # tampoco se exigen en ese caso.
        if not (self.fe_py_tipo_operacion_id and self.fe_py_tipo_operacion_id.es_b2f):
            if not partner.state_id:
                faltantes.append('Departamento del Cliente "%s"' % partner.display_name)
            if not partner.city_id:
                faltantes.append('Ciudad del Cliente "%s"' % partner.display_name)

        # -- Datos de la operación -------------------------------------
        if not self.fe_py_tipo_operacion_id:
            faltantes.append('FEPy Tipo de Operación')
        if not self.fe_py_tipo_transaccion_id:
            faltantes.append('FEPy Tipo de Transacción')
        if not self.fe_py_tipo_impuesto_id:
            faltantes.append('FEPy Tipo de Impuesto Afectado')
        if not self.fe_py_indicador_presencia_id:
            faltantes.append('FEPy Indicador de Presencia')

        # -- Moneda ----------------------------------------------------
        if not self.currency_id.fe_py_descripcion:
            faltantes.append(
                'FEPy Descripción de Moneda en "%s" (Contabilidad > Monedas)'
                % self.currency_id.name
            )
        if self.currency_id != company.currency_id and not config.fe_py_condicion_tipo_cambio_id:
            faltantes.append('FEPy Condición del Tipo de Cambio (Configuraciones Generales FEPy)')

        # -- Condición de la operación ---------------------------------
        term = self.invoice_payment_term_id
        if not term:
            faltantes.append('Términos de Pago (define si la operación es Contado o Crédito)')
        elif term.l10n_py_condicion == 'credito':
            if term.fe_py_condicion_credito == '2' and not self.fe_py_cuota_ids:
                faltantes.append(
                    'FEPy Cuotas: el Término de Pago "%s" es por Cuota, hay que '
                    'cargar el detalle de cada una' % term.name
                )

        # -- Líneas ----------------------------------------------------
        lineas = self.invoice_line_ids.filtered(
            lambda l: l.display_type not in ('line_section', 'line_note')
        )
        if not lineas:
            faltantes.append('Al menos una línea de producto o servicio')
        impuestos_sin_codigo, productos_sin_unidad = set(), set()
        for line in lineas:
            for tax in line.tax_ids:
                if not tax.fe_py_afectacion_iva_id:
                    impuestos_sin_codigo.add(tax.name)
            if line.product_id:
                if not line.product_id.fe_py_unidad_medida_id:
                    productos_sin_unidad.add(line.product_id.display_name)
            elif not config.fe_py_unidad_medida_id:
                faltantes.append(
                    'FEPy Unidad de Medida por Defecto (Configuraciones Generales '
                    'FEPy): hay líneas sin producto y no hay unidad de respaldo'
                )
        for nombre in sorted(impuestos_sin_codigo):
            faltantes.append(
                'FEPy Afectación IVA en el impuesto "%s" (Contabilidad > Impuestos)' % nombre
            )
        for nombre in sorted(productos_sin_unidad):
            faltantes.append('FEPy Unidad de Medida en el producto "%s"' % nombre)

        # -- Nota de Crédito / Débito ----------------------------------
        if self.fe_py_es_nc_nd:
            if not self.fe_py_motivo_emision_id:
                faltantes.append('FEPy Motivo de Emisión')
            if not config.fe_py_tipo_documento_asociado_id:
                faltantes.append(
                    'FEPy Tipo de Documento Asociado (Configuraciones Generales FEPy)'
                )
        if self.move_type == 'out_refund':
            if not self.reversed_entry_id:
                faltantes.append('Comprobante Asociado (factura que se está revirtiendo)')
            else:
                doc = self.reversed_entry_id.fe_py_documento_id
                if not doc or not doc.cdc:
                    faltantes.append(
                        'CDC de la Factura Electrónica asociada: la factura "%s" '
                        'todavía no generó su Documento Electrónico'
                        % self.reversed_entry_id.display_name
                    )

        # -- Compras Públicas (B2G) ------------------------------------
        if (self.fe_py_tipo_operacion_id and self.fe_py_tipo_operacion_id.es_b2g
                and not self.fe_py_venta_directa):
            for campo, etiqueta in (
                ('fe_py_dmodcont', 'Modalidad del Contrato'),
                ('fe_py_dentcont', 'Entidad Contratante'),
                ('fe_py_danocont', 'Año del Contrato'),
                ('fe_py_dseccont', 'Secuencia / N° de Contrato'),
                ('fe_py_dfecodcont', 'Fecha del Código de Contratación'),
            ):
                if not self[campo]:
                    faltantes.append(
                        'FEPy %s — Compras Públicas es obligatorio en B2G; si no '
                        'hubo licitación, tildar "Venta Directa"' % etiqueta
                    )

        return faltantes

    def _post(self, soft=True):
        """Al confirmar Factura/Nota de Crédito/Nota de Débito de Cliente
        con un Tipo Fiscal electrónico, crea automáticamente su Documento
        Electrónico (en Borrador) y lo enlaza directo en fe_py_documento_id.
        No genera nada para comprobantes no electrónicos ni para los que ya
        tengan uno creado.

        Antes de confirmar, valida TODOS los datos necesarios para
        Facturación Electrónica (RUC/dirección de Compañía y Cliente,
        Timbrado del Diario, Motivo de Emisión en NC/ND, etc.) — si falta
        algo, bloquea la Confirmación completa (no llega a postearse nada),
        en vez de dejar que la factura se confirme y recién explote más
        adelante al Generar el XML.

        Si la Compañía tiene "Generar, Firmar y Enviar Automáticamente"
        activo, además encadena esos 3 pasos (y opcionalmente KuDE/email)
        acá mismo — pero un fallo en esa cadena NUNCA hace fallar la
        Confirmación de la factura en sí: el Documento Electrónico
        simplemente queda en el estado que corresponda, listo para
        reintentar a mano."""
        a_validar = self.filtered(
            lambda m: m.move_type in ('out_invoice', 'out_refund') and m.fe_py_es_electronico
        )
        errores = []
        for move in a_validar:
            faltantes = move._fe_py_validar_datos_electronicos()
            if faltantes:
                errores.append('%s:\n  - %s' % (move.display_name, '\n  - '.join(faltantes)))
        if errores:
            raise exceptions.UserError(
                'No se puede Confirmar: faltan datos o configuraciones de '
                'Facturación Electrónica.\n\nLa operación queda en Borrador. '
                'Completá lo siguiente y volvé a Confirmar:\n\n'
                + '\n\n'.join(errores)
            )

        posted = super()._post(soft=soft)
        electronicos = posted.filtered(
            lambda m: m.move_type in ('out_invoice', 'out_refund')
            and m.local_py_tipo_fiscal_id.fe_py_es_electronico
            and not m.fe_py_documento_id
        )
        for move in electronicos:
            doc = self.env['fe_py.documento_electronico'].sudo().search(
                [('move_id', '=', move.id)], limit=1
            ) or self.env['fe_py.documento_electronico'].sudo().create({
                'move_id': move.id,
                'motivo_emision_id': move.fe_py_motivo_emision_id.id,
            })
            move.fe_py_documento_id = doc
            if move.company_id.fe_py_envio_automatico:
                move._fe_py_procesar_automatico(doc)
        return posted

    def _fe_py_procesar_automatico(self, doc):
        """Encadena Generar XML -> Firmar -> Enviar (y opcionalmente KuDE
        y email, según los interruptores de la Compañía), absorbiendo
        cualquier error para no afectar la Confirmación de la factura. Los
        propios action_* ya dejan registro en el Log de Operaciones de
        cada paso — acá solo hace falta no dejar que una excepción se
        propague hacia _post()."""
        self.ensure_one()
        company = self.company_id
        try:
            doc.action_generar_xml()
            doc.action_firmar()
            doc.action_enviar()
        except Exception:
            _logger.warning(
                "FE_Py: envío automático interrumpido para %s (comprobante "
                "confirmado igual; revisar el Log de Operaciones para el "
                "detalle del error).", self.display_name, exc_info=True,
            )
            return

        if doc.estado not in ('aprobado', 'aprobado_observacion'):
            return

        if company.fe_py_kude_automatico:
            try:
                doc.action_generar_kude()
            except Exception:
                _logger.warning(
                    "FE_Py: generación automática de KuDE falló para %s.",
                    self.display_name, exc_info=True,
                )
                return

        if company.fe_py_email_automatico:
            try:
                doc.action_enviar_email_cliente()
            except Exception:
                _logger.warning(
                    "FE_Py: envío automático de email falló para %s.",
                    self.display_name, exc_info=True,
                )


    # ------------------------------------------------------------------
    # Acciones de la pestaña "Facturación Electrónica" — delegan siempre
    # en el Documento Electrónico real, esto es solo un atajo para no
    # tener que salir de la Factura/NC/ND.
    # ------------------------------------------------------------------
    def _fe_py_get_documento(self):
        self.ensure_one()
        if not self.fe_py_documento_id:
            # Auto-reparación: si el comprobante ya está Confirmado y es
            # electrónico, pero por algún motivo (ej. el Tipo Fiscal se
            # marcó como electrónico DESPUÉS de que este comprobante ya
            # estaba confirmado) nunca se creó el Documento Electrónico,
            # se crea recién ahora en vez de bloquear al usuario pidiendo
            # algo que no puede deshacer (no tiene sentido exigir
            # "restablecer a Borrador y volver a Confirmar" solo para que
            # se dispare la creación).
            if self.state == 'posted' and self.move_type in ('out_invoice', 'out_refund') and self.fe_py_es_electronico:
                doc = self.env['fe_py.documento_electronico'].sudo().search(
                    [('move_id', '=', self.id)], limit=1
                ) or self.env['fe_py.documento_electronico'].sudo().create({'move_id': self.id})
                self.fe_py_documento_id = doc
            else:
                raise exceptions.UserError(
                    'Este comprobante todavía no tiene un Documento Electrónico '
                    'asociado (se genera automáticamente al Confirmar).'
                )
        return self.fe_py_documento_id

    def fe_py_action_generar_xml(self):
        return self._fe_py_get_documento().action_generar_xml()

    def fe_py_action_firmar(self):
        return self._fe_py_get_documento().action_firmar()

    def fe_py_action_enviar(self):
        return self._fe_py_get_documento().action_enviar()

    def fe_py_action_reenviar(self):
        """Reenvío individual "de un clic": regenera el XML (por si se
        corrigió un dato tras un Rechazo), firma y envía, encadenado — es
        lo que el requerimiento original pedía como "reescribir XML y
        reenviar de forma individual"."""
        doc = self._fe_py_get_documento()
        doc.action_generar_xml()
        doc.action_firmar()
        doc.action_enviar()
        return True

    def fe_py_action_generar_kude(self):
        return self._fe_py_get_documento().action_generar_kude()

    def fe_py_action_enviar_email(self):
        return self._fe_py_get_documento().action_enviar_email_cliente()

