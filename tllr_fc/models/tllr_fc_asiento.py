# -*- coding: utf-8 -*-
from odoo import Command, api, fields, models
from odoo.exceptions import UserError


class TllrFcOtAsiento(models.Model):
    """Asientos contables del taller (2026.19.010).

    - El consumo de stock no genera asiento (la ubicación «Consumo en taller» no tiene cuenta
      de valoración): el costo se reconoce cuando la OT se factura, se entrega o se cancela.
    - Cliente: el costo de lo facturado lo genera la factura (estándar de Odoo). El módulo
      agrega el costo de los repuestos e insumos NO facturados al confirmar la factura.
    - Interna / Garantía: al entregar, Debe gasto / Haber Inventario.
    - Cancelada sin liquidar: Debe pérdida / Haber Inventario.
    - Horas del personal: solo con el ajuste activado.
    """
    _inherit = 'tllr_fc.ot'

    analitica_id = fields.Many2one(
        'account.analytic.account', string="Cuenta analítica", readonly=True, copy=False,
        ondelete='set null')
    asiento_ids = fields.One2many(
        'account.move', 'tllr_fc_ot_id', string="Asientos del taller", readonly=True,
        domain=[('move_type', '=', 'entry')])
    asiento_count = fields.Integer(string="Asientos", compute='_compute_asiento_count')
    ajuste_ids = fields.One2many(
        'tllr_fc.ot.ajuste_costo', 'ot_id', string="Ajustes de costo", readonly=True)

    def _compute_asiento_count(self):
        datos = self.env['account.move'].sudo()._read_group(
            [('tllr_fc_ot_id', 'in', self.ids), ('move_type', '=', 'entry')],
            ['tllr_fc_ot_id'], ['__count'])
        conteos = {ot.id: cantidad for ot, cantidad in datos}
        for ot in self:
            ot.asiento_count = conteos.get(ot.id, 0)

    def action_ver_asientos(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': "Asientos del taller",
            'res_model': 'account.move', 'view_mode': 'list,form',
            'domain': [('tllr_fc_ot_id', '=', self.id), ('move_type', '=', 'entry')],
            'context': {'create': False}}

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------
    def _tllr_fc_asientos_activos(self):
        self.ensure_one()
        compania = self.company_id.sudo()
        return bool(compania.tllr_fc_generar_asientos and compania.tllr_fc_diario_id)

    def _tllr_fc_cuenta_analitica(self):
        """Cuenta analítica de la OT (se crea la primera vez, en el plan «Taller»)."""
        self.ensure_one()
        ot = self.sudo()
        if not ot.analitica_id:
            Plan = self.env['account.analytic.plan'].sudo()
            plan = Plan.search([('name', '=', "Taller")], limit=1) or Plan.create({'name': "Taller"})
            ot.analitica_id = self.env['account.analytic.account'].sudo().create({
                'name': ot.name, 'plan_id': plan.id, 'company_id': ot.company_id.id,
                'partner_id': ot.partner_id.id})
        return ot.analitica_id

    def _tllr_fc_asiento_existente(self, tipo, origen=None):
        self.ensure_one()
        dominio = [
            ('tllr_fc_ot_id', '=', self.id), ('move_type', '=', 'entry'),
            ('tllr_fc_tipo_asiento', '=', tipo), ('state', '=', 'posted'),
            ('reversed_entry_id', '=', False)]
        if origen:
            dominio.append(('tllr_fc_origen_id', '=', origen.id))
        return self.env['account.move'].sudo().search(dominio).filtered(
            lambda m: not m.reversal_move_ids)

    def _tllr_fc_valor_linea(self, linea):
        """Costo (en moneda de la compañía) de lo consumido en la línea."""
        return sum(abs(m.value) for m in linea.sudo().move_ids if m.state == 'done')

    def _tllr_fc_lineas_costo(self, productos, cuenta_debito=None, concepto=""):
        """Líneas de asiento por el costo de los repuestos/insumos: Debe gasto / Haber Inventario."""
        self.ensure_one()
        moneda = self.company_id.currency_id
        debitos, creditos = {}, {}
        for linea in productos.sudo():
            producto = linea.product_id
            if not producto.is_storable or producto.valuation != 'real_time':
                continue
            valor = moneda.round(self._tllr_fc_valor_linea(linea))
            if moneda.is_zero(valor):
                continue
            cuentas = producto.product_tmpl_id.with_company(self.company_id)._get_product_accounts()
            inventario = cuentas['stock_valuation']
            gasto = cuenta_debito or cuentas['expense']
            if not inventario or not gasto:
                raise UserError(
                    "Falta la cuenta de %s de «%s» (categoría %s): revisá la configuración "
                    "contable de la categoría del producto." % (
                        "inventario" if not inventario else "gasto", producto.display_name,
                        producto.categ_id.display_name))
            debitos[gasto] = debitos.get(gasto, 0.0) + valor
            creditos[inventario] = creditos.get(inventario, 0.0) + valor
        lineas = [
            {'account': cuenta, 'debit': valor, 'credit': 0.0, 'analitica': True,
             'name': concepto or "Costo de repuestos e insumos"}
            for cuenta, valor in debitos.items()]
        lineas += [
            {'account': cuenta, 'debit': 0.0, 'credit': valor, 'analitica': False,
             'name': concepto or "Costo de repuestos e insumos"}
            for cuenta, valor in creditos.items()]
        return lineas

    def _tllr_fc_lineas_horas(self, importe, cuenta_debito, concepto="Costo de mano de obra"):
        self.ensure_one()
        compania = self.company_id.sudo()
        importe = compania.currency_id.round(importe)
        if (not compania.tllr_fc_asiento_horas or compania.currency_id.is_zero(importe)
                or not cuenta_debito):
            return []
        return [
            {'account': cuenta_debito, 'debit': importe, 'credit': 0.0, 'analitica': True,
             'name': concepto},
            {'account': compania.tllr_fc_cuenta_mano_obra_id, 'debit': 0.0, 'credit': importe,
             'analitica': False, 'name': concepto},
        ]

    def _tllr_fc_crear_asiento(self, tipo, lineas, concepto, fecha=None, origen=None):
        """Crea y confirma el asiento del taller (nada si el total es cero)."""
        self.ensure_one()
        compania = self.company_id.sudo()
        if not lineas:
            return self.env['account.move']
        distribucion = {str(self._tllr_fc_cuenta_analitica().id): 100}
        comandos = [Command.create({
            'account_id': linea['account'].id,
            'name': "%s – %s" % (self.name, linea['name']),
            'debit': linea['debit'], 'credit': linea['credit'],
            'analytic_distribution': distribucion if linea['analitica'] else False,
        }) for linea in lineas]
        asiento = self.env['account.move'].sudo().with_company(compania).create({
            'move_type': 'entry',
            'journal_id': compania.tllr_fc_diario_id.id,
            'date': fecha or fields.Date.context_today(self),
            'ref': "%s – %s" % (self.name, concepto),
            'company_id': compania.id,
            'tllr_fc_ot_id': self.id,
            'tllr_fc_tipo_asiento': tipo,
            'tllr_fc_origen_id': origen.id if origen else False,
            'line_ids': comandos,
        })
        asiento.action_post()
        self.message_post(body="Asiento contable generado: %s (%s)." % (
            asiento._get_html_link(), concepto))
        return asiento

    # ------------------------------------------------------------------
    # Asientos
    # ------------------------------------------------------------------
    def _tllr_fc_asiento_factura(self, factura):
        """Al confirmar la factura de la OT: costo de lo que no se factura y horas cobradas."""
        self.ensure_one()
        if not self._tllr_fc_asientos_activos() or self._tllr_fc_asiento_existente(
                'factura', origen=factura):
            return False
        compania = self.company_id.sudo()
        lineas = []
        if self.tipo == 'cliente':
            # Lo facturado lleva el costo de ventas estándar de la factura; el resto, aquí.
            lineas += self._tllr_fc_lineas_costo(
                self.producto_ids.filtered(lambda p: not p.facturable),
                concepto="Costo de repuestos e insumos no facturados")
        lineas += self._tllr_fc_lineas_horas(
            self._tllr_fc_horas_reparto()[0], compania.tllr_fc_cuenta_costo_ventas_id,
            concepto="Costo de mano de obra")
        return self._tllr_fc_crear_asiento(
            'factura', lineas, "costo al facturar (%s)" % (factura.name or ''),
            fecha=factura.invoice_date, origen=factura)

    def _tllr_fc_asiento_entrega(self):
        """Al entregar una OT interna o de garantía: Debe gasto / Haber Inventario."""
        self.ensure_one()
        if (self.tipo == 'cliente' or not self._tllr_fc_asientos_activos()
                or self._tllr_fc_asiento_existente('entrega')):
            return False
        compania = self.company_id.sudo()
        if self.tipo == 'interno':
            cuenta = compania.tllr_fc_cuenta_gasto_interna_id
            productos = self.producto_ids
            concepto = "gasto de OT interna"
        else:
            cuenta = compania.tllr_fc_cuenta_gasto_garantia_id
            productos = self.producto_ids.filtered(lambda p: not p.facturable)
            concepto = "gasto de garantía"
        lineas = self._tllr_fc_lineas_costo(
            productos, cuenta_debito=cuenta, concepto="Costo de repuestos e insumos")
        lineas += self._tllr_fc_lineas_horas(
            self._tllr_fc_horas_reparto()[1], cuenta, concepto="Costo de mano de obra")
        return self._tllr_fc_crear_asiento('entrega', lineas, concepto)

    def _tllr_fc_asiento_cancelacion(self):
        """OT cancelada sin liquidar: lo consumido y las horas van a pérdida."""
        self.ensure_one()
        if not self._tllr_fc_asientos_activos() or self._tllr_fc_asiento_existente('cancelacion'):
            return False
        compania = self.company_id.sudo()
        cuenta = compania.tllr_fc_cuenta_perdida_id
        lineas = self._tllr_fc_lineas_costo(
            self.producto_ids, cuenta_debito=cuenta, concepto="Costo de repuestos e insumos")
        horas = sum(self._tllr_fc_horas_reparto())
        lineas += self._tllr_fc_lineas_horas(horas, cuenta, concepto="Costo de mano de obra")
        return self._tllr_fc_crear_asiento('cancelacion', lineas, "pérdida por OT cancelada")

    def _tllr_fc_revertir_asientos(self, origen=None):
        """Revierte (contra-asiento de hoy) los asientos de factura de la OT."""
        hoy = fields.Date.context_today(self)
        for ot in self:
            dominio = [
                ('tllr_fc_ot_id', '=', ot.id), ('move_type', '=', 'entry'),
                ('tllr_fc_tipo_asiento', '=', 'factura'), ('state', '=', 'posted'),
                ('reversed_entry_id', '=', False)]
            if origen:
                dominio.append(('tllr_fc_origen_id', '=', origen.id))
            asientos = self.env['account.move'].sudo().search(dominio).filtered(
                lambda m: not m.reversal_move_ids)
            for asiento in asientos:
                asiento._reverse_moves(
                    [{'date': hoy, 'ref': "Reversa de %s" % asiento.name}], cancel=True)
                ot.message_post(body="Asiento %s revertido." % asiento.name)
