# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = 'account.move'

    tllr_fc_ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT de taller", copy=False, readonly=True,
        index='btree_not_null', ondelete='restrict',
        help="Orden de trabajo de taller que originó este comprobante.")
    tllr_fc_tipo_asiento = fields.Selection([
        ('factura', "Costo de la OT al facturar"),
        ('entrega', "Costo de la OT al entregar"),
        ('cancelacion', "Pérdida por OT cancelada"),
        ('ajuste', "Ajuste de costo de la OT"),
        ('consumo', "Consumo o devolución de stock de la OT"),
        ('traslado', "Traslado de stock de la OT"),
    ], string="Asiento del taller", copy=False, readonly=True, index='btree_not_null')
    tllr_fc_origen_id = fields.Many2one(
        'account.move', string="Factura de origen (taller)", copy=False, readonly=True,
        ondelete='set null', help="Factura que originó este asiento del taller.")

    def _post(self, soft=True):
        for nota in self.filtered(lambda m: m.move_type == 'out_refund'):
            nota._tllr_fc_validar_nota_credito()
        posted = super()._post(soft=soft)
        for factura in posted.filtered(
                lambda m: m.move_type == 'out_invoice' and m.tllr_fc_ot_id):
            factura.tllr_fc_ot_id.sudo()._tllr_fc_asiento_factura(factura)
        for nota in posted.filtered(
                lambda m: m.move_type == 'out_refund' and m.reversed_entry_id.tllr_fc_ot_id):
            nota.reversed_entry_id.tllr_fc_ot_id.sudo()._tllr_fc_nota_credito_total(nota)
        return posted

    def _reverse_moves(self, default_values_list=None, cancel=False):
        # La reversa (nota de crédito o reversa de asiento) conserva la OT de origen.
        if not default_values_list:
            default_values_list = [{} for _movimiento in self]
        for movimiento, valores in zip(self, default_values_list):
            if movimiento.tllr_fc_ot_id:
                valores.setdefault('tllr_fc_ot_id', movimiento.tllr_fc_ot_id.id)
                if movimiento.move_type == 'entry':
                    valores.setdefault('tllr_fc_tipo_asiento', movimiento.tllr_fc_tipo_asiento)
        return super()._reverse_moves(default_values_list=default_values_list, cancel=cancel)

    # ------------------------------------------------------------------
    # Operaciones de una OT: se deshacen desde Taller
    # ------------------------------------------------------------------
    def _tllr_fc_es_de_ot(self):
        return bool(self.tllr_fc_ot_id) and not self.env.context.get('tllr_fc_permitir_write')

    def button_draft(self):
        for movimiento in self.filtered(lambda m: m._tllr_fc_es_de_ot()):
            if movimiento.move_type == 'out_invoice':
                raise UserError(
                    "La factura %s pertenece a la OT %s y no se pasa a borrador: se corrige "
                    "con una nota de crédito por el total." % (
                        movimiento.name or '', movimiento.tllr_fc_ot_id.name))
            raise UserError(
                "El asiento %s pertenece a la OT %s: se deshace desde el módulo de Taller." % (
                    movimiento.name or '', movimiento.tllr_fc_ot_id.name))
        return super().button_draft()

    def button_cancel(self):
        for movimiento in self.filtered(lambda m: m._tllr_fc_es_de_ot()):
            raise UserError(
                "%s %s pertenece a la OT %s: se anula desde el módulo de Taller%s." % (
                    "La factura" if movimiento.move_type == 'out_invoice' else "El comprobante",
                    movimiento.name or '', movimiento.tllr_fc_ot_id.name,
                    " (reabriendo la facturación de la OT)" if movimiento.move_type == 'out_invoice' else ""))
        return super().button_cancel()

    @api.ondelete(at_uninstall=False)
    def _tllr_fc_unlink_de_ot(self):
        for movimiento in self.filtered(lambda m: m._tllr_fc_es_de_ot()):
            raise UserError(
                "%s pertenece a la OT %s y no se elimina desde Contabilidad: se gestiona desde "
                "el módulo de Taller." % (movimiento.display_name, movimiento.tllr_fc_ot_id.name))

    # ------------------------------------------------------------------
    # Notas de crédito de facturas de una OT: solo por el total
    # ------------------------------------------------------------------
    def _tllr_fc_validar_nota_credito(self):
        self.ensure_one()
        factura = self.reversed_entry_id
        if not factura.tllr_fc_ot_id or factura.move_type != 'out_invoice':
            return
        moneda = factura.currency_id
        if moneda.compare_amounts(self.amount_total, factura.amount_total) != 0:
            raise UserError(
                "La factura %s pertenece a la OT %s: la nota de crédito debe ser por el total "
                "(%s). Para facturar solo una parte, emití la nota de crédito total y generá la "
                "nueva factura desde la OT marcando «No facturar» en lo que no se cobra." % (
                    factura.name, factura.tllr_fc_ot_id.name, factura.amount_total))
        otras = self.search_count([
            ('reversed_entry_id', '=', factura.id), ('state', '=', 'posted'),
            ('id', '!=', self.id)])
        if otras:
            raise UserError("La factura %s ya tiene una nota de crédito confirmada." % factura.name)
