# -*- coding: utf-8 -*-
import base64
import csv
import io
import zipfile

from odoo import models, fields, api
from odoo.exceptions import UserError


class LocalPyLibroMarangatuWizard(models.TransientModel):
    _name = 'local_py.libro_marangatu.wizard'
    _description = 'Asistente Libro Ventas / Libro Compras (Marangatu)'

    tipo_registro = fields.Selection(
        [('ventas', 'Ventas'), ('compras', 'Compras')],
        string='Tipo de Registro', required=True,
    )
    date_from = fields.Date(string='Fecha desde', required=True)
    date_to = fields.Date(string='Fecha hasta', required=True)
    periodicidad = fields.Selection(
        [('mensual', 'Mensual (obligación 955)'), ('anual', 'Anual (obligación 956)')],
        string='Periodicidad', default='mensual', required=True,
    )
    identificador = fields.Char(
        string='Identificador de archivo', size=5, default='V0001', required=True,
        help='Hasta 5 caracteres alfanuméricos. Debe ser único para cada archivo '
             'presentado en el mismo período (ej. V0001, V0002).',
    )
    file_data = fields.Binary(string='Archivo Marangatu (.zip)', readonly=True)
    file_name = fields.Char(string='Nombre de archivo', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        res.setdefault('date_from', today.replace(day=1))
        res.setdefault('date_to', today)
        return res

    def _get_move_types(self):
        self.ensure_one()
        return ('out_invoice', 'out_refund') if self.tipo_registro == 'ventas' else ('in_invoice', 'in_refund')

    def _get_domain(self):
        self.ensure_one()
        return [
            ('move_type', 'in', self._get_move_types()),
            ('state', '=', 'posted'),
            ('invoice_date', '>=', self.date_from),
            ('invoice_date', '<=', self.date_to),
        ]

    def action_view_report(self):
        self.ensure_one()
        is_ventas = self.tipo_registro == 'ventas'
        view_xml_id = (
            'local_py.view_move_list_libro_ventas_marangatu' if is_ventas
            else 'local_py.view_move_list_libro_compras_marangatu'
        )
        return {
            'name': 'Libro Ventas' if is_ventas else 'Libro Compras',
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list',
            'views': [(self.env.ref(view_xml_id).id, 'list')],
            'domain': self._get_domain(),
        }

    def action_generate_file(self):
        """Genera el archivo real de importación a Marangatu: CSV sin
        encabezados, comprimido en ZIP, con el nombre de archivo oficial
        <RUC sin DV>_REG_MMAAAA|AAAA_XXXXX.zip."""
        self.ensure_one()
        moves = self.env['account.move'].search(self._get_domain(), order='invoice_date, id')
        if not moves:
            raise UserError('No hay comprobantes confirmados en el rango de fechas seleccionado.')

        company = self.env.company
        ruc_sin_dv = (company.vat or '').split('-')[0].strip()
        if not ruc_sin_dv:
            raise UserError(
                'La compañía no tiene RUT configurado; no se puede generar el '
                'nombre del archivo (se necesita para el prefijo <RUC>_REG_...).'
            )

        periodo = self.date_from.strftime('%m%Y') if self.periodicidad == 'mensual' else self.date_from.strftime('%Y')
        base_name = '%s_REG_%s_%s' % (ruc_sin_dv, periodo, self.identificador)

        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=',', lineterminator='\r\n')
        for move in moves:
            writer.writerow(move.l10n_py_mkt_row_values())
        csv_bytes = buffer.getvalue().encode('utf-8')

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr('%s.csv' % base_name, csv_bytes)

        self.file_data = base64.b64encode(zip_buffer.getvalue())
        self.file_name = '%s.zip' % base_name

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'local_py.libro_marangatu.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'views': [(self.env.ref('local_py.view_libro_marangatu_wizard_form').id, 'form')],
        }
