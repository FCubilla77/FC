# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import Command, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    tllr_fc_ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT de taller", copy=False, readonly=True,
        index='btree_not_null', ondelete='set null',
        help="Orden de trabajo del taller que originó este presupuesto o pedido.")
    tllr_fc_recepcion_ids = fields.One2many(
        'tllr_fc.recepcion', 'sale_order_id', string="Recepciones vinculadas")
    tllr_fc_recepcion_id = fields.Many2one(
        'tllr_fc.recepcion', string="Recepción de taller",
        compute='_compute_tllr_fc_recepcion_id')
    tllr_fc_vehiculo_id = fields.Many2one(
        'tllr_fc.vehiculo', string="Vehículo", copy=False, tracking=True,
        ondelete='restrict', index='btree_not_null')
    tllr_fc_chapa = fields.Char(string="Chapa", related='tllr_fc_vehiculo_id.chapa')
    tllr_fc_marca = fields.Char(string="Marca", related='tllr_fc_vehiculo_id.marca_id.name')
    tllr_fc_modelo = fields.Char(string="Modelo", related='tllr_fc_vehiculo_id.modelo_id.name')
    tllr_fc_kilometraje = fields.Integer(string="Kilometraje", copy=False)

    @api.depends('tllr_fc_recepcion_ids.state')
    def _compute_tllr_fc_recepcion_id(self):
        for pedido in self:
            pedido.tllr_fc_recepcion_id = pedido.tllr_fc_recepcion_ids.filtered(
                lambda r: r.state != 'cancelada')[:1]

    @api.constrains('tllr_fc_ot_id', 'state')
    def _check_tllr_fc_ot_unica(self):
        for pedido in self.filtered(lambda p: p.tllr_fc_ot_id and p.state != 'cancel'):
            otro = self.sudo().search_count([
                ('id', '!=', pedido.id), ('tllr_fc_ot_id', '=', pedido.tllr_fc_ot_id.id),
                ('state', '!=', 'cancel')])
            if otro:
                raise ValidationError(
                    "La OT %s ya tiene un presupuesto vigente: una OT tiene un solo presupuesto."
                    % pedido.tllr_fc_ot_id.name)

    # ------------------------------------------------------------------
    # Facturas y vencimiento
    # ------------------------------------------------------------------
    def _prepare_invoice(self):
        valores = super()._prepare_invoice()
        if self.tllr_fc_ot_id:
            valores['tllr_fc_ot_id'] = self.tllr_fc_ot_id.id
        return valores

    def _tllr_fc_es_del_taller(self):
        """True si el presupuesto o pedido pertenece al taller (OT, recepción o vehículo)."""
        self.ensure_one()
        return bool(self.tllr_fc_ot_id or self.tllr_fc_recepcion_ids or self.tllr_fc_vehiculo_id)

    def action_confirm(self):
        """Avisa antes de confirmar un presupuesto del taller vencido."""
        if (len(self) == 1 and self.state in ('draft', 'sent') and self.validity_date
                and self.validity_date < fields.Date.context_today(self)
                and (self.tllr_fc_vehiculo_id or self.tllr_fc_ot_id)
                and not self.env.context.get('tllr_fc_vencido_ok')):
            return {
                'type': 'ir.actions.act_window',
                'name': "Presupuesto vencido",
                'res_model': 'tllr_fc_sale.wizard.vencido',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_order_id': self.id,
                    'default_mensaje': (
                        "El presupuesto %s venció el %s. ¿Confirmarlo de todos modos?" % (
                            self.name, self.validity_date.strftime('%d/%m/%Y'))),
                },
            }
        return super().action_confirm()

    # ------------------------------------------------------------------
    # Auxiliares de la OT
    # ------------------------------------------------------------------
    def _tllr_fc_html_lineas(self):
        """Tabla HTML con las líneas actuales (para el historial del chatter)."""
        self.ensure_one()
        filas = Markup('')
        for linea in self.order_line.filtered(lambda l: not l.display_type):
            filas += Markup(
                "<tr><td>%s</td><td style='text-align:right'>%s</td>"
                "<td style='text-align:right'>%s</td><td style='text-align:right'>%s</td>"
                "<td style='text-align:right'>%s</td></tr>") % (
                    linea.product_id.display_name or linea.name, linea.product_uom_qty,
                    linea.price_unit, linea.discount, linea.price_subtotal)
        return Markup(
            "<table border='1' cellpadding='3'><tr><th>Producto</th><th>Cant.</th>"
            "<th>Precio</th><th>Desc. %%</th><th>Subtotal</th></tr>%s</table>"
            "<p>Total anterior: %s</p>") % (filas, self.amount_total)

    def _tllr_fc_verificar_almacenables_manuales(self, ot):
        """Al cerrar la OT no puede haber productos almacenables cargados a mano."""
        self.ensure_one()
        manuales = self.order_line.filtered(
            lambda l: l.product_uom_qty > 0 and l._tllr_fc_es_almacenable_manual())
        if manuales:
            raise UserError(
                "El presupuesto %s tiene productos almacenables cargados a mano que no están "
                "en la OT %s: %s. Cargalos en la orden de trabajo o quitalos del presupuesto "
                "para poder cerrar y facturar." % (
                    self.name, ot.name, ', '.join(manuales.mapped('product_id.display_name'))))

    def _tllr_fc_crear_factura(self, ot):
        """Factura en borrador desde el pedido, con lo que dice el pedido (no la política de facturación)."""
        self.ensure_one()
        compania = ot.company_id
        valores = self._prepare_invoice()
        valores.update({
            'journal_id': compania.tllr_fc_diario_venta_id.id,
            'tllr_fc_ot_id': ot.id,
            'ref': ot.name,
            'invoice_origin': self.name,
        })
        lineas = []
        secuencia = 10
        for linea in self.order_line.filtered(
                lambda l: not l.display_type and l.product_uom_qty > 0):
            lineas.append(Command.create(linea._prepare_invoice_line(
                sequence=secuencia, quantity=linea.product_uom_qty)))
            secuencia += 1
        valores['invoice_line_ids'] = lineas
        factura = self.env['account.move'].sudo().with_company(compania).create(valores)
        self.message_post(body=Markup("Factura %s generada desde la OT %s.") % (
            factura._get_html_link(), escape(ot.name)))
        return factura
