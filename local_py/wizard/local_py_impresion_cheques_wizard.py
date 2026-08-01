# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class LocalPyImpresionChequesWizard(models.TransientModel):
    _name = 'local_py.impresion_cheques.wizard'
    _description = 'Impresión Masiva de Cheques'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company,
    )
    journal_id = fields.Many2one(
        'account.journal', string='Diario', required=True,
        domain="[('type', '=', 'bank'), ('company_id', '=', company_id)]",
    )
    chequera_id = fields.Many2one('local_py.chequera', string='Chequera Activa', compute='_compute_chequera_id')
    siguiente_numero = fields.Integer(related='chequera_id.siguiente_numero', string='Próximo Número')
    pago_ids = fields.Many2many('account.payment', string='Cheques a imprimir', compute='_compute_pago_ids')

    @api.depends('journal_id')
    def _compute_chequera_id(self):
        for wiz in self:
            wiz.chequera_id = self.env['local_py.chequera'].search([
                ('diario_id', '=', wiz.journal_id.id), ('state', '=', 'activo'),
            ], limit=1)

    @api.depends('journal_id')
    def _compute_pago_ids(self):
        for wiz in self:
            wiz.pago_ids = wiz._get_pagos_pendientes()

    def _get_pagos_pendientes(self):
        self.ensure_one()
        if not self.journal_id:
            return self.env['account.payment']
        medios = self.env['local_py.orden_pago.medio'].search([
            ('journal_id', '=', self.journal_id.id),
            ('chequera_id', '!=', False),
        ])
        pagos = medios.mapped('payment_ids').filtered(lambda p: p.state in ('in_process', 'paid'))
        ya_impresos = self.env['local_py.chequera.cheque'].search(
            [('payment_id', 'in', pagos.ids)]
        ).mapped('payment_id')
        return (pagos - ya_impresos).sorted('id')

    def action_imprimir(self):
        self.ensure_one()
        if not self.chequera_id:
            raise UserError('El Diario "%s" no tiene una Chequera Activa.' % self.journal_id.name)
        pagos = self._get_pagos_pendientes()
        if not pagos:
            raise UserError('No hay cheques pendientes de imprimir para este Diario.')

        cheques = self.env['local_py.chequera.cheque']
        Medio = self.env['local_py.orden_pago.medio']
        for pago in pagos:
            numero = self.chequera_id._asignar_siguiente_numero()
            medio = Medio.search([('payment_ids', 'in', pago.id)], limit=1)
            cheque = self.env['local_py.chequera.cheque'].create({
                'chequera_id': self.chequera_id.id,
                'numero': numero,
                'estado': 'emitido',
                'fecha_emision': pago.date,
                'payment_id': pago.id,
                'orden_pago_medio_id': medio.id,
            })
            cheques |= cheque
            if medio:
                medio.nro_documento = str(numero)

        report_action = self.env.ref('local_py.action_report_impresion_cheques')
        return report_action.report_action(cheques, config=False)
