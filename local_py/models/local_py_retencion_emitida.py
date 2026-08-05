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
    es_absorcion = fields.Boolean(
        string='Es Retención con Absorción', default=False,
        help='Proveedores del exterior (Concepto IVA distinto de IVA.1): no se le '
             'descuenta nada al Proveedor — el monto retenido pasa a ser un Gasto '
             'aparte para la Compañía. No participa del cuadre de Medios de la Orden '
             'de Pago.',
    )
    absorcion_move_id = fields.Many2one(
        'account.move', string='Asiento de Absorción', readonly=True, copy=False,
        help='Asiento contable paralelo (Débito Gasto, Crédito Retenciones a Pagar) '
             'generado por esta Retención con Absorción.',
    )
    estado = fields.Selection(
        [('pendiente', 'Pendiente'), ('levantada', 'Levantada'), ('anulada', 'Anulada')],
        string='Estado', default='pendiente', required=True, copy=False,
    )
    numero_comprobante = fields.Char(
        string='Nro. Comprobante', copy=False,
        help='Número asignado por la DNIT (Tesaka) al levantar la retención — se '
             'carga a mano por ahora.',
    )

    @api.depends('monto_5', 'monto_10')
    def _compute_monto(self):
        for retencion in self:
            retencion.monto = retencion.monto_5 + retencion.monto_10

    def action_marcar_levantada(self):
        for retencion in self:
            if retencion.estado != 'pendiente':
                raise UserError('Solo se puede marcar como Levantada una Retención Pendiente.')
            if not retencion.numero_comprobante:
                raise UserError('Cargue el Nro. Comprobante antes de marcarla como Levantada.')
            retencion.estado = 'levantada'

    def action_marcar_anulada(self):
        for retencion in self:
            if retencion.estado != 'levantada':
                raise UserError('Solo se puede anular una Retención que esté Levantada.')
            retencion.estado = 'anulada'

    def unlink(self):
        for retencion in self:
            if retencion.estado != 'pendiente':
                raise UserError(
                    'No se puede eliminar una Retención %s — solo se pueden eliminar '
                    'las que están Pendientes (se borran solas al Deshacer Confirmación '
                    'de su Orden de Pago).' % dict(retencion._fields['estado'].selection).get(retencion.estado)
                )
        return super().unlink()
