# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class LocalPyChequeCliente(models.Model):
    _name = 'local_py.cheque_cliente'
    _description = 'Cheque de Cliente'
    _order = 'id desc'

    name = fields.Char(string='Número de Cheque', required=True)
    bank_id = fields.Many2one('res.bank', string='Banco', required=True)
    tipo = fields.Selection(
        [('al_dia', 'Al día'), ('diferido', 'Diferido')], string='Tipo', required=True, default='al_dia',
    )
    fecha_emision = fields.Date(string='Fecha de Emisión')
    fecha_vencimiento = fields.Date(string='Fecha de Vencimiento')
    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency', string='Moneda', required=True, default=lambda self: self.env.company.currency_id,
    )
    importe = fields.Monetary(string='Importe', currency_field='currency_id')
    partner_id = fields.Many2one('res.partner', string='Cliente')
    recibo_medio_id = fields.Many2one(
        'local_py.recibo.medio', string='Medio de Cobro origen', readonly=True, copy=False,
    )
    recibo_id = fields.Many2one(related='recibo_medio_id.recibo_id', string='Recibo')

    estado = fields.Selection(
        [
            ('en_cartera', 'En Cartera'),
            ('rechazado', 'Rechazado'),
            ('depositado', 'Depositado'),
            ('negociado', 'Negociado'),
            ('canjeado', 'Canjeado'),
            ('anulado', 'Anulado'),
        ],
        string='Estado', default='en_cartera', required=True, copy=False,
        help='Depositado, Negociado y Canjeado quedan previstos en el dato para '
             'cuando se construya el módulo de Depósito Bancario y los procesos de '
             'Negociación/Canje — todavía no tienen ninguna funcionalidad propia.',
    )
    fecha_rechazo = fields.Date(string='Fecha de Rechazo', readonly=True, copy=False)
    motivo_rechazo = fields.Char(string='Motivo de Rechazo', copy=False)
    rechazo_move_id = fields.Many2one(
        'account.move', string='Asiento de Rechazo', readonly=True, copy=False,
        help='Asiento que mueve el importe de "Cheques en Cartera" a "Cheques '
             'Rechazados" — se revierte solo si se usa "Deshacer Rechazo".',
    )

    @api.constrains('name', 'bank_id', 'tipo', 'company_id', 'estado')
    def _check_duplicado(self):
        """Mismo Número + Banco + Tipo no puede repetirse entre Cheques que
        no estén Anulados — a propósito, sin cruzar por Cliente (no
        debería darse esa combinación en la práctica)."""
        for cheque in self:
            if cheque.estado == 'anulado' or not cheque.name or not cheque.bank_id:
                continue
            duplicado = self.search([
                ('id', '!=', cheque.id),
                ('name', '=', cheque.name),
                ('bank_id', '=', cheque.bank_id.id),
                ('tipo', '=', cheque.tipo),
                ('company_id', '=', cheque.company_id.id),
                ('estado', '!=', 'anulado'),
            ], limit=1)
            if duplicado:
                raise ValidationError(
                    'Ya existe un Cheque de Cliente con el mismo Número, Banco y Tipo, sin '
                    'estar Anulado (Recibo %s).' % (duplicado.recibo_id.name or '')
                )

    def action_abrir_wizard_rechazar(self):
        self.ensure_one()
        if self.estado != 'en_cartera':
            raise UserError('Solo se puede Rechazar un Cheque que esté "En Cartera".')
        return {
            'name': 'Rechazar Cheque',
            'type': 'ir.actions.act_window',
            'res_model': 'local_py.cheque_cliente.rechazar_wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_cheque_id': self.id},
        }

    def action_rechazar(self, motivo, fecha=None):
        """Mueve el importe de "Cheques en Cartera" a "Cheques Rechazados"
        — no reabre la Factura ni anula el Recibo: el Cliente ya pagó
        con un instrumento válido, el rechazo solo cambia dónde está
        guardado ese valor mientras se resuelve (Canje, todavía no
        desarrollado)."""
        self.ensure_one()
        if self.estado != 'en_cartera':
            raise UserError('Solo se puede Rechazar un Cheque que esté "En Cartera".')
        if not motivo:
            raise UserError('Indique el Motivo de Rechazo.')
        config = self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', self.company_id.id)], limit=1,
        )
        if not config or not config.l10n_py_diario_cheque_cliente_id or not config.l10n_py_cuenta_cheques_rechazados_id:
            raise UserError(
                'Falta configurar el Diario de Cheques de Clientes y/o la Cuenta '
                '"Cheques Rechazados" en Configuraciones Localización Py.'
            )
        diario = config.l10n_py_diario_cheque_cliente_id
        cuenta_cartera = diario.default_account_id
        cuenta_rechazados = config.l10n_py_cuenta_cheques_rechazados_id
        if not cuenta_cartera:
            raise UserError(
                'El Diario de Cheques de Clientes ("%s") no tiene una Cuenta configurada '
                '(Contabilidad > Diarios).' % diario.name
            )
        fecha = fecha or fields.Date.context_today(self)
        concepto = 'Rechazo Cheque Cliente %s - %s' % (self.name, self.partner_id.display_name)
        move = self.env['account.move'].create({
            'journal_id': diario.id,
            'date': fecha,
            'ref': concepto,
            'line_ids': [
                (0, 0, {
                    'name': concepto, 'account_id': cuenta_rechazados.id, 'partner_id': self.partner_id.id,
                    'debit': self.importe, 'credit': 0.0,
                }),
                (0, 0, {
                    'name': concepto, 'account_id': cuenta_cartera.id, 'partner_id': self.partner_id.id,
                    'debit': 0.0, 'credit': self.importe,
                }),
            ],
        })
        move.action_post()
        self.write({
            'estado': 'rechazado', 'fecha_rechazo': fecha, 'motivo_rechazo': motivo, 'rechazo_move_id': move.id,
        })

    def action_deshacer_rechazo(self):
        self.ensure_one()
        if self.estado != 'rechazado':
            raise UserError('Solo se puede deshacer el Rechazo de un Cheque que esté "Rechazado".')
        if self.rechazo_move_id:
            self.rechazo_move_id.button_draft()
            self.rechazo_move_id.unlink()
        self.write({
            'estado': 'en_cartera', 'fecha_rechazo': False, 'motivo_rechazo': False, 'rechazo_move_id': False,
        })
