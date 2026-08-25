# -*- coding: utf-8 -*-

from odoo import api, exceptions, fields, models


class FePyDocumentoElectronicoLog(models.Model):
    _name = 'fe_py.documento_electronico.log'
    _description = 'Historial de Operaciones Electrónicas (SIFEN)'
    _order = 'fecha desc, id desc'

    # ------------------------------------------------------------------
    # Origen: cada fila de log pertenece a un Documento Electrónico
    # (envío/firma/consulta de una Factura, NC o ND) o a un Evento
    # (Cancelación/Inutilización) — nunca a ambos a la vez.
    # ------------------------------------------------------------------
    documento_id = fields.Many2one(
        'fe_py.documento_electronico', string='Documento Electrónico',
        ondelete='cascade', index=True,
    )
    evento_id = fields.Many2one(
        'fe_py.evento', string='Evento',
        ondelete='cascade', index=True,
    )

    # Campos derivados, para poder filtrar y hacer clic directo desde la
    # ventana global de log (ver requerimiento de "acceder a la operación
    # misma" con un clic) sin tener que pasar primero por el Documento
    # Electrónico. En Inutilización no hay Comprobante asociado (es un
    # rango de numeración), por eso move_id puede quedar vacío.
    move_id = fields.Many2one(
        'account.move', string='Comprobante',
        compute='_compute_datos_relacionados', store=True, index=True,
    )
    journal_id = fields.Many2one(
        'account.journal', string='Diario',
        compute='_compute_datos_relacionados', store=True, index=True,
    )
    partner_id = fields.Many2one(
        'res.partner', string='Cliente',
        compute='_compute_datos_relacionados', store=True, index=True,
    )
    company_id = fields.Many2one(
        'res.company', string='Compañía',
        compute='_compute_datos_relacionados', store=True, index=True,
    )

    fecha = fields.Datetime(
        string='Fecha', required=True, default=fields.Datetime.now, index=True,
    )
    usuario_id = fields.Many2one(
        'res.users', string='Usuario', default=lambda self: self.env.user,
    )

    tipo_operacion = fields.Selection(
        string='Tipo de Operación',
        selection=[
            ('generacion_xml', 'Generación de XML'),
            ('firma', 'Firma Electrónica'),
            ('envio_individual', 'Envío Individual (WS Sincrónico)'),
            ('envio_lote', 'Envío por Lote (WS Asincrónico)'),
            ('consulta_lote', 'Consulta de Lote'),
            ('consulta_cdc', 'Consulta por CDC'),
            ('evento_cancelacion', 'Evento: Cancelación'),
            ('evento_inutilizacion', 'Evento: Inutilización'),
            ('reenvio', 'Reenvío'),
        ],
        required=True, index=True,
    )
    resultado = fields.Selection(
        string='Resultado',
        selection=[('exito', 'Éxito'), ('error', 'Error'), ('advertencia', 'Advertencia')],
        required=True, index=True,
    )
    codigo_resultado = fields.Char(string='Código de Resultado')
    mensaje_resultado = fields.Text(string='Mensaje de Resultado')

    # Payloads técnicos completos (XML/JSON de request y response), para
    # poder auditar exactamente qué se envió y qué respondió SIFEN (o el
    # Simulador) en cada operación puntual.
    request_payload = fields.Text(string='Request')
    response_payload = fields.Text(string='Response')

    simulado = fields.Boolean(
        string='Simulado',
        help='Marca si esta operación se generó con el Simulador SIFEN '
             '(Ambiente = Simulado), en vez de una respuesta real de la DNIT.',
    )

    @api.depends(
        'documento_id', 'documento_id.move_id',
        'evento_id', 'evento_id.documento_id', 'evento_id.documento_id.move_id',
        'evento_id.journal_id',
    )
    def _compute_datos_relacionados(self):
        for log in self:
            move = False
            journal = False
            company = False
            if log.documento_id:
                move = log.documento_id.move_id
            elif log.evento_id and log.evento_id.documento_id:
                move = log.evento_id.documento_id.move_id

            if move:
                journal = move.journal_id
                company = move.company_id
            elif log.evento_id:
                journal = log.evento_id.journal_id
                company = log.evento_id.company_id

            log.move_id = move
            log.journal_id = journal
            log.partner_id = move.partner_id if move else False
            log.company_id = company or self.env.company

    # ------------------------------------------------------------------
    # Trazabilidad fiscal: el historial de operaciones no se edita ni se
    # borra una vez creado (mismo criterio que ya usa local_py para los
    # asientos generados por Ajuste de Inventario Físico).
    # ------------------------------------------------------------------
    def write(self, vals):
        raise exceptions.UserError(
            'El Historial de Operaciones Electrónicas no puede modificarse: '
            'es un registro de auditoría fiscal.'
        )

    def unlink(self):
        raise exceptions.UserError(
            'El Historial de Operaciones Electrónicas no puede eliminarse: '
            'es un registro de auditoría fiscal.'
        )

    def action_ver_operacion(self):
        """Abre la operación de origen (el comprobante, o el evento si no
        hay comprobante — caso de Inutilización). Es la acción detrás del
        "clic para acceder a la operación misma" pedido en el
        requerimiento de la ventana global de log."""
        self.ensure_one()
        if self.move_id:
            return {
                'type': 'ir.actions.act_window',
                'name': self.move_id.display_name,
                'res_model': 'account.move',
                'res_id': self.move_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        if self.evento_id:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Evento SIFEN',
                'res_model': 'fe_py.evento',
                'res_id': self.evento_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        raise exceptions.UserError('Esta operación no tiene un comprobante ni un evento asociado.')
