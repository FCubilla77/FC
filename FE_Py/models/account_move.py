# -*- coding: utf-8 -*-
import logging

from odoo import api, exceptions, fields, models

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
    fe_py_simular_resultado = fields.Selection(related='fe_py_documento_id.simular_resultado', string='Resultado a Simular', readonly=False)
    fe_py_simular_codigo_rechazo = fields.Char(related='fe_py_documento_id.simular_codigo_rechazo', string='Código a Simular (Rechazo)', readonly=False)
    fe_py_simular_mensaje_rechazo = fields.Char(related='fe_py_documento_id.simular_mensaje_rechazo', string='Mensaje a Simular (Rechazo)', readonly=False)

    # Campo PROPIO (no related) — a diferencia de los de arriba, este tiene
    # que poder completarse ANTES de Confirmar (en Borrador), momento en el
    # que el Documento Electrónico todavía no existe (se crea recién en
    # _post). Se copia hacia fe_py.documento_electronico.motivo_emision
    # (related, de solo lectura desde ese lado) una vez creado.
    fe_py_motivo_emision = fields.Selection(
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
        copy=False,
        help='Obligatorio para Nota de Crédito/Débito Electrónica — se '
             'exige al Confirmar, no recién al generar el XML.',
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
        """Devuelve la lista de datos que faltan para poder generar el DE
        de este comprobante (vacía si está todo completo). Se usa tanto al
        Confirmar (bloquea la Confirmación si falta algo) como al Generar/
        Regenerar XML (por si algo cambió después de confirmar) — una sola
        fuente de verdad para no repetir la misma lista en dos lugares."""
        self.ensure_one()
        company = self.company_id
        partner = self.partner_id
        faltantes = []

        if not company.vat:
            faltantes.append('RUC de la Compañía')
        if not company.fe_py_actividad_economica_codigo:
            faltantes.append('Código de Actividad Económica (Compañía)')
        if not company.street:
            faltantes.append('Dirección de la Compañía')
        if not company.state_id:
            faltantes.append('Departamento de la Compañía')
        if not company.city_id:
            faltantes.append('Ciudad de la Compañía')
        if not self.journal_id.l10n_py_inicio_vigencia_timbrado:
            faltantes.append('Inicio de Vigencia del Timbrado (Diario)')

        if not partner.vat:
            faltantes.append(
                'RUC del Cliente (receptor sin RUC todavía no está soportado en esta fase)'
            )
        if not partner.country_id:
            faltantes.append('País del Cliente')
        if not partner.street:
            faltantes.append('Dirección del Cliente')
        if not partner.state_id:
            faltantes.append('Departamento del Cliente')
        if not partner.city_id:
            faltantes.append('Ciudad del Cliente')

        if self.fe_py_es_nc_nd and not self.fe_py_motivo_emision:
            faltantes.append('Motivo de Emisión')
        if self.move_type == 'out_refund' and not self.reversed_entry_id:
            faltantes.append('Comprobante Asociado')
        if self.move_type == 'out_refund' and self.reversed_entry_id:
            doc_asociado = self.reversed_entry_id.fe_py_documento_id
            if not doc_asociado or not doc_asociado.cdc:
                faltantes.append(
                    'CDC de la Factura Electrónica asociada (todavía no fue generado)'
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
                'No se puede Confirmar: faltan datos para Facturación Electrónica.\n\n'
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
                'motivo_emision': move.fe_py_motivo_emision,
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

