# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import models


class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        publicados = super()._post(soft=soft)
        for factura in publicados.filtered(lambda m: m.move_type == 'in_invoice'):
            factura._tllr_fc_ajuste_compra_tardia()
        return publicados

    def _tllr_fc_ajuste_compra_tardia(self):
        """Factura de proveedor de una compra de la OT, publicada con la OT ya terminada.

        Crea un ajuste de costo automático por la diferencia entre lo facturado y lo imputado
        a la OT (el asiento lo genera la propia factura de proveedor).
        """
        self.ensure_one()
        compania = self.company_id
        for linea in self.invoice_line_ids.filtered('purchase_line_id'):
            compra = linea.purchase_line_id.order_id.sudo()
            ot = compra.tllr_fc_ot_id
            if (not ot or ot.state not in ('entregado', 'cancelada')
                    or not ot.company_id.tllr_fc_usar_compras):
                continue
            linea_compra = linea.purchase_line_id.sudo()
            esperado = linea_compra.currency_id._convert(
                linea_compra.price_unit * linea.quantity, compania.currency_id, compania,
                self.invoice_date or self.date)
            diferencia = compania.currency_id.round(linea.balance - esperado)
            if compania.currency_id.is_zero(diferencia):
                continue
            self.env['tllr_fc.ot.ajuste_costo'].sudo().with_context(
                tllr_fc_ajuste_automatico=True, tllr_fc_ajuste_sin_asiento=True,
                tllr_fc_permitir_write=True,
            ).create({
                'ot_id': ot.id,
                'fecha': self.invoice_date or self.date,
                'monto': diferencia,
                'motivo': "Factura de proveedor %s de la compra %s: diferencia contra lo imputado a la OT." % (
                    self.name, compra.name),
                'origen_compra_id': compra.id,
            })
