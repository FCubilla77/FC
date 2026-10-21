# -*- coding: utf-8 -*-
from datetime import date

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import TallerCommon


@tagged('post_install', '-at_install')
class TestAsientos(TallerCommon):
    """2026.19.010: asientos contables del taller."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        compania = cls.env.company
        Cuenta = cls.env['account.account']
        cls.inventario = Cuenta.create({'name': 'Inventario F6', 'code': '119901', 'account_type': 'asset_current'})
        cls.costo_ventas = Cuenta.create({'name': 'Costo ventas F6', 'code': '519901', 'account_type': 'expense_direct_cost'})
        cls.gasto_interna = Cuenta.create({'name': 'Gasto internas F6', 'code': '619901', 'account_type': 'expense'})
        cls.gasto_garantia = Cuenta.create({'name': 'Gasto garantía F6', 'code': '619902', 'account_type': 'expense'})
        cls.perdida = Cuenta.create({'name': 'Pérdida cancel F6', 'code': '619903', 'account_type': 'expense'})
        cls.mano_obra = Cuenta.create({'name': 'Mano de obra aplicada F6', 'code': '219901', 'account_type': 'liability_current'})
        cls.categoria = cls.env['product.category'].create({
            'name': 'Repuestos F6', 'property_valuation': 'real_time',
            'property_cost_method': 'standard',
            'property_stock_valuation_account_id': cls.inventario.id,
            'property_account_expense_categ_id': cls.costo_ventas.id})
        (cls.repuesto | cls.insumo).write({'categ_id': cls.categoria.id})
        cls.diario_venta = cls.env['account.journal'].search(
            [('type', '=', 'sale'), ('company_id', '=', compania.id)], limit=1)
        cls.diario_asientos = cls.env['account.journal'].create({
            'name': 'Taller F6', 'code': 'TF6', 'type': 'general'})
        compania.write({
            'tllr_fc_diario_venta_id': cls.diario_venta.id,
            'tllr_fc_diario_id': cls.diario_asientos.id,
            'tllr_fc_cuenta_gasto_interna_id': cls.gasto_interna.id,
            'tllr_fc_cuenta_gasto_garantia_id': cls.gasto_garantia.id,
            'tllr_fc_cuenta_perdida_id': cls.perdida.id,
            'tllr_fc_generar_asientos': True})
        funcion = cls.env['tllr_fc.funcion'].create({'name': 'Mecánico F6'})
        cls.env['tllr_fc.funcion.costo'].create({
            'funcion_id': funcion.id, 'fecha_desde': date(2020, 1, 1), 'costo_hora': 20000})
        cls.personal1.funcion_id = funcion
        cls.plazo = cls.env['account.payment.term'].create({
            'name': '30 días F6', 'line_ids': [Command.create({
                'value': 'percent', 'value_amount': 100, 'delay_type': 'days_after',
                'nb_days': 30})]})

    # ---------------- Auxiliares ----------------
    def _ot_lista(self, tipo='cliente', productos=(), horas=0.0):
        """OT lista para entrega con los productos (producto, reservado, utilizado, extra)."""
        ot = self._ot_planificada()
        if tipo != 'cliente':
            ot.write({'tipo': tipo})
        lineas = self.env['tllr_fc.ot.producto']
        for producto, cantidad, extra in productos:
            vals = {'ot_id': ot.id, 'product_id': producto.id, 'cantidad_reservada': cantidad}
            vals.update(extra)
            lineas |= self.env['tllr_fc.ot.producto'].create(vals)
        ot.action_iniciar()
        for linea in lineas:
            linea.cantidad_utilizada = linea.cantidad_reservada
        if horas:
            self.env['tllr_fc.ot.hora'].create({
                'ot_id': ot.id, **self._sv(ot), 'personal_id': self.personal1.id, 'horas': horas})
        for puesto in ot.puesto_line_ids.sorted('sequence'):
            if puesto.state == 'activo':
                puesto.servicio_ids.filtered(lambda s: s.estado == 'pendiente').action_terminar()
                ot.action_terminar_puesto()
        self.assertEqual(ot.state, 'listo')
        return ot

    def _asientos(self, ot, tipo=None):
        asientos = self.env['account.move'].search([
            ('tllr_fc_ot_id', '=', ot.id), ('move_type', '=', 'entry'),
            ('reversed_entry_id', '=', False)])
        if tipo:
            asientos = asientos.filtered(lambda m: m.tllr_fc_tipo_asiento == tipo)
        return asientos

    def _saldo(self, asiento, cuenta):
        lineas = asiento.line_ids.filtered(lambda l: l.account_id == cuenta)
        return sum(lineas.mapped('debit')) - sum(lineas.mapped('credit'))

    def _entregar(self, ot):
        entrega = self.env['tllr_fc.entrega'].create({'ot_id': ot.id})
        entrega.linea_ids.write({'entregado': 'si'})
        entrega.write({'retira_id': entrega.partner_id.id, 'combustible_salida': 'lleno'})
        entrega.kilometraje_salida = 3000
        entrega.action_confirmar()
        self.assertEqual(ot.state, 'entregado')

    # ---------------- Cliente ----------------
    def test_consumo_no_genera_asiento(self):
        ot = self._ot_lista(productos=[(self.repuesto, 2, {})])
        self.assertEqual(ot.producto_ids.cantidad_consumida, 2)
        self.assertFalse(self._asientos(ot))

    def test_factura_cliente_costo_de_lineas_no_facturadas(self):
        ot = self._ot_lista(productos=[
            (self.repuesto, 2, {}),            # facturado: costo estándar de la factura
            (self.insumo, 3, {}),              # insumo no facturable
        ], horas=2.0)
        ot.action_cerrar_facturar()
        factura = ot._tllr_fc_facturas()
        self.assertNotIn(self.insumo, factura.invoice_line_ids.product_id)
        factura.invoice_payment_term_id = self.plazo
        factura.action_post()
        # Costo de ventas estándar de Odoo por lo facturado.
        cogs = factura.line_ids.filtered(lambda l: l.display_type == 'cogs')
        self.assertTrue(cogs)
        # Asiento propio: solo el insumo no facturado (3 × 3000), sin horas (ajuste inactivo).
        asiento = self._asientos(ot, 'factura')
        self.assertEqual(len(asiento), 1)
        self.assertAlmostEqual(self._saldo(asiento, self.costo_ventas), 9000)
        self.assertAlmostEqual(self._saldo(asiento, self.inventario), -9000)
        analiticas = asiento.line_ids.filtered(lambda l: l.account_id == self.costo_ventas)
        self.assertTrue(analiticas.analytic_distribution)
        # La factura de una OT no vuelve a borrador (2026.19.011): se corrige con nota de crédito total.
        with self.assertRaises(UserError):
            factura.button_draft()
        nota = factura._reverse_moves(cancel=True)
        self.assertEqual(nota.tllr_fc_ot_id, ot)
        self.assertFalse(self._asientos(ot, 'factura').filtered(lambda m: not m.reversal_move_ids))
        self.assertFalse(ot.cerrada_facturar)
        self.assertTrue(ot.puede_refacturar)

    def test_linea_no_facturar_lleva_costo_sin_ingreso(self):
        ot = self._ot_lista(productos=[
            (self.repuesto, 2, {'no_facturar': True}), (self.insumo, 1, {})])
        ot.action_cerrar_facturar()
        factura = ot._tllr_fc_facturas()
        self.assertNotIn(self.repuesto, factura.invoice_line_ids.product_id)
        factura.invoice_payment_term_id = self.plazo
        factura.action_post()
        asiento = self._asientos(ot, 'factura')
        # 2 × 12000 (repuesto cortesía) + 1 × 3000 (insumo)
        self.assertAlmostEqual(self._saldo(asiento, self.costo_ventas), 27000)

    def test_horas_solo_con_el_parametro_activo(self):
        compania = self.env.company
        ot = self._ot_lista(productos=[(self.insumo, 1, {})], horas=2.0)
        ot.action_cerrar_facturar()
        factura = ot._tllr_fc_facturas()
        factura.invoice_payment_term_id = self.plazo
        factura.action_post()
        self.assertAlmostEqual(self._saldo(self._asientos(ot, 'factura'), self.mano_obra), 0)
        # Con el parámetro activo, las horas (2 × 20000) van a costo de ventas / mano de obra.
        compania.write({
            'tllr_fc_cuenta_mano_obra_id': self.mano_obra.id,
            'tllr_fc_cuenta_costo_ventas_id': self.costo_ventas.id,
            'tllr_fc_asiento_horas': True})
        ot2 = self._ot_lista(productos=[(self.insumo, 1, {})], horas=2.0)
        ot2.action_cerrar_facturar()
        f2 = ot2._tllr_fc_facturas()
        f2.invoice_payment_term_id = self.plazo
        f2.action_post()
        asiento = self._asientos(ot2, 'factura')
        self.assertAlmostEqual(self._saldo(asiento, self.mano_obra), -40000)
        self.assertAlmostEqual(self._saldo(asiento, self.costo_ventas), 40000 + 3000)
        compania.tllr_fc_asiento_horas = False

    # ---------------- Interna y garantía ----------------
    def test_ot_interna_genera_gasto_al_entregar(self):
        ot = self._ot_lista(tipo='interno', productos=[(self.repuesto, 2, {})])
        self.assertFalse(self._asientos(ot))
        self._entregar(ot)
        asiento = self._asientos(ot, 'entrega')
        self.assertEqual(len(asiento), 1)
        self.assertAlmostEqual(self._saldo(asiento, self.gasto_interna), 24000)
        self.assertAlmostEqual(self._saldo(asiento, self.inventario), -24000)

    def test_ot_garantia_excluye_lo_cobrado_al_cliente(self):
        ot = self._ot_planificada()
        ot.write({'tipo': 'garantia'})
        cobrado = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 1,
            'cobrar_cliente': True})
        absorbido = self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.insumo.id, 'cantidad_reservada': 2})
        ot.action_iniciar()
        self.env['tllr_fc.wizard.aprobacion'].with_context(default_ot_id=ot.id).create({
            'ot_id': ot.id, 'persona': 'Cliente', 'estado': 'aprobado'}).action_registrar()
        cobrado.cantidad_utilizada = 1
        absorbido.cantidad_utilizada = 2
        for puesto in ot.puesto_line_ids.sorted('sequence'):
            if puesto.state == 'activo':
                puesto.servicio_ids.filtered(lambda s: s.estado == 'pendiente').action_terminar()
                ot.action_terminar_puesto()
        ot.action_cerrar_facturar()
        factura = ot._tllr_fc_facturas()
        factura.invoice_payment_term_id = self.plazo
        factura.action_post()
        self._entregar(ot)
        asiento = self._asientos(ot, 'entrega')
        # Solo el insumo (2 × 3000); el repuesto cobrado sigue la factura.
        self.assertAlmostEqual(self._saldo(asiento, self.gasto_garantia), 6000)

    # ---------------- Cancelación ----------------
    def test_cancelacion_sin_liquidar_va_a_perdida(self):
        ot = self._ot_planificada()
        self.env['tllr_fc.ot.producto'].create({
            'ot_id': ot.id, 'product_id': self.repuesto.id, 'cantidad_reservada': 2})
        ot.action_iniciar()
        ot.producto_ids.cantidad_utilizada = 1
        motivo = self.env['tllr_fc.motivo'].search([('tipo', '=', 'cancelacion')], limit=1)
        ot._tllr_fc_cancelar(motivo, False)
        asiento = self._asientos(ot, 'cancelacion')
        self.assertEqual(len(asiento), 1)
        self.assertAlmostEqual(self._saldo(asiento, self.perdida), 12000)
        self.assertAlmostEqual(self._saldo(asiento, self.inventario), -12000)

    def test_cancelacion_sin_trabajo_no_genera_asiento(self):
        ot = self._ot_planificada()
        motivo = self.env['tllr_fc.motivo'].search([('tipo', '=', 'cancelacion')], limit=1)
        ot._tllr_fc_cancelar(motivo, False)
        self.assertFalse(self._asientos(ot))

    # ---------------- Ajuste de costo ----------------
    def test_ajuste_de_costo_solo_administrador_y_genera_asiento(self):
        ot = self._ot_lista(tipo='interno', productos=[(self.repuesto, 1, {})])
        self._entregar(ot)
        costo_antes = ot.costo_propio
        ajuste = self.env['tllr_fc.ot.ajuste_costo'].create({
            'ot_id': ot.id, 'monto': 5000, 'motivo': 'Costo mal cargado',
            'cuenta_debe_id': self.gasto_interna.id, 'cuenta_haber_id': self.inventario.id})
        self.assertTrue(ajuste.asiento_id)
        self.assertAlmostEqual(self._saldo(ajuste.asiento_id, self.gasto_interna), 5000)
        self.assertAlmostEqual(ot.costo_propio, costo_antes + 5000)
        with self.assertRaises(UserError):
            ajuste.motivo = 'otro'
        with self.assertRaises(UserError):
            ajuste.unlink()
        negativo = self.env['tllr_fc.ot.ajuste_costo'].create({
            'ot_id': ot.id, 'monto': -2000, 'motivo': 'Corrección',
            'cuenta_debe_id': self.gasto_interna.id, 'cuenta_haber_id': self.inventario.id})
        self.assertAlmostEqual(self._saldo(negativo.asiento_id, self.gasto_interna), -2000)
        supervisor = self.env['res.users'].create({
            'name': 'Supervisor F6', 'login': 'sup_f6',
            'group_ids': [Command.link(self.env.ref('tllr_fc.group_supervisor').id)]})
        with self.assertRaises(AccessError):
            self.env['tllr_fc.ot.ajuste_costo'].with_user(supervisor).create({
                'ot_id': ot.id, 'monto': 1, 'motivo': 'x'})

    def test_sin_asientos_activados_no_se_genera_nada(self):
        compania = self.env.company
        compania.tllr_fc_generar_asientos = False
        ot = self._ot_lista(tipo='interno', productos=[(self.repuesto, 2, {})])
        self._entregar(ot)
        self.assertFalse(self._asientos(ot))
        compania.tllr_fc_generar_asientos = True

    def test_asientos_exigen_cuentas(self):
        compania = self.env.company
        with self.assertRaises(ValidationError):
            compania.tllr_fc_cuenta_perdida_id = False
