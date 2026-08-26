# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError


class LocalPyRetencionRecibida(models.Model):
    _name = 'local_py.retencion_recibida'
    _description = 'Retención Recibida'
    _order = 'fecha desc'

    recibo_id = fields.Many2one('local_py.recibo', string='Recibo', required=True, ondelete='cascade')
    recibo_factura_id = fields.Many2one(
        'local_py.recibo.factura', string='Factura (Recibo)', required=True, ondelete='cascade',
    )
    company_id = fields.Many2one(related='recibo_id.company_id', string='Compañía', store=True)
    partner_id = fields.Many2one(related='recibo_id.partner_id', string='Cliente', store=True)
    factura_id = fields.Many2one(
        related='recibo_factura_id.move_line_id.move_id', string='Factura', store=True,
        help='La Factura del Cliente sobre la que se informó esta Retención — una '
             'misma Factura puede tener más de una Retención Recibida a lo largo del '
             'tiempo (en distintos Recibos, por pagos parciales).',
    )
    fecha = fields.Date(string='Fecha', required=True, help='Fecha del Recibo que la generó.')
    currency_id = fields.Many2one(related='recibo_factura_id.currency_id', string='Moneda')

    importe = fields.Monetary(
        string='Importe', currency_field='currency_id',
        help='Lo que se cargó en la columna "Importe Retención" de la Factura, al '
             'Confirmar el Recibo — es lo que ya está contabilizado en la Cuenta '
             '"Retenido a Confirmar".',
    )
    importe_dnit = fields.Monetary(
        string='Importe DNIT', currency_field='currency_id', copy=False,
        help='Importe oficial informado por el archivo de Marangatu de la DNIT (Fase '
             '2) — se completa recién al procesar ese archivo. Si difiere del '
             'Importe, la diferencia se ajusta contra la Cuenta "Diferencia" al '
             'confirmar.',
    )

    estado = fields.Selection(
        [
            ('a_confirmar', 'A Confirmar'),
            ('confirmada', 'Confirmada'),
            ('anulada', 'Anulada'),
        ],
        string='Estado', default='a_confirmar', required=True, copy=False,
        help='A Confirmar: recién generada desde el Recibo, el monto está en la Cuenta '
             '"Retenido a Confirmar". Confirmada: ya se emparejó contra el archivo de '
             'la DNIT (a mano o automático) y se reclasificó a la Cuenta "Retenciones '
             'Recibidas" — a partir de acá, Anular el Recibo que la generó queda '
             'bloqueado. Anulada: la DNIT anuló el comprobante (Fase 2).',
    )
    numero_comprobante = fields.Char(
        string='Nro. Comprobante', copy=False,
        help='Número de comprobante de retención informado por la DNIT — se carga a '
             'mano por ahora, o automáticamente al procesar el archivo de Marangatu '
             '(Fase 2).',
    )
    fecha_confirmacion = fields.Date(
        string='Fecha de Confirmación DNIT', copy=False,
        help='Fecha en que se confirmó contra el archivo de la DNIT — a título de '
             'auditoría.',
    )
    control = fields.Char(
        string='Control', copy=False,
        help='Código de control que asigna la DNIT a cada comprobante, si el archivo '
             'de Marangatu lo trae (Fase 2).',
    )
    retencion_move_id = fields.Many2one(
        'account.move', string='Asiento (Retenido a Confirmar)', readonly=True, copy=False,
        help='Asiento generado al Confirmar el Recibo: Débito Cuenta "Retenido a '
             'Confirmar", Crédito la Cuenta Por Cobrar del Cliente, conciliado contra '
             'la Factura.',
    )

    def unlink(self):
        for retencion in self:
            if retencion.estado != 'a_confirmar':
                raise UserError(
                    'No se puede eliminar una Retención Recibida %s — solo se pueden '
                    'eliminar las que están "A Confirmar" (se borran solas al Anular '
                    'el Recibo que las generó).'
                    % dict(retencion._fields['estado'].selection).get(retencion.estado)
                )
        return super().unlink()
