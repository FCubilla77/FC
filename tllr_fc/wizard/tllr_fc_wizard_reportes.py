# -*- coding: utf-8 -*-
from datetime import datetime, time

from odoo import api, fields, models
from odoo.exceptions import UserError


class TllrFcWizardRepRentabilidad(models.TransientModel):
    """Reporte de rentabilidad de las OT por rango de fecha de ingreso."""
    _name = 'tllr_fc.wizard.rep_rentabilidad'
    _description = "Reporte de rentabilidad de OT"

    fecha_desde = fields.Date(
        string="Ingreso desde", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1))
    fecha_hasta = fields.Date(
        string="Ingreso hasta", required=True, default=fields.Date.context_today)
    company_id = fields.Many2one(
        'res.company', string="Compañía", required=True, default=lambda self: self.env.company)

    def action_imprimir(self):
        self.ensure_one()
        if self.fecha_hasta < self.fecha_desde:
            raise UserError("La fecha final no puede ser anterior a la inicial.")
        return self.env.ref('tllr_fc.action_report_rep_rentabilidad').report_action(self)

    def get_datos(self):
        """Devuelve las OT agrupadas por tipo, con subtotales y total general."""
        self.ensure_one()
        inicio = datetime.combine(self.fecha_desde, time.min)
        fin = datetime.combine(self.fecha_hasta, time.max)
        ots = self.env['tllr_fc.ot'].sudo().search([
            ('company_id', '=', self.company_id.id),
            ('fecha_ingreso', '>=', inicio), ('fecha_ingreso', '<=', fin),
        ], order='name')
        etiquetas = dict(self.env['tllr_fc.ot']._fields['tipo']._description_selection(self.env))
        claves = ('ingreso', 'costo_propio', 'mano_obra', 'impuesto', 'ajustes_costo',
                  'garantias', 'costos', 'margen')

        def vacio():
            return dict.fromkeys(claves, 0.0)

        def porcentaje(t):
            return (t['margen'] / t['ingreso'] * 100.0) if t['ingreso'] else 0.0

        grupos, total = [], vacio()
        for tipo in ('cliente', 'garantia', 'interno'):
            filas, subtotal = [], vacio()
            for ot in ots.filtered(lambda o: o.tipo == tipo):
                fila = {
                    'ot': ot.name,
                    'fecha': ot.fecha_ingreso.date() if ot.fecha_ingreso else False,
                    'cliente': ot.partner_id.name,
                    'vehiculo': ' '.join(filter(None, [
                        ot.vehiculo_id.chapa, ot.vehiculo_id.marca_id.name,
                        ot.vehiculo_id.modelo_id.name])),
                    'ingreso': ot.ingreso, 'costo_propio': ot.costo_propio,
                    'mano_obra': ot.mano_obra, 'impuesto': ot.impuesto,
                    'ajustes_costo': ot.ajustes_costo, 'garantias': ot.costo_garantias_origen,
                }
                fila['costos'] = (fila['costo_propio'] + fila['mano_obra'] + fila['impuesto']
                                  + fila['ajustes_costo'] + fila['garantias'])
                fila['margen'] = fila['ingreso'] + fila['costos']
                fila['porcentaje'] = porcentaje(fila)
                for clave in claves:
                    subtotal[clave] += fila[clave]
                filas.append(fila)
            if not filas:
                continue
            subtotal['porcentaje'] = porcentaje(subtotal)
            for clave in claves:
                total[clave] += subtotal[clave]
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

    def action_imprimir(self):
        self.ensure_one()
        return self.env.ref('tllr_fc.action_report_rep_existencia').report_action(self)

    def get_datos(self):
        """Devuelve, por almacén, los productos almacenables con saldo distinto de cero."""
        self.ensure_one()
        almacenes = self.almacen_ids or self.env['stock.warehouse'].sudo().search(
            [('company_id', '=', self.company_id.id)])
        quants = self.env['stock.quant'].sudo()
        resultado = []
        for almacen in almacenes.sorted('name'):
            lectura = quants._read_group(
                [('company_id', '=', almacen.company_id.id),
                 ('location_id', 'child_of', almacen.view_location_id.id),
                 ('location_id.usage', '=', 'internal'),
                 ('product_id.is_storable', '=', True)],
                ['product_id'], ['quantity:sum'])
            filas = []
            for producto, cantidad in lectura:
                if not cantidad:
                    continue
                filas.append({
                    'codigo': producto.default_code or '',
                    'descripcion': producto.with_context(display_default_code=False).display_name,
                    'cantidad': cantidad, 'unidad': producto.uom_id.name})
            filas.sort(key=lambda f: (f['codigo'] or '~', f['descripcion']))
            resultado.append({'almacen': almacen.name, 'filas': filas})
        return resultado
