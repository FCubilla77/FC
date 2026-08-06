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
    incluir_ya_generadas = fields.Boolean(
        string='Incluir ya generadas', default=False,
        help='Por defecto, "Cargar Retenciones Pendientes" solo trae las que todavía no se '
             'incluyeron en ningún archivo — así no se duplican sin querer. Tildar esta '
             'opción solo si hace falta rehacer un archivo que se perdió o no se llegó a '
             'subir a Tesaka.',
    )
    retencion_ids = fields.Many2many('local_py.retencion_emitida', string='Retenciones a incluir')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        res.setdefault('fecha_desde', today.replace(day=1))
        res.setdefault('fecha_hasta', today)
        return res

    def action_cargar_retenciones_pendientes(self):
        """Trae las Retenciones que coinciden con los filtros (Pendientes,
        y también con JSON Generado si se tildó "Incluir ya generadas"),
        sumándolas a lo que ya haya en la lista — sin pisar filas que el
        usuario haya sacado a mano, igual que "Cargar Facturas
        Pendientes" en Orden de Pago."""
        self.ensure_one()
        estados = ['pendiente', 'json_generado'] if self.incluir_ya_generadas else ['pendiente']
        domain = [
            ('company_id', '=', self.company_id.id),
            ('estado', 'in', estados),
            ('tipo_retencion', '=', 'iva'),
        ]
        if self.fecha_desde:
            domain.append(('fecha', '>=', self.fecha_desde))
        if self.fecha_hasta:
            domain.append(('fecha', '<=', self.fecha_hasta))
        if self.partner_ids:
            domain.append(('partner_id', 'in', self.partner_ids.ids))
        encontradas = self.env['local_py.retencion_emitida'].search(domain)
        self.retencion_ids = [(4, r.id) for r in encontradas]
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _condicion_compra(self, retencion):
        term = retencion.factura_id.invoice_payment_term_id
        condicion = term.l10n_py_condicion if term else False
        if condicion == 'contado':
            return 'CONTADO'
        if condicion == 'credito':
            return 'CREDITO'
        return False

    def _detalle_json(self, retencion):
        """Arma el detalle con las líneas REALES de la factura (tal como
        fue emitida) — Cantidad, Precio Unitario (con IVA incluido para
        líneas gravadas al 5%/10%, sin IVA para líneas Exentas) y Tasa —
        en vez de un resumen agrupado por tasa. El precio se calcula
        siempre a partir del Subtotal de la línea (nunca del "Precio
        Unitario" nativo de Odoo), para no depender de si el producto
        está configurado con precios IVA incluido o no."""
        detalle = []
        move = retencion.factura_id
        for linea in move.line_ids.filtered(lambda l: l.display_type == 'product'):
            if not linea.quantity:
                continue
            precio_neto_unitario = linea.price_subtotal / linea.quantity
            tasas = [round(t) for t in linea.tax_ids.mapped('amount')]
            if 10 in tasas:
                tasa_aplica, precio_unitario = '10', round(precio_neto_unitario * 1.10, 2)
            elif 5 in tasas:
                tasa_aplica, precio_unitario = '5', round(precio_neto_unitario * 1.05, 2)
            else:
                tasa_aplica, precio_unitario = '0', round(precio_neto_unitario, 2)
            detalle.append({
                'cantidad': linea.quantity,
                'tasaAplica': tasa_aplica,
                'precioUnitario': precio_unitario,
                'descripcion': (linea.name or move.name or '')[:300],
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
            'situacion': partner.l10n_py_tipo_identificacion_fiscal_id.name or False,
            'ruc': ruc or None,
            'dv': dv or None,
            'nombre': partner.name,
            'domicilio': partner.street or '',
        }

    def _transaccion_json(self, retencion):
        move = retencion.factura_id
        return {
            'condicionCompra': self._condicion_compra(retencion),
            'tipoComprobante': move.local_py_tipo_fiscal_id.tipo_comprobante_retencion or False,
            'numeroComprobanteVenta': move.l10n_py_nro_documento or '',
            'fecha': move.invoice_date.strftime('%Y-%m-%d') if move.invoice_date else '',
            'numeroTimbrado': str(move.journal_id.l10n_py_timbrado or 0).zfill(8),
        }

    def _retencion_json(self, retencion):
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
            'conceptoIva': retencion.concepto_iva_id.codigo or '',
            'ivaPorcentaje5': porcentaje if retencion.base_5 else 0,
            'ivaPorcentaje10': porcentaje if retencion.base_10 else 0,
        }

    def action_generar_json(self):
        self.ensure_one()
        retenciones = self.retencion_ids
        if not retenciones:
            raise UserError('No hay Retenciones cargadas para generar el archivo.')

        errores = []
        sin_concepto = retenciones.filtered(lambda r: not r.concepto_iva_id)
        if sin_concepto:
            errores.append(
                'Falta el Concepto IVA (Configuraciones Localización Py o ficha del '
                'Proveedor) en: %s' % ', '.join(sin_concepto.mapped('factura_id.name'))
            )
        sin_situacion = retenciones.filtered(lambda r: not r.partner_id.l10n_py_tipo_identificacion_fiscal_id)
        if sin_situacion:
            errores.append(
                'Falta el Tipo de Identificación Fiscal en la ficha del Proveedor de: %s'
                % ', '.join(sin_situacion.mapped('factura_id.name'))
            )
        sin_condicion = retenciones.filtered(lambda r: not self._condicion_compra(r))
        if sin_condicion:
            errores.append(
                'Falta la Condición (Contado/Crédito) en el Término de Pago de la Factura de: %s'
                % ', '.join(sin_condicion.mapped('factura_id.name'))
            )
        sin_tipo_comprobante = retenciones.filtered(
            lambda r: not r.factura_id.local_py_tipo_fiscal_id.tipo_comprobante_retencion
        )
        if sin_tipo_comprobante:
            errores.append(
                'Falta el "Tipo Comprobante Retención" en el Tipo Fiscal de la Factura de: %s'
                % ', '.join(sin_tipo_comprobante.mapped('factura_id.name'))
            )
        if errores:
            raise UserError(
                'No se puede generar el archivo — falta completar esta configuración:\n\n- %s'
                % '\n- '.join(errores)
            )

        ahora = fields.Datetime.now()
        registros = []
        for retencion in retenciones:
            registros.append({
                'detalle': self._detalle_json(retencion),
                'retencion': self._retencion_json(retencion),
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
        # Las Retenciones incluidas pasan a "JSON Generado" — así, si se
        # vuelve a abrir esta pantalla sin querer, "Cargar Retenciones
        # Pendientes" no las trae de nuevo (evita duplicarlas en dos
        # archivos distintos). Si hace falta rehacer el archivo, se
        # tildan con "Incluir ya generadas".
        retenciones.filtered(lambda r: r.estado == 'pendiente').write({'estado': 'json_generado'})
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }
