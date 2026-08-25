# -*- coding: utf-8 -*-

import base64
import io

from odoo import api, fields, models
from odoo.exceptions import UserError


class LocalPyCuentaCorrienteWizard(models.TransientModel):
    _name = 'local_py.cuenta_corriente_wizard'
    _description = 'Imprimir Estado de Cuenta Corriente'

    partner_id = fields.Many2one('res.partner', string='Proveedor/Cliente', required=True)
    fecha_desde = fields.Date(string='Fecha Desde')
    fecha_hasta = fields.Date(string='Fecha Hasta')

    def _fecha_emision_texto(self):
        """Momento real en que se generó el PDF, convertido al huso
        horario de quien lo está imprimiendo (igual criterio que ya
        usamos para la Fecha de Creación de cada línea)."""
        self.ensure_one()
        ahora = fields.Datetime.context_timestamp(self, fields.Datetime.now())
        return ahora.strftime('%d/%m/%Y %H:%M')

    def _fmt(self, valor, currency=None):
        """Mismo criterio de formato que ya usa Orden de Pago: separador de
        miles con punto (estilo Paraguay), y decimal con coma si hiciera falta."""
        decimales = currency.decimal_places if currency else 2
        texto = '{:,.{prec}f}'.format(valor or 0.0, prec=decimales)
        entero, sep, decimal = texto.partition('.')
        entero = entero.replace(',', '.')
        return entero + (',' + decimal if sep else '')

    def _obtener_datos(self):
        """Arma la estructura Compañía > Tipo (Cliente/Proveedor) > Moneda,
        separando en secciones distintas las cuentas a cobrar (Cliente) de
        las cuentas a pagar (Proveedor) — necesario para un Contacto que es
        Cliente y Proveedor a la vez. Dentro de cada grupo: Saldo Inicial
        (todo lo anterior a Fecha Desde, resumido en una sola línea) y el
        detalle ordenado cronológicamente (Fecha contable, y Fecha/Hora de
        creación como desempate).

        El signo del Saldo depende del Tipo del grupo: Cliente = Débito -
        Crédito (positivo = a favor de la Empresa, lo que el Cliente
        debe — estándar de Cuentas por Cobrar); Proveedor = Crédito -
        Débito (positivo = a favor del Proveedor, lo que la Empresa
        debe)."""
        self.ensure_one()
        Line = self.env['account.move.line']
        domain_base = [
            ('partner_id', '=', self.partner_id.id),
            ('account_id.account_type', 'in', ('liability_payable', 'asset_receivable')),
            ('move_id.state', '=', 'posted'),
            ('display_type', 'not in', ('line_section', 'line_note')),
        ]
        if self.fecha_hasta:
            domain_base.append(('date', '<=', self.fecha_hasta))
        todas = Line.search(domain_base, order='date, create_date, id')

        etiqueta_tipo = {'cliente': 'Cliente', 'proveedor': 'Proveedor'}
        orden_tipo = {'cliente': 0, 'proveedor': 1}

        grupos = {}
        for linea in todas:
            tipo = 'cliente' if linea.account_id.account_type == 'asset_receivable' else 'proveedor'
            clave = (linea.company_id, tipo, linea.currency_id or linea.company_id.currency_id)
            grupos.setdefault(clave, []).append(linea)

        resultado = []
        for (company, tipo, currency), lineas in sorted(
            grupos.items(), key=lambda kv: (kv[0][0].name, orden_tipo[kv[0][1]], kv[0][2].name)
        ):
            signo = 1 if tipo == 'cliente' else -1
            anteriores = lineas if not self.fecha_desde else [l for l in lineas if l.date < self.fecha_desde]
            detalle_lineas = lineas if not self.fecha_desde else [l for l in lineas if l.date >= self.fecha_desde]
            saldo_inicial = signo * sum(l.debit - l.credit for l in anteriores)

            saldo = saldo_inicial
            detalle = []
            for linea in detalle_lineas:
                saldo += signo * (linea.debit - linea.credit)
                detalle.append({
                    'fecha': linea.date,
                    'fecha_creacion': fields.Datetime.context_timestamp(self, linea.create_date),
                    'diario': linea.journal_id.name,
                    'comentario': linea.move_id.l10n_py_comentario or linea.name or '',
                    'debito': linea.debit,
                    'credito': linea.credit,
                    'saldo': saldo,
                })
            resultado.append({
                'company': company,
                'tipo': tipo,
                'tipo_label': etiqueta_tipo[tipo],
                'currency': currency,
                'saldo_inicial': saldo_inicial,
                'detalle': detalle,
                'saldo_final': saldo,
            })
        return resultado

    def action_generar_pdf(self):
        self.ensure_one()
        return self.env.ref('local_py.action_report_cuenta_corriente').report_action(self)

    def action_generar_excel(self):
        self.ensure_one()
        try:
            import xlsxwriter
        except ImportError:
            raise UserError('Falta la librería "xlsxwriter" en el servidor para poder exportar a Excel.')

        datos = self._obtener_datos()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Cuenta Corriente')
        fmt_titulo = workbook.add_format({'bold': True, 'font_size': 12})
        fmt_grupo = workbook.add_format({'bold': True, 'bg_color': '#EEEEEE'})
        fmt_encabezado = workbook.add_format({'bold': True, 'border': 1})
        fmt_numero = workbook.add_format({'num_format': '#,##0.00'})
        fmt_fecha = workbook.add_format({'num_format': 'dd/mm/yyyy'})

        sheet.write(0, 0, 'Estado de Cuenta Corriente — %s' % self.partner_id.display_name, fmt_titulo)
        fila = 2
        for grupo in datos:
            sheet.write(
                fila, 0,
                '%s — %s — %s' % (grupo['company'].name, grupo['tipo_label'], grupo['currency'].name),
                fmt_grupo,
            )
            fila += 1
            encabezados = ['Fecha', 'Fecha de Creación', 'Diario', 'Comentario', 'Débito', 'Crédito', 'Saldo']
            for col, titulo in enumerate(encabezados):
                sheet.write(fila, col, titulo, fmt_encabezado)
            fila += 1
            sheet.write(fila, 3, 'Saldo Inicial', fmt_encabezado)
            sheet.write(fila, 6, grupo['saldo_inicial'], fmt_numero)
            fila += 1
            for linea in grupo['detalle']:
                sheet.write_datetime(fila, 0, linea['fecha'], fmt_fecha)
                sheet.write(fila, 1, linea['fecha_creacion'].strftime('%d/%m/%Y %H:%M'))
                sheet.write(fila, 2, linea['diario'])
                sheet.write(fila, 3, linea['comentario'])
                sheet.write(fila, 4, linea['debito'], fmt_numero)
                sheet.write(fila, 5, linea['credito'], fmt_numero)
                sheet.write(fila, 6, linea['saldo'], fmt_numero)
                fila += 1
            fila += 1
        workbook.close()
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': 'Estado de Cuenta - %s.xlsx' % self.partner_id.display_name,
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
