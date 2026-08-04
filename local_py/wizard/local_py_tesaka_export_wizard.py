# -*- coding: utf-8 -*-

import base64
import json

from odoo import api, fields, models
from odoo.exceptions import UserError


class LocalPyTesakaExportWizard(models.TransientModel):
    _name = 'local_py.tesaka_export.wizard'
    _description = 'Generar Archivo Tesaka (Retenciones)'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True, default=lambda self: self.env.company,
    )
    fecha_desde = fields.Date(string='Fecha desde', required=True)
    fecha_hasta = fields.Date(string='Fecha hasta', required=True)
    partner_ids = fields.Many2many('res.partner', string='Proveedor', help='Vacío = todos.')
    retencion_ids = fields.Many2many(
        'local_py.retencion_emitida', string='Retenciones a incluir', compute='_compute_retencion_ids',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        res.setdefault('fecha_desde', today.replace(day=1))
        res.setdefault('fecha_hasta', today)
        return res

    @api.depends('fecha_desde', 'fecha_hasta', 'partner_ids', 'company_id')
    def _compute_retencion_ids(self):
        for wiz in self:
            domain = [
                ('company_id', '=', wiz.company_id.id),
                ('estado', '=', 'pendiente'),
                ('tipo_retencion', '=', 'iva'),
            ]
            if wiz.fecha_desde:
                domain.append(('fecha', '>=', wiz.fecha_desde))
            if wiz.fecha_hasta:
                domain.append(('fecha', '<=', wiz.fecha_hasta))
            if wiz.partner_ids:
                domain.append(('partner_id', 'in', wiz.partner_ids.ids))
            wiz.retencion_ids = self.env['local_py.retencion_emitida'].search(domain)

    def _condicion_compra(self, retencion):
        return 'CREDITO' if retencion.orden_pago_factura_id.move_id.invoice_payment_term_id else 'CONTADO'

    def _detalle_json(self, retencion):
        detalle = []
        if retencion.base_5 or retencion.monto_5:
            detalle.append({
                'cantidad': 1,
                'tasaAplica': '5',
                'precioUnitario': round(retencion.base_5 * 1.05, 2),
                'descripcion': 'Retención IVA 5%% - %s' % retencion.factura_id.name,
            })
        if retencion.base_10 or retencion.monto_10:
            detalle.append({
                'cantidad': 1,
                'tasaAplica': '10',
                'precioUnitario': round(retencion.base_10 * 1.10, 2),
                'descripcion': 'Retención IVA 10%% - %s' % retencion.factura_id.name,
            })
        return detalle

    def _informado_json(self, retencion):
        partner = retencion.partner_id
        vat = (partner.vat or '').strip()
        if '-' in vat:
            ruc, dv = vat.rsplit('-', 1)
        else:
            ruc, dv = vat, ''
        return {
            'situacion': 'CONTRIBUYENTE',
            'ruc': ruc or None,
            'dv': dv or None,
            'nombre': partner.name,
            'domicilio': partner.street or '',
        }

    def _transaccion_json(self, retencion):
        move = retencion.factura_id
        return {
            'condicionCompra': self._condicion_compra(retencion),
            'tipoComprobante': 1,
            'numeroComprobanteVenta': move.l10n_py_nro_documento or '',
            'fecha': move.invoice_date.strftime('%Y-%m-%d') if move.invoice_date else '',
            'numeroTimbrado': str(move.journal_id.l10n_py_timbrado or 0).zfill(8),
        }

    def _retencion_json(self, retencion, concepto_iva):
        porcentaje = retencion.porcentaje or 0.0
        return {
            'moneda': retencion.currency_id.name,
            'fecha': retencion.fecha.strftime('%Y-%m-%d'),
            'retencionRenta': False,
            'conceptoRenta': '',
            'rentaPorcentaje': 0,
            'rentaCabezasBase': 0,
            'rentaCabezasCantidad': 0,
            'rentaToneladasBase': 0,
            'rentaToneladasCantidad': 0,
            'retencionIva': True,
            'conceptoIva': concepto_iva,
            'ivaPorcentaje5': porcentaje if retencion.base_5 else 0,
            'ivaPorcentaje10': porcentaje if retencion.base_10 else 0,
        }

    def action_generar_json(self):
        self.ensure_one()
        retenciones = self.retencion_ids
        if not retenciones:
            raise UserError('No hay Retenciones Pendientes que coincidan con los filtros elegidos.')

        config = self.env['local_py.configuracion_localizacion'].search(
            [('company_id', '=', self.company_id.id)], limit=1,
        )
        if not config or not config.l10n_py_concepto_iva_id:
            raise UserError(
                'Falta configurar el "Concepto IVA" en Configuraciones Localización Py antes '
                'de generar el archivo.'
            )
        concepto_iva = config.l10n_py_concepto_iva_id.codigo

        ahora = fields.Datetime.now()
        registros = []
        for retencion in retenciones:
            registros.append({
                'detalle': self._detalle_json(retencion),
                'retencion': self._retencion_json(retencion, concepto_iva),
                'informado': self._informado_json(retencion),
                'transaccion': self._transaccion_json(retencion),
                'atributos': {
                    'fechaCreacion': ahora.strftime('%Y-%m-%d'),
                    'fechaHoraCreacion': ahora.strftime('%Y-%m-%d %H:%M:%S'),
                },
            })

        contenido = json.dumps(registros, ensure_ascii=False, indent=2)
        nombre_archivo = 'Tesaka_Retenciones_%s_%s.json' % (
            self.fecha_desde.strftime('%Y%m%d'), self.fecha_hasta.strftime('%Y%m%d'),
        )
        attachment = self.env['ir.attachment'].create({
            'name': nombre_archivo,
            'type': 'binary',
            'datas': base64.b64encode(contenido.encode('utf-8')),
            'mimetype': 'application/json',
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
