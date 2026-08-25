# -*- coding: utf-8 -*-

from odoo import api, models


class AccountMove(models.Model):
    _inherit = 'account.move'

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

    def _post(self, soft=True):
        """Al confirmar Factura/Nota de Crédito/Nota de Débito de Cliente
        con un Tipo Fiscal electrónico, crea automáticamente su Documento
        Electrónico (en Borrador — la generación del XML/CDC es una acción
        aparte, no ocurre acá). No genera nada para comprobantes no
        electrónicos ni para los que ya tengan uno creado."""
        posted = super()._post(soft=soft)
        electronicos = posted.filtered(
            lambda m: m.move_type in ('out_invoice', 'out_refund')
            and m.local_py_tipo_fiscal_id.fe_py_es_electronico
        )
        if electronicos:
            ya_tienen = self.env['fe_py.documento_electronico'].sudo().search([
                ('move_id', 'in', electronicos.ids)
            ]).move_id
            faltantes = electronicos - ya_tienen
            for move in faltantes:
                self.env['fe_py.documento_electronico'].sudo().create({'move_id': move.id})
        return posted

