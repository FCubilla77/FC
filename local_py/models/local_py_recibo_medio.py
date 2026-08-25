# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LocalPyReciboMedio(models.Model):
    _name = 'local_py.recibo.medio'
    _description = 'Medio de Cobro en un Recibo'

    recibo_id = fields.Many2one('local_py.recibo', string='Recibo', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='recibo_id.company_id', string='Compañía')
    currency_id = fields.Many2one(related='recibo_id.currency_id', string='Moneda')
    recibo_partner_id = fields.Many2one(related='recibo_id.partner_id', string='Cliente (para filtro)')

    tipo = fields.Selection(
        [
            ('efectivo', 'Efectivo'),
            ('transferencia', 'Transferencia'),
            ('cheque', 'Cheque'),
            ('retencion', 'Retención'),
            ('saldo_favor', 'Saldo a Favor'),
        ],
        string='Tipo', required=True, default='efectivo',
    )
    importe = fields.Monetary(string='Importe', currency_field='currency_id')

    # Efectivo / Transferencia
    journal_id = fields.Many2one(
        'account.journal', string='Diario',
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
        help='Solo para Efectivo y Transferencia.',
    )

    # Cheque de Cliente — datos de carga, el registro real (local_py.cheque_cliente)
    # se genera recién al Confirmar el Recibo.
    cheque_numero = fields.Char(string='Número de Cheque')
    cheque_banco_id = fields.Many2one('res.bank', string='Banco (Cheque)')
    cheque_tipo = fields.Selection(
        [('al_dia', 'Al día'), ('diferido', 'Diferido')], string='Tipo de Cheque', default='al_dia',
    )
    cheque_fecha_emision = fields.Date(string='Fecha de Emisión (Cheque)')
    cheque_fecha_vencimiento = fields.Date(string='Fecha de Vencimiento (Cheque)')
    cheque_cliente_id = fields.Many2one(
        'local_py.cheque_cliente', string='Cheque generado', readonly=True, copy=False,
    )

    # Retención Recibida
    recibo_factura_id = fields.Many2one(
        'local_py.recibo.factura', string='Factura de la Retención',
        help='A qué Factura de este mismo Recibo corresponde esta porción retenida — '
             'necesario para el futuro emparejamiento contra el archivo de Marangatu.',
    )
    retencion_numero_dni = fields.Char(
        string='Nro. Comprobante DNIT', copy=False,
        help='Se completa recién cuando se confirma contra el archivo de Marangatu (o '
             'a mano) — mientras tanto, el monto queda en la Cuenta "Retenido a '
             'Confirmar".',
    )
    retencion_fecha_confirmacion = fields.Date(string='Fecha de Confirmación DNIT', copy=False)
    retencion_estado = fields.Selection(
        [('pendiente', 'Pendiente'), ('confirmada', 'Confirmada')],
        string='Estado Retención', default='pendiente', copy=False,
    )
    retencion_move_id = fields.Many2one(
        'account.move', string='Asiento de Retención (a Confirmar)', readonly=True, copy=False,
    )
    retencion_reclasificacion_move_id = fields.Many2one(
        'account.move', string='Asiento de Reclasificación', readonly=True, copy=False,
        help='Asiento que mueve el monto de "Retenido a Confirmar" a "Retenciones '
             'Recibidas", generado al confirmar contra la DNIT (o a mano).',
    )

    # Saldo a Favor
    saldo_favor_payment_id = fields.Many2one(
        'account.payment', string='Saldo a Favor',
        domain="[('l10n_py_es_saldo_favor', '=', True), ('partner_id', '=', recibo_partner_id),"
               " ('l10n_py_saldo_favor_disponible', '>', 0), ('currency_id', '=', currency_id)]",
        help='Un Cobro de un Recibo anterior que quedó con un sobrante sin conciliar '
             '(Saldo a Favor de este mismo Cliente) — se puede reutilizar acá, total o '
             'parcialmente, en vez de generar un Cobro nuevo.',
    )
    saldo_favor_disponible = fields.Monetary(
        related='saldo_favor_payment_id.l10n_py_saldo_favor_disponible', string='Disponible',
        currency_field='currency_id',
    )

    payment_ids = fields.One2many(
        'account.payment', 'l10n_py_recibo_medio_id', string='Cobros',
    )
    documentos_relacionados = fields.Char(
        string='Doc. relacionados', compute='_compute_documentos_relacionados',
    )

    @api.depends('payment_ids', 'tipo', 'cheque_cliente_id', 'saldo_favor_payment_id', 'retencion_move_id')
    def _compute_documentos_relacionados(self):
        for medio in self:
            if medio.tipo == 'saldo_favor':
                medio.documentos_relacionados = medio.saldo_favor_payment_id.name or ''
            elif medio.tipo == 'retencion':
                medio.documentos_relacionados = medio.retencion_move_id.name or ''
            elif medio.tipo == 'cheque' and medio.cheque_cliente_id:
                medio.documentos_relacionados = medio.cheque_cliente_id.display_name
            else:
                medio.documentos_relacionados = ', '.join(medio.payment_ids.mapped('name'))

    @api.constrains('importe')
    def _check_importe(self):
        for medio in self:
            if medio.importe <= 0:
                raise ValidationError('El importe de cada Medio de Cobro debe ser mayor a cero.')

    @api.constrains('importe', 'saldo_favor_payment_id')
    def _check_saldo_favor_alcanza(self):
        for medio in self:
            if medio.saldo_favor_payment_id and medio.importe > medio.saldo_favor_payment_id.l10n_py_saldo_favor_disponible:
                raise ValidationError(
                    'El Importe cargado (%s) supera el Saldo a Favor disponible de ese Cobro (%s).'
                    % (medio.importe, medio.saldo_favor_payment_id.l10n_py_saldo_favor_disponible)
                )

    @api.constrains('tipo', 'journal_id', 'cheque_numero', 'cheque_banco_id', 'saldo_favor_payment_id')
    def _check_datos_segun_tipo(self):
        for medio in self:
            if medio.tipo in ('efectivo', 'transferencia') and not medio.journal_id:
                raise ValidationError('Elija el Diario para esta fila de %s.' % dict(
                    medio._fields['tipo'].selection).get(medio.tipo))
            if medio.tipo == 'cheque' and not (medio.cheque_numero and medio.cheque_banco_id):
                raise ValidationError('Complete el Número de Cheque y el Banco para esta fila.')
            if medio.tipo == 'saldo_favor' and not medio.saldo_favor_payment_id:
                raise ValidationError('Elija qué Saldo a Favor usar en esta fila.')

    @api.onchange('saldo_favor_payment_id')
    def _onchange_saldo_favor_payment_id(self):
        for medio in self:
            if medio.saldo_favor_payment_id:
                medio.importe = medio.saldo_favor_payment_id.l10n_py_saldo_favor_disponible

    @api.onchange('tipo')
    def _onchange_tipo(self):
        for medio in self:
            medio.journal_id = False
            medio.cheque_numero = False
            medio.cheque_banco_id = False
            medio.saldo_favor_payment_id = False
