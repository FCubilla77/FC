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
            representantes = self.env['account.payment']
            for medio in wiz._get_medios_pendientes():
                pago = medio.payment_ids.filtered(lambda p: p.state in ('in_process', 'paid'))[:1]
                representantes |= pago
            wiz.pago_ids = representantes

    def _get_medios_pendientes(self):
        """Filas de Medios de este Diario que todavía necesitan que se les
        imprima/reimprima un cheque — porque nunca tuvieron uno, o porque
        el último que tuvieron fue Anulado (hay que reemplazarlo). Los
        cheques reutilizados NO pasan por acá: ya se reactivan solos al
        Confirmar la Orden de Pago, sin necesidad de volver a imprimirlos."""
        self.ensure_one()
        if not self.journal_id:
            return self.env['local_py.orden_pago.medio']
        medios = self.env['local_py.orden_pago.medio'].search([
            ('journal_id', '=', self.journal_id.id),
            ('chequera_id', '!=', False),
        ])
        pendientes = self.env['local_py.orden_pago.medio']
        for medio in medios:
            pagos = medio.payment_ids.filtered(lambda p: p.state in ('in_process', 'paid'))
            if not pagos:
                continue
            ultimo_cheque = self.env['local_py.chequera.cheque'].search(
                [('payment_id', 'in', pagos.ids)], order='id desc', limit=1
            )
            if not ultimo_cheque or ultimo_cheque.estado == 'anulado':
                pendientes |= medio
        return pendientes

    def action_imprimir(self):
        self.ensure_one()
        if not self.chequera_id:
            raise UserError('El Diario "%s" no tiene una Chequera Activa.' % self.journal_id.name)
        medios = self._get_medios_pendientes()
        if not medios:
            raise UserError('No hay cheques pendientes de imprimir para este Diario.')

        Cheque = self.env['local_py.chequera.cheque']
        cheques = self.env['local_py.chequera.cheque']
        for medio in medios.sorted('id'):
            pago = medio.payment_ids.filtered(lambda p: p.state in ('in_process', 'paid'))[:1]
            if not pago:
                continue

            numero = self.chequera_id._asignar_siguiente_numero()
            cheque = Cheque.create({
                'chequera_id': self.chequera_id.id,
                'numero': numero,
                'estado': 'emitido',
                'fecha_emision': pago.date,
                'payment_id': pago.id,
                'orden_pago_medio_id': medio.id,
            })
            cheques |= cheque
            medio.nro_documento = str(numero)

            # Si el cheque se repartió en más de un Pago, ya están agrupados
            # en un Lote de Pago — se le pone el número real del cheque como
            # nombre, para reconocerlo de un vistazo al conciliar el banco.
            # (Si "Lotes de Pago" no está habilitado en Ajustes, el campo ni
            # siquiera existe — se omite este paso sin afectar la impresión.)
            if 'batch_payment_id' in self.env['account.payment']._fields:
                lote = medio.payment_ids.mapped('batch_payment_id')
                if lote:
                    lote[:1].name = 'Cheque %s' % numero

        report_action = self.env.ref('local_py.action_report_impresion_cheques')
        return report_action.report_action(cheques, config=False)
