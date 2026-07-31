# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LocalPyOrdenPagoMedio(models.Model):
    _name = 'local_py.orden_pago.medio'
    _description = 'Medio de Pago de una Orden de Pago'

    orden_pago_id = fields.Many2one(
        'local_py.orden_pago', string='Orden de Pago', required=True, ondelete='cascade',
    )
    journal_id = fields.Many2one(
        'account.journal', string='Diario', required=True,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(related='orden_pago_id.company_id')
    importe = fields.Monetary(string='Importe', currency_field='currency_id')
    currency_id = fields.Many2one(related='orden_pago_id.currency_id')

    # Datos de referencia — hoy son solo texto/fecha libres; más adelante se
    # van a vincular a los modelos reales de Chequera y Retención.
    fecha_emision = fields.Date(string='Fecha Emisión')
    fecha_vencimiento = fields.Date(string='Fecha Venc.')
    nro_documento = fields.Char(string='Nro. Documento')
    banco = fields.Char(string='Banco')
    chequera = fields.Char(string='Chequera')
    cuenta_banco = fields.Char(string='Cuenta Banco')

    payment_id = fields.Many2one(
        'account.payment', string='Pago', readonly=True, copy=False,
        help='Pago generado por esta fila al Confirmar la Orden de Pago — cada fila de Medios '
             'genera siempre su propio pago, sin consolidar con otras filas.',
    )

    @api.constrains('importe')
    def _check_importe(self):
        for medio in self:
            if medio.importe <= 0:
                raise ValidationError('El importe de cada Medio de Pago debe ser mayor a cero.')
