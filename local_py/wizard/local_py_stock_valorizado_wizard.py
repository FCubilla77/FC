# -*- coding: utf-8 -*-

from odoo import api, fields, models

from ..models.local_py_libro_report import fmt_pyg


class LocalPyStockValorizadoWizard(models.TransientModel):
    _name = 'local_py.stock_valorizado.wizard'
    _description = 'Asistente Movimiento de Stock Valorizado'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company,
    )
    fecha_desde = fields.Date(string='Fecha desde', required=True)
    fecha_hasta = fields.Date(string='Fecha hasta', required=True)
    product_ids = fields.Many2many(
        'product.product', string='Productos',
        help='Dejar vacío para incluir todos los productos.',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        res.setdefault('fecha_desde', today.replace(day=1))
        res.setdefault('fecha_hasta', today)
        return res

    def action_ver_reporte(self):
        self.ensure_one()
        builder = self.env['local_py.libro_report.builder']
        rows = builder._build_stock_valorizado_rows(
            self.company_id, self.fecha_desde, self.fecha_hasta, self.product_ids,
        )
        paginas = builder._paginar_simple(rows)
        render_context = {
            'company': self.company_id,
            'fecha_desde': self.fecha_desde,
            'fecha_hasta': self.fecha_hasta,
            'paginas': paginas,
            'pagina_inicial': 1,
            'total_paginas_libro': len(paginas) or 1,
            'rubrica': self.env['local_py.rubrica'],
            'fmt_pyg': fmt_pyg,
        }
        report_action = self.env.ref('local_py.action_report_stock_valorizado_html')
        html_content, _ = report_action.with_context(
            local_py_libro_render_data=render_context
        )._render_qweb_html(report_action.report_name, [self.company_id.id])

        import base64
        attachment = self.env['ir.attachment'].create({
            'name': 'Movimiento de Stock Valorizado (vista de control).html',
            'type': 'binary',
            'datas': base64.b64encode(html_content),
            'mimetype': 'text/html',
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=false' % attachment.id,
            'target': 'new',
        }

    def action_descargar_excel(self):
        self.ensure_one()
        builder = self.env['local_py.libro_report.builder']
        rows = builder._build_stock_valorizado_rows(
            self.company_id, self.fecha_desde, self.fecha_hasta, self.product_ids,
        )

        import base64
        import io

        import xlsxwriter

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Stock Valorizado')

        fmt_header = workbook.add_format({
            'bold': True, 'bg_color': '#EEEEEE', 'border': 1, 'align': 'center',
        })
        fmt_producto = workbook.add_format({'bold': True, 'bg_color': '#DDDDDD'})
        fmt_cuenta = workbook.add_format({'bold': True, 'bg_color': '#F0F0F0'})
        fmt_saldo_inicial = workbook.add_format({'italic': True})
        fmt_saldo_inicial_num = workbook.add_format({'italic': True, 'num_format': '#,##0', 'align': 'right'})
        fmt_saldo_inicial_qty = workbook.add_format({'italic': True, 'num_format': '#,##0.00', 'align': 'right'})
        fmt_texto = workbook.add_format({})
        fmt_qty = workbook.add_format({'num_format': '#,##0.00', 'align': 'right'})
        fmt_money = workbook.add_format({'num_format': '#,##0', 'align': 'right'})
        fmt_total_texto = workbook.add_format({'italic': True})
        fmt_total_qty = workbook.add_format({'italic': True, 'num_format': '#,##0.00', 'align': 'right'})
        fmt_total_money = workbook.add_format({'italic': True, 'num_format': '#,##0', 'align': 'right'})
        fmt_total_producto_texto = workbook.add_format({'bold': True})
        fmt_total_producto_qty = workbook.add_format({'bold': True, 'num_format': '#,##0.00', 'align': 'right'})
        fmt_total_producto_money = workbook.add_format({'bold': True, 'num_format': '#,##0', 'align': 'right'})

        headers = [
            'Fecha', 'Fecha Sistema', 'Referencia', 'Nro. Fiscal', 'Cantidad',
            'Costo Unitario', 'Costo Total', 'Débito', 'Crédito', 'Valor Acumulado',
            'Cantidad Acumulada', 'Costo Promedio',
        ]
        for col, header in enumerate(headers):
            sheet.write(0, col, header, fmt_header)
        anchos = [12, 20, 20, 10, 10, 14, 14, 12, 12, 15, 16, 14]
        for col, ancho in enumerate(anchos):
            sheet.set_column(col, col, ancho)

        fila_excel = 1
        for fila in rows:
            if fila['tipo'] == 'producto':
                sheet.merge_range(fila_excel, 0, fila_excel, 11, fila['nombre'], fmt_producto)
            elif fila['tipo'] == 'cuenta':
                texto = '%s - %s' % (fila['cuenta'], fila['nombre_cuenta'])
                sheet.merge_range(fila_excel, 0, fila_excel, 11, texto, fmt_cuenta)
            elif fila['tipo'] == 'saldo_inicial':
                sheet.merge_range(fila_excel, 0, fila_excel, 8, fila['referencia'], fmt_saldo_inicial)
                sheet.write_number(fila_excel, 9, fila['saldo'], fmt_saldo_inicial_num)
                sheet.write_number(fila_excel, 10, fila['saldo_cantidad'], fmt_saldo_inicial_qty)
                if fila['costo_promedio'] is not False:
                    sheet.write_number(fila_excel, 11, fila['costo_promedio'], fmt_saldo_inicial_qty)
                else:
                    sheet.write(fila_excel, 11, '', fmt_saldo_inicial)
            elif fila['tipo'] == 'linea':
                sheet.write(fila_excel, 0, fila['fecha'].strftime('%d/%m/%Y') if fila['fecha'] else '', fmt_texto)
                sheet.write(
                    fila_excel, 1,
                    fila['fecha_sistema'].strftime('%d/%m/%Y %H:%M:%S') if fila['fecha_sistema'] else '', fmt_texto,
                )
                sheet.write(fila_excel, 2, fila['referencia'], fmt_texto)
                sheet.write(fila_excel, 3, fila['nro_fiscal'] or '', fmt_texto)
                sheet.write_number(fila_excel, 4, fila['cantidad'], fmt_qty)
                sheet.write_number(fila_excel, 5, fila['costo_unitario'], fmt_money)
                sheet.write_number(fila_excel, 6, fila['costo_total'], fmt_money)
                sheet.write_number(fila_excel, 7, fila['debe'], fmt_money)
                sheet.write_number(fila_excel, 8, fila['haber'], fmt_money)
                sheet.write_number(fila_excel, 9, fila['saldo'], fmt_money)
                sheet.write_number(fila_excel, 10, fila['saldo_cantidad'], fmt_qty)
                if fila['costo_promedio'] is not False:
                    sheet.write_number(fila_excel, 11, fila['costo_promedio'], fmt_qty)
                else:
                    sheet.write(fila_excel, 11, '', fmt_texto)
            elif fila['tipo'] == 'total_cuenta':
                sheet.merge_range(fila_excel, 0, fila_excel, 3, 'Total por cuenta', fmt_total_texto)
                sheet.write_number(fila_excel, 4, fila['total_cantidad'], fmt_total_qty)
                sheet.write(fila_excel, 5, '', fmt_total_texto)
                sheet.write(fila_excel, 6, '', fmt_total_texto)
                sheet.write_number(fila_excel, 7, fila['total_debe'], fmt_total_money)
                sheet.write_number(fila_excel, 8, fila['total_haber'], fmt_total_money)
                sheet.write_number(fila_excel, 9, fila['saldo'], fmt_total_money)
                sheet.write_number(fila_excel, 10, fila['saldo_cantidad'], fmt_total_qty)
                if fila['costo_promedio'] is not False:
                    sheet.write_number(fila_excel, 11, fila['costo_promedio'], fmt_total_qty)
                else:
                    sheet.write(fila_excel, 11, '', fmt_total_texto)
            elif fila['tipo'] == 'total_producto':
                sheet.merge_range(fila_excel, 0, fila_excel, 3, 'Total por producto', fmt_total_producto_texto)
                sheet.write_number(fila_excel, 4, fila['total_cantidad'], fmt_total_producto_qty)
                sheet.write(fila_excel, 5, '', fmt_total_producto_texto)
                sheet.write(fila_excel, 6, '', fmt_total_producto_texto)
                sheet.write_number(fila_excel, 7, fila['total_debe'], fmt_total_producto_money)
                sheet.write_number(fila_excel, 8, fila['total_haber'], fmt_total_producto_money)
                sheet.write_number(fila_excel, 9, fila['saldo'], fmt_total_producto_money)
                sheet.write_number(fila_excel, 10, fila['saldo_cantidad'], fmt_total_producto_qty)
                if fila['costo_promedio'] is not False:
                    sheet.write_number(fila_excel, 11, fila['costo_promedio'], fmt_total_producto_qty)
                else:
                    sheet.write(fila_excel, 11, '', fmt_total_producto_texto)
            fila_excel += 1

        workbook.close()
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': 'Movimiento_Stock_Valorizado_%s_%s.xlsx' % (
                self.fecha_desde.strftime('%Y%m%d'), self.fecha_hasta.strftime('%Y%m%d'),
            ),
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
