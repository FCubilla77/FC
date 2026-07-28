# -*- coding: utf-8 -*-

from odoo import fields, models
from odoo.exceptions import UserError


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    l10n_py_asiento_ajuste_id = fields.Many2one(
        'account.move', string='Asiento Ajuste Inventario', readonly=True, copy=False,
        help='Asiento contable generado automáticamente al aplicar este ajuste de '
             'Inventario Físico (solo si la funcionalidad está activa en Configuraciones '
             'Localización Py). Ese asiento no puede eliminarse ni restablecerse a '
             'borrador.',
    )

    def _l10n_py_get_config_ajuste_inventario(self):
        company = self.env.company
        return self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', company.id)], limit=1
        )

    def _apply_inventory(self, date=None):
        config = self._l10n_py_get_config_ajuste_inventario()
        generar = bool(config and config.l10n_py_asiento_ajuste_inventario)

        quants_con_diff = self.filtered(
            lambda q: q.product_uom_id.compare(q.inventory_diff_quantity, 0) != 0
        )

        if generar:
            for quant in quants_con_diff:
                categ = quant.product_id.categ_id
                if not categ.property_stock_valuation_account_id or not categ.property_account_expense_categ_id:
                    raise UserError(
                        'La categoría "%s" del producto "%s" no tiene configuradas la cuenta '
                        'de valoración de inventario y/o la cuenta de gastos. Complete esos '
                        'datos en la categoría del producto antes de aplicar este ajuste.'
                        % (categ.name, quant.product_id.display_name)
                    )

        # Guardamos las diferencias antes de aplicar (Odoo las vacía al terminar)
        diffs = {q.id: q.inventory_diff_quantity for q in quants_con_diff}

        result = super()._apply_inventory(date=date)

        if generar:
            for quant in quants_con_diff:
                quant._l10n_py_crear_asiento_ajuste_inventario(diffs[quant.id])

        return result

    def _l10n_py_crear_asiento_ajuste_inventario(self, diff_qty):
        self.ensure_one()
        product = self.product_id
        categ = product.categ_id
        company = self.company_id or self.env.company

        costo_unitario = product.standard_price
        valor = abs(diff_qty) * costo_unitario
        if not valor:
            return  # sin costo configurado o diferencia sin impacto de valor: no hay nada que asentar

        comentario = 'Ajuste de Inventario Físico %s' % product.display_name

        if diff_qty > 0:
            cuenta_debito = categ.property_stock_valuation_account_id
            cuenta_credito = categ.property_account_expense_categ_id
        else:
            cuenta_debito = categ.property_account_expense_categ_id
            cuenta_credito = categ.property_stock_valuation_account_id

        journal = categ.property_stock_journal
        if not journal:
            journal = self.env['account.journal'].search([
                ('type', '=', 'general'), ('company_id', '=', company.id),
            ], limit=1)

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'company_id': company.id,
            'date': fields.Date.context_today(self),
            'l10n_py_comentario': comentario,
            'line_ids': [
                (0, 0, {'account_id': cuenta_debito.id, 'debit': valor, 'credit': 0.0, 'name': comentario}),
                (0, 0, {'account_id': cuenta_credito.id, 'debit': 0.0, 'credit': valor, 'name': comentario}),
            ],
        })
        move.action_post()
        self.l10n_py_asiento_ajuste_id = move.id
