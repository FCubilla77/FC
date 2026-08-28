# -*- coding: utf-8 -*-

from odoo import api, fields, models, exceptions


class FePyDocumentoElectronico(models.Model):
    _name = 'fe_py.documento_electronico'
    _description = 'Documento Electrónico (SIFEN)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    @api.depends('move_id', 'move_id.l10n_py_nro_documento', 'move_id.name', 'partner_id')
    def _compute_display_name(self):
        for doc in self:
            nro = doc.move_id.l10n_py_nro_documento or doc.move_id.name or str(doc.id)
            cliente = doc.partner_id.name or ''
            comprobante = doc.move_id.name or ''
            doc.display_name = '%s - %s (%s)' % (nro, cliente, comprobante)

    # ------------------------------------------------------------------
    # Relación 1:1 con el comprobante contable. Aplica a Factura Cliente,
    # Nota de Crédito Cliente y Nota de Débito Cliente (estas dos últimas
    # con move_type distinto/igual según corresponda, filtradas por
    # local_py_tipo_fiscal_id en la capa de negocio, no acá).
    # ------------------------------------------------------------------
    move_id = fields.Many2one(
        'account.move', string='Comprobante', required=True,
        ondelete='cascade', copy=False, index=True,
    )
    company_id = fields.Many2one(
        related='move_id.company_id', string='Compañía', store=True, readonly=True,
    )
    partner_id = fields.Many2one(
        related='move_id.partner_id', string='Cliente', store=True, readonly=True,
    )
    tipo_fiscal_id = fields.Many2one(
        related='move_id.local_py_tipo_fiscal_id', string='Tipo Fiscal',
        store=True, readonly=True,
    )
    journal_id = fields.Many2one(
        related='move_id.journal_id', string='Diario', store=True, readonly=True,
    )
    fe_py_ambiente = fields.Selection(
        related='move_id.company_id.fe_py_ambiente', string='Ambiente FE',
    )

    # ------------------------------------------------------------------
    # Estado del ciclo de vida SIFEN. El paso a cada estado lo controla la
    # lógica de negocio de las fases siguientes (generación, firma,
    # envío) — acá solo se define el campo y sus valores posibles.
    # ------------------------------------------------------------------
    estado = fields.Selection(
        string='Estado SIFEN',
        selection=[
            ('borrador', 'Borrador'),
            ('xml_generado', 'XML Generado'),
            ('firmado', 'Firmado'),
            ('enviado', 'Enviado'),
            ('aprobado', 'Aprobado'),
            ('aprobado_observacion', 'Aprobado con Observación'),
            ('rechazado', 'Rechazado'),
            ('error_comunicacion', 'Error de Comunicación'),
            ('cancelado', 'Cancelado'),
            ('inutilizado', 'Inutilizado'),
        ],
        default='borrador', copy=False, index=True, tracking=True,
    )

    # -- Identificación del Documento Electrónico ------------------------
    cdc = fields.Char(string='CDC', size=44, copy=False, index=True)
    codigo_seguridad = fields.Char(string='Código de Seguridad', size=9, copy=False)
    digito_verificador_cdc = fields.Char(string='DV del CDC', size=1, copy=False)
    tipo_emision = fields.Selection(
        string='Tipo de Emisión',
        selection=[('normal', 'Normal'), ('contingencia', 'Contingencia')],
        default='normal', copy=False,
    )
    version_formato = fields.Char(string='Versión de Formato', default='150', copy=False)

    tipo_operacion = fields.Selection(
        string='Tipo de Operación',
        selection=[('1', 'B2B'), ('2', 'B2C'), ('3', 'B2G'), ('4', 'B2F')],
        default='1',
        help='Se propone automáticamente según el Cliente (B2B si es Empresa, '
             'B2C si es Persona) — editable antes de generar el XML si '
             'corresponde otro caso (venta al Estado = B2G, servicios a '
             'personas/empresas del exterior = B2F).',
    )
    motivo_emision = fields.Selection(
        string='Motivo de Emisión',
        selection=[
            ('1', 'Devolución y Ajuste de precios'),
            ('2', 'Devolución'),
            ('3', 'Descuento'),
            ('4', 'Bonificación'),
            ('5', 'Crédito incobrable'),
            ('6', 'Recupero de costo'),
            ('7', 'Recupero de gasto'),
            ('8', 'Ajuste de precio'),
        ],
        help='Obligatorio para Nota de Crédito/Débito Electrónica — motivo '
             'de emisión exigido por SIFEN (gCamNCDE/iMotEmi).',
    )

    # -- Simulador SIFEN (Ambiente = Simulado) ---------------------------
    simular_resultado = fields.Selection(
        string='Resultado a Simular',
        selection=[
            ('aprobado', 'Aprobado'),
            ('aprobado_observacion', 'Aprobado con Observación'),
            ('rechazado', 'Rechazado'),
            ('error_comunicacion', 'Error de Comunicación'),
        ],
        default='aprobado',
        help='Solo tiene efecto cuando la Compañía tiene Ambiente = '
             'Simulado. Define qué respuesta va a generar el Simulador '
             'SIFEN interno la próxima vez que se use "Enviar" sobre este '
             'documento — permite probar todos los estados sin conexión real.',
    )
    simular_codigo_rechazo = fields.Char(
        string='Código a Simular (Rechazo)', default='0160',
        help='Solo se usa si "Resultado a Simular" = Rechazado.',
    )
    simular_mensaje_rechazo = fields.Char(
        string='Mensaje a Simular (Rechazo)', default='XML malformado',
        help='Solo se usa si "Resultado a Simular" = Rechazado.',
    )

    # -- Contenido: XML y respuesta de SIFEN ------------------------------
    xml_generado = fields.Text(string='XML Generado', copy=False)
    xml_firmado = fields.Text(string='XML Firmado', copy=False)
    xml_respuesta = fields.Text(string='XML de Respuesta SIFEN', copy=False)
    codigo_respuesta = fields.Char(string='Código de Respuesta', copy=False)
    mensaje_respuesta = fields.Text(string='Mensaje de Respuesta', copy=False)

    # -- KuDE (representación gráfica) ------------------------------------
    kude_pdf = fields.Binary(string='KuDE (PDF)', copy=False, attachment=True)
    kude_pdf_filename = fields.Char(string='Nombre archivo KuDE', copy=False)
    qr_url = fields.Char(string='URL del QR', copy=False)

    # -- Trazabilidad de fechas e intentos ---------------------------------
    fecha_generacion = fields.Datetime(string='Fecha de Generación', copy=False)
    fecha_envio = fields.Datetime(string='Fecha de Envío', copy=False)
    fecha_respuesta = fields.Datetime(string='Fecha de Respuesta', copy=False)
    intentos = fields.Integer(string='Intentos de Envío', default=0, copy=False)
    simulado = fields.Boolean(
        string='Generado en Modo Simulado',
        help='Indica si el último envío se procesó con el Simulador SIFEN '
             '(Ambiente = Simulado) en vez de una respuesta real de la DNIT.',
    )

    log_ids = fields.One2many(
        'fe_py.documento_electronico.log', 'documento_id', string='Historial de Operaciones',
    )
    evento_ids = fields.One2many(
        'fe_py.evento', 'documento_id', string='Eventos',
    )

    _move_uniq = models.Constraint(
        'unique(move_id)',
        'Ya existe un Documento Electrónico para este comprobante.',
    )

    def unlink(self):
        raise exceptions.UserError(
            'Un Documento Electrónico no puede eliminarse: es un registro de '
            'auditoría fiscal. Si el comprobante contable se anula/revierte, '
            'el Documento Electrónico debe pasar por el evento correspondiente '
            '(Cancelación/Inutilización), no borrarse.'
        )
