# -*- coding: utf-8 -*-

from odoo import api, exceptions, fields, models


class FePyEvento(models.Model):
    _name = 'fe_py.evento'
    _description = 'Evento SIFEN (Cancelación / Inutilización)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company,
    )
    tipo_evento = fields.Selection(
        string='Tipo de Evento',
        selection=[('cancelacion', 'Cancelación'), ('inutilizacion', 'Inutilización')],
        required=True, tracking=True,
    )

    # -- Cancelación: se hace sobre un CDC puntual, ya Aprobado ----------
    documento_id = fields.Many2one(
        'fe_py.documento_electronico', string='Documento Electrónico',
        copy=False,
        help='Documento a cancelar (debe estar Aprobado). Solo aplica a '
             'eventos de tipo Cancelación.',
    )
    move_id = fields.Many2one(
        'account.move', string='Comprobante',
        related='documento_id.move_id', store=True, readonly=True,
    )

    # -- Inutilización: se hace sobre un rango de numeración no usado ----
    journal_id = fields.Many2one(
        'account.journal', string='Diario',
        domain="[('type', '=', 'sale'), ('local_py_tipo_fiscal_id.fe_py_es_electronico', '=', True)]",
        help='Diario (Punto de Expedición) del rango a inutilizar. Solo '
             'aplica a eventos de tipo Inutilización — solo se ofrecen '
             'diarios cuyo Tipo Fiscal es electrónico.',
    )
    tipo_fiscal_id = fields.Many2one(
        'local_py.tipo_fiscal', string='Tipo Fiscal', readonly=True,
        help='Tipo de comprobante del rango a inutilizar. Se completa solo '
             'al elegir el Diario (no editable a mano, para que no pueda '
             'quedar desincronizado del Diario elegido). Solo aplica a '
             'eventos de tipo Inutilización.',
    )
    nro_documento_desde = fields.Char(
        string='Nro. Documento Desde', size=15, placeholder='000-000-0000000',
    )
    nro_documento_hasta = fields.Char(
        string='Nro. Documento Hasta', size=15, placeholder='000-000-0000000',
    )

    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        for evento in self:
            evento.tipo_fiscal_id = evento.journal_id.local_py_tipo_fiscal_id

    motivo = fields.Text(string='Motivo', required=True)

    estado = fields.Selection(
        string='Estado',
        selection=[
            ('borrador', 'Borrador'),
            ('enviado', 'Enviado'),
            ('aprobado', 'Aprobado'),
            ('rechazado', 'Rechazado'),
        ],
        default='borrador', copy=False, tracking=True, index=True,
    )
    fecha_envio = fields.Datetime(string='Fecha de Envío', copy=False)
    fecha_respuesta = fields.Datetime(string='Fecha de Respuesta', copy=False)
    codigo_respuesta = fields.Char(string='Código de Respuesta', copy=False)
    mensaje_respuesta = fields.Text(string='Mensaje de Respuesta', copy=False)

    log_ids = fields.One2many(
        'fe_py.documento_electronico.log', 'evento_id', string='Historial',
    )

    @api.constrains('tipo_evento', 'documento_id', 'journal_id', 'tipo_fiscal_id',
                     'nro_documento_desde', 'nro_documento_hasta')
    def _check_campos_segun_tipo_evento(self):
        for evento in self:
            if evento.tipo_evento == 'cancelacion' and not evento.documento_id:
                raise exceptions.ValidationError(
                    'Un evento de Cancelación necesita indicar el Documento Electrónico a cancelar.'
                )
            if evento.tipo_evento == 'inutilizacion' and not (
                evento.journal_id and evento.tipo_fiscal_id
                and evento.nro_documento_desde and evento.nro_documento_hasta
            ):
                raise exceptions.ValidationError(
                    'Un evento de Inutilización necesita Diario, Tipo Fiscal, '
                    'Nro. Documento Desde y Nro. Documento Hasta.'
                )

    def unlink(self):
        raise exceptions.UserError(
            'Un Evento SIFEN no puede eliminarse: es un registro de auditoría fiscal. '
            'Si fue cargado por error y todavía está en Borrador, puede dejarse sin usar.'
        )
