# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class LocalPyRetencionEmitida(models.Model):
    _name = 'local_py.retencion_emitida'
    _description = 'Retención Emitida'
    _order = 'fecha desc'

    def write(self, vals):
        result = super().write(vals)
        if 'numero_comprobante' in vals:
            for retencion in self:
                medio = self.env['local_py.orden_pago.medio'].search([
                    ('orden_pago_id', '=', retencion.orden_pago_id.id),
                    ('retencion_factura_id', '=', retencion.orden_pago_factura_id.id),
                ], limit=1)
                if medio:
                    medio.nro_documento = vals['numero_comprobante']
        return result

    orden_pago_id = fields.Many2one('local_py.orden_pago', string='Orden de Pago', required=True, ondelete='cascade')
    orden_pago_factura_id = fields.Many2one(
        'local_py.orden_pago.factura', string='Factura (Orden de Pago)', required=True, ondelete='cascade',
    )
    company_id = fields.Many2one(related='orden_pago_id.company_id', string='Compañía', store=True)
    partner_id = fields.Many2one(related='orden_pago_id.partner_id', string='Proveedor', store=True)
    factura_id = fields.Many2one(
        related='orden_pago_factura_id.move_line_id.move_id', string='Factura', store=True,
    )
    fecha = fields.Date(string='Fecha', required=True)
    tipo_retencion = fields.Selection(
        [('iva', 'IVA'), ('renta', 'Renta')], string='Tipo', required=True, default='iva',
    )
    currency_id = fields.Many2one(related='orden_pago_id.currency_id', string='Moneda')
    base_5 = fields.Monetary(string='Base Imponible 5%', currency_field='currency_id')
    monto_5 = fields.Monetary(string='Monto Retenido 5%', currency_field='currency_id')
    base_10 = fields.Monetary(string='Base Imponible 10%', currency_field='currency_id')
    monto_10 = fields.Monetary(string='Monto Retenido 10%', currency_field='currency_id')
    monto = fields.Monetary(
        string='Monto Retenido', currency_field='currency_id', compute='_compute_monto', store=True,
        help='Suma de lo retenido al 5% y al 10% — es el monto real que se resta al '
             'Proveedor (coincide con el importe de la fila de Medios).',
    )
    porcentaje = fields.Float(string='Porcentaje', digits=(5, 2))
    company_currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda de la Empresa')
    monto_gs = fields.Monetary(
        string='Monto Retenido (Gs.)', currency_field='company_currency_id',
        help='Monto declarado ante la DNIT — siempre en Guaraníes, convertido a la '
             'Cotización de la Orden de Pago.',
    )
    concepto_iva_id = fields.Many2one(
        'local_py.concepto_iva', string='Concepto IVA',
        help='Código exigido por la DNIT (Tesaka) para clasificar esta Retención — se '
             'copia del configurado en Configuraciones Localización Py al momento de '
             'Confirmar.',
    )
    es_absorcion_iva = fields.Boolean(
        string='IVA con Absorción', default=False,
        help='Proveedores del exterior que tienen "Se Absorbe IVA" tildado en su ficha: '
             'no se le descuenta nada al Proveedor por el IVA — el monto retenido pasa '
             'a ser un Gasto aparte para la Compañía. No participa del cuadre de Medios '
             'de la Orden de Pago.',
    )
    absorcion_move_id_iva = fields.Many2one(
        'account.move', string='Asiento de Absorción (IVA)', readonly=True, copy=False,
        help='Asiento contable paralelo (Débito Gasto, Crédito Retenciones a Pagar) '
             'generado por la Retención IVA con Absorción.',
    )
    concepto_renta_id = fields.Many2one(
        'local_py.concepto_renta_no_residente', string='Concepto Renta No Residente',
        help='Código exigido por la DNIT (Tesaka) para clasificar la Retención Renta — '
             'se copia del Concepto cargado en la Factura al momento de Confirmar.',
    )
    base_renta = fields.Monetary(string='Base Imponible Renta', currency_field='currency_id')
    monto_renta = fields.Monetary(string='Monto Retenido Renta', currency_field='currency_id')
    monto_renta_gs = fields.Monetary(
        string='Monto Retenido Renta (Gs.)', currency_field='company_currency_id',
        help='Monto de Renta declarado ante la DNIT — siempre en Guaraníes, convertido '
             'a la Cotización de la Orden de Pago.',
    )
    factura_currency_id = fields.Many2one(related='factura_id.currency_id', string='Moneda de la Factura')
    iva_5_cubierto_aporte = fields.Monetary(
        string='Aporte al acumulado IVA 5%', currency_field='factura_currency_id', copy=False,
        help='Cuánto sumó esta Retención al acumulado "IVA 5% ya cubierto" de la cuota '
             '(en la moneda propia de la Factura) — se usa para poder revertirlo con '
             'precisión si esta Retención se anula o su Orden de Pago se revierte.',
    )
    iva_10_cubierto_aporte = fields.Monetary(
        string='Aporte al acumulado IVA 10%', currency_field='factura_currency_id', copy=False,
        help='Mismo criterio que "Aporte al acumulado IVA 5%", para el tramo al 10%.',
    )
    renta_importe_cubierto_aporte = fields.Monetary(
        string='Aporte al acumulado Renta', currency_field='factura_currency_id', copy=False,
        help='Cuánto sumó esta Retención al acumulado "Importe ya cubierto (Renta)" de '
             'la cuota (en la moneda propia de la Factura).',
    )
    es_absorcion_renta = fields.Boolean(
        string='Renta con Absorción', default=False,
        help='Proveedores del exterior que tienen "Se Absorbe Renta" tildado en su '
             'ficha: no se le descuenta nada al Proveedor por la Renta — el monto '
             'retenido pasa a ser un Gasto aparte para la Compañía.',
    )
    absorcion_move_id_renta = fields.Many2one(
        'account.move', string='Asiento de Absorción (Renta)', readonly=True, copy=False,
        help='Asiento contable paralelo (Débito Gasto, Crédito Retenciones a Pagar) '
             'generado por la Retención Renta con Absorción.',
    )
    estado = fields.Selection(
        [
            ('pendiente', 'Pendiente'),
            ('json_generado', 'JSON Generado'),
            ('levantada', 'Levantada'),
            ('anulada', 'Anulada'),
        ],
        string='Estado', default='pendiente', required=True, copy=False,
        help='Pendiente: todavía no se incluyó en ningún archivo para la DNIT. JSON '
             'Generado: ya se incluyó en un archivo (evita duplicarla en otro archivo sin '
             'querer) — todavía no confirmado por la DNIT. Levantada: la DNIT ya la '
             'aceptó. Anulada: la DNIT la anuló.',
    )
    numero_comprobante = fields.Char(
        string='Nro. Comprobante', copy=False,
        help='Número asignado por la DNIT (Tesaka) al levantar la retención — se '
             'carga a mano por ahora, o automáticamente al procesar el archivo Excel '
             'de retenciones de Tesaka.',
    )
    fecha_anulacion = fields.Date(
        string='Fecha de Anulación', copy=False,
        help='Fecha en que la DNIT anuló este comprobante de retención (columna "Fecha '
             'de Anulación" del Excel de Tesaka).',
    )
    control = fields.Char(
        string='Control', copy=False,
        help='Código de control que asigna la DNIT a cada comprobante (columna '
             '"Control" del Excel de Tesaka).',
    )

    @api.depends('monto_5', 'monto_10')
    def _compute_monto(self):
        for retencion in self:
            retencion.monto = retencion.monto_5 + retencion.monto_10

    monto_total = fields.Monetary(
        string='Monto Retenido Total', currency_field='currency_id', compute='_compute_monto_total',
        help='Suma de la Retención IVA y la Retención Renta de este mismo comprobante '
             '(cuando incluye ambas) — a título informativo, ya que cada una puede '
             'terminar en un asiento contable distinto según se absorba o se descuente.',
    )
    monto_total_gs = fields.Monetary(
        string='Monto Retenido Total (Gs.)', currency_field='company_currency_id',
        compute='_compute_monto_total',
    )

    @api.depends('monto', 'monto_gs', 'monto_renta', 'monto_renta_gs')
    def _compute_monto_total(self):
        for retencion in self:
            retencion.monto_total = retencion.monto + retencion.monto_renta
            retencion.monto_total_gs = retencion.monto_gs + retencion.monto_renta_gs

    def action_marcar_levantada(self):
        for retencion in self:
            if retencion.estado not in ('pendiente', 'json_generado'):
                raise UserError('Solo se puede marcar como Levantada una Retención Pendiente o con JSON Generado.')
            if not retencion.numero_comprobante:
                raise UserError('Cargue el Nro. Comprobante antes de marcarla como Levantada.')
            retencion.estado = 'levantada'

    def action_marcar_anulada(self):
        """Al anular una Retención Levantada o con JSON Generado (a mano
        o al procesar el Excel de Tesaka), hay que decidir qué pasa
        después: volver a incluirla en el próximo archivo JSON
        (Reprocesar), o deshacer toda la Orden de Pago. Se abre el
        wizard que ofrece esas 2 opciones en vez de decidir solo."""
        for retencion in self:
            if retencion.estado not in ('levantada', 'json_generado'):
                raise UserError('Solo se puede anular una Retención Levantada o con JSON Generado.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Retención Anulada — ¿Qué hacemos?',
            'res_model': 'local_py.retencion_anular.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_retencion_ids': self.ids},
        }

    def action_resolver_anulacion(self):
        """Para Retenciones que llegaron marcadas como Anuladas directo
        desde el Excel de Tesaka (sin pasar por el botón "Anular") — abre
        el mismo wizard de 2 opciones para decidir qué hacer."""
        for retencion in self:
            if retencion.estado != 'anulada':
                raise UserError('Esta acción es solo para Retenciones que ya están Anuladas.')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Retención Anulada — ¿Qué hacemos?',
            'res_model': 'local_py.retencion_anular.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_retencion_ids': self.ids},
        }

    def unlink(self):
        for retencion in self:
            if retencion.estado != 'pendiente':
                raise UserError(
                    'No se puede eliminar una Retención %s — solo se pueden eliminar '
                    'las que están Pendientes (se borran solas al Deshacer Confirmación '
                    'de su Orden de Pago).' % dict(retencion._fields['estado'].selection).get(retencion.estado)
                )
        return super().unlink()
