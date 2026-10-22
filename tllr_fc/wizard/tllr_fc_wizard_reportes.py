# -*- coding: utf-8 -*-
from datetime import datetime, time

from odoo import api, fields, models
from odoo.exceptions import UserError

TIPOS_ORDEN = ('cliente', 'garantia', 'interno')
CLAVES_IMPORTE = ('ingreso', 'costo_propio', 'mano_obra', 'impuesto', 'ajustes_costo',
                  'garantias', 'costos', 'margen')


class TllrFcWizardRepRentabilidad(models.TransientModel):
    """Reporte de rentabilidad de las OT por rango de fecha de ingreso (sin canceladas)."""
    _name = 'tllr_fc.wizard.rep_rentabilidad'
    _description = "Reporte de rentabilidad de OT"

    fecha_desde = fields.Date(
        string="Ingreso desde", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    fecha_hasta = fields.Date(
        string="Ingreso hasta", required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True, default=lambda self: self.env.company)
    linea_ids = fields.One2many(
        'tllr_fc.rep.rentabilidad.linea', 'wizard_id', string="Líneas")

    def _generar_lineas(self):
        """Calcula el reporte y lo deja en líneas (una por OT, sin las canceladas)."""
        self.ensure_one()
        if self.fecha_hasta < self.fecha_desde:
            raise UserError("La fecha final no puede ser anterior a la inicial.")
        self.linea_ids.unlink()
        inicio = datetime.combine(self.fecha_desde, time.min)
        fin = datetime.combine(self.fecha_hasta, time.max)
        ots = self.env['tllr_fc.ot'].sudo().search([
            ('company_id', '=', self.company_id.id), ('state', '!=', 'cancelada'),
            ('fecha_ingreso', '>=', inicio), ('fecha_ingreso', '<=', fin),
        ], order='name')
        valores = []
        for tipo in TIPOS_ORDEN:
            for ot in ots.filtered(lambda o: o.tipo == tipo):
                costos = (ot.costo_propio + ot.mano_obra + ot.impuesto
                          + ot.ajustes_costo + ot.costo_garantias_origen)
                valores.append({
                    'wizard_id': self.id, 'ot_id': ot.id, 'tipo': tipo,
                    'fecha': ot.fecha_ingreso.date() if ot.fecha_ingreso else False,
                    'partner_id': ot.partner_id.id, 'vehiculo_id': ot.vehiculo_id.id,
                    'ingreso': ot.ingreso, 'costo_propio': ot.costo_propio,
                    'mano_obra': ot.mano_obra, 'impuesto': ot.impuesto,
                    'ajustes_costo': ot.ajustes_costo, 'garantias': ot.costo_garantias_origen,
                    'costos': costos, 'margen': ot.ingreso + costos,
                    'porcentaje': ((ot.ingreso + costos) / ot.ingreso * 100.0) if ot.ingreso else 0.0,
                })
        return self.env['tllr_fc.rep.rentabilidad.linea'].create(valores)

    def action_ver(self):
        """Muestra el reporte en una grilla."""
        self.ensure_one()
        self._generar_lineas()
        return {
            'type': 'ir.actions.act_window', 'name': "Rentabilidad de OT",
            'res_model': 'tllr_fc.rep.rentabilidad.linea', 'view_mode': 'list',
            'views': [(False, 'list')], 'target': 'current',
            'domain': [('wizard_id', '=', self.id)],
            'context': {'search_default_agrupar_tipo': 1, 'create': False, 'edit': False,
                        'delete': False}}

    def action_imprimir(self):
        """Descarga el reporte en PDF."""
        self.ensure_one()
        lineas = self._generar_lineas()
        if not lineas:
            raise UserError("No hay órdenes de trabajo en el rango indicado.")
        return self.env.ref('tllr_fc.action_report_rep_rentabilidad').report_action(lineas)


class TllrFcRepRentabilidadLinea(models.TransientModel):
    _name = 'tllr_fc.rep.rentabilidad.linea'
    _description = "Línea del reporte de rentabilidad"
    _order = 'id'

    wizard_id = fields.Many2one(
        'tllr_fc.wizard.rep_rentabilidad', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='wizard_id.company_id')
    currency_id = fields.Many2one(related='wizard_id.company_id.currency_id')
    ot_id = fields.Many2one('tllr_fc.ot', string="OT", ondelete='cascade')
    tipo = fields.Selection(
        [('cliente', "Cliente"), ('interno', "Interno"), ('garantia', "Garantía")],
        string="Tipo")
    fecha = fields.Date(string="Fecha de ingreso")
    partner_id = fields.Many2one('res.partner', string="Cliente")
    vehiculo_id = fields.Many2one('tllr_fc.vehiculo', string="Vehículo")
    ingreso = fields.Monetary(string="Valor de la factura", currency_field='currency_id')
    costo_propio = fields.Monetary(string="Costo de la OT", currency_field='currency_id')
    mano_obra = fields.Monetary(string="Mano de obra", currency_field='currency_id')
    impuesto = fields.Monetary(string="Impuesto", currency_field='currency_id')
    ajustes_costo = fields.Monetary(string="Ajustes", currency_field='currency_id')
    garantias = fields.Monetary(string="Garantías", currency_field='currency_id')
    costos = fields.Monetary(string="Total costos", currency_field='currency_id')
    margen = fields.Monetary(string="Margen", currency_field='currency_id')
    porcentaje = fields.Float(string="Margen %", digits=(16, 1))

    def get_datos(self):
        """Líneas agrupadas por tipo, con subtotales y total general."""
        etiquetas = dict(self._fields['tipo']._description_selection(self.env))

        def acumular(destino, linea):
            for clave in CLAVES_IMPORTE:
                destino[clave] += linea[clave]

        def vacio():
            return dict.fromkeys(CLAVES_IMPORTE, 0.0)

        def porcentaje(t):
            return (t['margen'] / t['ingreso'] * 100.0) if t['ingreso'] else 0.0

        grupos, total = [], vacio()
        for tipo in TIPOS_ORDEN:
            lineas = self.filtered(lambda l: l.tipo == tipo)
            if not lineas:
                continue
            subtotal = vacio()
            filas = []
            for linea in lineas:
                acumular(subtotal, linea)
                filas.append({
                    'ot': linea.ot_id.name, 'fecha': linea.fecha,
                    'cliente': linea.partner_id.name,
                    'vehiculo': ' '.join(filter(None, [
                        linea.vehiculo_id.chapa, linea.vehiculo_id.marca_id.name,
                        linea.vehiculo_id.modelo_id.name])),
                    **{c: linea[c] for c in CLAVES_IMPORTE}, 'porcentaje': linea.porcentaje})
            subtotal['porcentaje'] = porcentaje(subtotal)
            acumular(total, subtotal)
            grupos.append({'tipo': etiquetas.get(tipo, tipo), 'filas': filas, 'subtotal': subtotal})
        total['porcentaje'] = porcentaje(total)
        return {'grupos': grupos, 'total': total}


class TllrFcWizardRepExistencia(models.TransientModel):
    """Reporte de existencia (saldo actual) por almacén."""
    _name = 'tllr_fc.wizard.rep_existencia'
    _description = "Reporte de existencia por almacén"

    almacen_ids = fields.Many2many(
        'stock.warehouse', 'tllr_fc_rep_existencia_almacen_rel', 'wizard_id', 'almacen_id',
        string="Almacenes", help="Vacío = todos los almacenes de la compañía.")
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True, default=lambda self: self.env.company)
    linea_ids = fields.One2many('tllr_fc.rep.existencia.linea', 'wizard_id', string="Líneas")

    def _generar_lineas(self):
        """Productos almacenables con saldo distinto de cero, por almacén."""
        self.ensure_one()
        self.linea_ids.unlink()
        almacenes = self.almacen_ids or self.env['stock.warehouse'].sudo().search(
            [('company_id', '=', self.company_id.id)])
        quants = self.env['stock.quant'].sudo()
        valores = []
        for almacen in almacenes.sorted('name'):
            lectura = quants._read_group(
                [('company_id', '=', almacen.company_id.id),
                 ('location_id', 'child_of', almacen.view_location_id.id),
                 ('location_id.usage', '=', 'internal'),
                 ('product_id.is_storable', '=', True)],
                ['product_id'], ['quantity:sum'])
            filas = [(p, c) for p, c in lectura if c]
            filas.sort(key=lambda f: (f[0].default_code or '~', f[0].name))
            for producto, cantidad in filas:
                valores.append({
                    'wizard_id': self.id, 'almacen_id': almacen.id,
                    'codigo': producto.default_code or '',
                    'descripcion': producto.name, 'cantidad': cantidad,
                    'unidad': producto.uom_id.name})
        return self.env['tllr_fc.rep.existencia.linea'].create(valores)

    def action_ver(self):
        self.ensure_one()
        self._generar_lineas()
        return {
            'type': 'ir.actions.act_window', 'name': "Existencia por almacén",
            'res_model': 'tllr_fc.rep.existencia.linea', 'view_mode': 'list',
            'views': [(False, 'list')], 'target': 'current',
            'domain': [('wizard_id', '=', self.id)],
            'context': {'search_default_agrupar_almacen': 1, 'create': False, 'edit': False,
                        'delete': False}}

    def action_imprimir(self):
        self.ensure_one()
        lineas = self._generar_lineas()
        if not lineas:
            raise UserError("No hay productos con saldo en los almacenes elegidos.")
        return self.env.ref('tllr_fc.action_report_rep_existencia').report_action(lineas)


class TllrFcRepExistenciaLinea(models.TransientModel):
    _name = 'tllr_fc.rep.existencia.linea'
    _description = "Línea del reporte de existencia"
    _order = 'id'

    wizard_id = fields.Many2one(
        'tllr_fc.wizard.rep_existencia', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='wizard_id.company_id')
    almacen_id = fields.Many2one('stock.warehouse', string="Almacén")
    codigo = fields.Char(string="Código")
    descripcion = fields.Char(string="Descripción")
    cantidad = fields.Float(string="Cantidad saldo", digits='Product Unit')
    unidad = fields.Char(string="Unidad")

    def get_datos(self):
        """Líneas agrupadas por almacén (orden alfabético)."""
        resultado = []
        for almacen in self.almacen_id.sorted('name'):
            resultado.append({
                'almacen': almacen.name,
                'filas': [{'codigo': l.codigo, 'descripcion': l.descripcion,
                           'cantidad': l.cantidad, 'unidad': l.unidad}
                          for l in self.filtered(lambda l: l.almacen_id == almacen)]})
        return resultado
