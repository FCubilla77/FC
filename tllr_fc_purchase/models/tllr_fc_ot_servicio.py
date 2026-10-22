# -*- coding: utf-8 -*-
from markupsafe import Markup, escape

from odoo import Command, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class TllrFcOtServicio(models.Model):
    _inherit = 'tllr_fc.ot.servicio'

    tllr_fc_usar_compras = fields.Boolean(related='ot_id.company_id.tllr_fc_usar_compras')
    puede_tercerizarse = fields.Boolean(
        related='product_id.product_tmpl_id.tllr_fc_puede_tercerizarse', string="Puede tercerizarse")
    tercerizado = fields.Boolean(
        string="Tercerizado", copy=False,
        help="El servicio lo realiza un proveedor externo. Solo el supervisor.")
    proveedor_id = fields.Many2one(
        'res.partner', string="Proveedor", copy=False, ondelete='restrict', index='btree_not_null')
    compra_line_id = fields.Many2one(
        'purchase.order.line', string="Línea de compra", copy=False, readonly=True,
        ondelete='set null', index='btree_not_null')
    compra_id = fields.Many2one(
        'purchase.order', string="Compra", related='compra_line_id.order_id')
    costo_real = fields.Monetary(
        string="Costo real", currency_field='currency_id', compute='_compute_costo_real',
        groups='tllr_fc.group_supervisor',
        help="Subtotal de la compra confirmada, en la moneda de la compañía.")

    # ------------------------------------------------------------------
    # Cálculos
    # ------------------------------------------------------------------
    def _tllr_fc_compra_confirmada(self):
        self.ensure_one()
        linea = self.compra_line_id.sudo()
        return bool(linea and linea.order_id.state in ('purchase', 'done'))

    def _tllr_fc_valor_compra(self):
        """Subtotal de la línea de compra, en la moneda de la compañía."""
        self.ensure_one()
        linea = self.compra_line_id.sudo()
        compania = self.ot_id.company_id
        return linea.currency_id._convert(
            linea.price_subtotal, compania.currency_id, compania,
            linea.order_id.date_order or fields.Date.context_today(self))

    @api.depends('compra_line_id.price_subtotal', 'compra_line_id.order_id.state')
    def _compute_costo_real(self):
        for servicio in self:
            servicio.costo_real = (
                servicio._tllr_fc_valor_compra() if servicio._tllr_fc_compra_confirmada() else 0.0)

    def _tllr_fc_costo_efectivo_servicio(self):
        self.ensure_one()
        if self.tercerizado and self._tllr_fc_compra_confirmada():
            return self._tllr_fc_valor_compra()
        return super()._tllr_fc_costo_efectivo_servicio()

    @api.depends('tercerizado', 'compra_line_id.price_subtotal', 'compra_line_id.order_id.state')
    def _compute_costos(self):
        super()._compute_costos()

    @api.depends('tercerizado')
    def _compute_horas_estandar(self):
        super()._compute_horas_estandar()
        for servicio in self.filtered('tercerizado'):
            servicio.horas_estandar = 0.0

    def _tllr_fc_requiere_horas(self):
        self.ensure_one()
        return not self.tercerizado and super()._tllr_fc_requiere_horas()

    # ------------------------------------------------------------------
    # Restricciones
    # ------------------------------------------------------------------
    @api.constrains('tercerizado', 'proveedor_id', 'product_id')
    def _check_tercerizado(self):
        for servicio in self.filtered('tercerizado'):
            if not servicio.puede_tercerizarse:
                raise ValidationError(
                    "El servicio «%s» no está marcado «Puede tercerizarse» en su ficha."
                    % servicio.product_id.display_name)
            if not servicio.proveedor_id:
                raise ValidationError(
                    "Indicá el proveedor del servicio tercerizado «%s»." % servicio.product_id.display_name)

    def _tllr_fc_verificar_supervisor_tercerizado(self, vals):
        campos = {'tercerizado', 'proveedor_id'} & set(vals)
        if campos and not self.env.user.has_group('tllr_fc.group_supervisor'):
            raise AccessError(
                "Solo el supervisor o el administrador de taller pueden tercerizar un servicio.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('tercerizado') or vals.get('proveedor_id'):
                self._tllr_fc_verificar_supervisor_tercerizado(vals)
        return super().create(vals_list)

    def write(self, vals):
        self._tllr_fc_verificar_supervisor_tercerizado(vals)
        if vals.get('tercerizado') is False or 'proveedor_id' in vals:
            for servicio in self:
                compra = servicio.compra_line_id.sudo().order_id
                if compra and compra.state != 'cancel':
                    raise UserError(
                        "El servicio ya tiene la compra %s: cancelala antes de cambiar la "
                        "tercerización." % compra.name)
        return super().write(vals)

    # ------------------------------------------------------------------
    # Compra del servicio
    # ------------------------------------------------------------------
    def action_generar_compra(self):
        """Crea la orden de compra (borrador) del servicio tercerizado."""
        self.ensure_one()
        ot = self.ot_id
        if not self.env.user.has_group('tllr_fc.group_supervisor'):
            raise AccessError(
                "Solo el supervisor o el administrador de taller pueden generar la compra.")
        if not ot.company_id.tllr_fc_usar_compras:
            raise UserError("La integración con Compras está desactivada en Ajustes.")
        if not self.tercerizado:
            raise UserError("Marcá el servicio como tercerizado y elegí el proveedor.")
        if ot.state not in ('espera', 'proceso'):
            raise UserError("La compra del servicio se genera con la OT en espera o en proceso.")
        if self.compra_line_id and self.compra_line_id.order_id.sudo().state != 'cancel':
            raise UserError("El servicio ya tiene la compra %s." % self.compra_line_id.order_id.name)
        compania = ot.company_id
        compra = self.env['purchase.order'].sudo().with_company(compania).create({
            'partner_id': self.proveedor_id.id,
            'company_id': compania.id,
            'origin': ot.name,
            'tllr_fc_ot_id': ot.id,
            'tllr_fc_tipo': 'tercerizado',
            'order_line': [Command.create({
                'product_id': self.product_id.id,
                'name': self.product_id.display_name,
                'product_qty': self.cantidad,
                'tllr_fc_ot_servicio_id': self.id,
            })],
        })
        self.sudo().with_context(tllr_fc_permitir_write=True).write(
            {'compra_line_id': compra.order_line[:1].id})
        ot.message_post(body=Markup("Servicio tercerizado «%s»: se generó la compra %s al proveedor %s.") % (
            escape(self.product_id.display_name), compra._get_html_link(),
            escape(self.proveedor_id.display_name)))
        return True
