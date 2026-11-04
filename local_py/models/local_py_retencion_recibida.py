# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


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
        help='Importe oficial total informado por el archivo de Marangatu de la DNIT '
             '(Fase 2) — se completa recién al procesar ese archivo. Si difiere del '
             'Importe, la diferencia se ajusta contra la Cuenta "Diferencia" al '
             'confirmar.',
    )
    importe_dnit_iva = fields.Monetary(
        string='Importe DNIT (IVA)', currency_field='currency_id', copy=False,
        help='Porción de IVA del Importe DNIT, según el desglose que trae el archivo '
             'de Marangatu — un mismo comprobante de retención puede tener IVA y Renta '
             'a la vez. Define cuánto se reclasifica a la Cuenta "Retenciones '
             'Recibidas (IVA)" al confirmar (Fase 2).',
    )
    importe_dnit_renta = fields.Monetary(
        string='Importe DNIT (Renta)', currency_field='currency_id', copy=False,
        help='Porción de Renta del Importe DNIT — mismo criterio que el de IVA.',
    )

    @api.constrains('importe_dnit', 'importe_dnit_iva', 'importe_dnit_renta')
    def _check_desglose_dnit(self):
        """El desglose IVA + Renta tiene que cerrar contra el total DNIT.
        Solo se valida una vez que hay un Importe DNIT cargado — mientras la
        Retención está "A Confirmar" los 3 están en cero y no hay nada que
        controlar."""
        for retencion in self:
            if not retencion.importe_dnit:
                continue
            suma = retencion.importe_dnit_iva + retencion.importe_dnit_renta
            currency = retencion.currency_id or self.env.company.currency_id
            if currency.compare_amounts(suma, retencion.importe_dnit) != 0:
                raise ValidationError(
                    'El desglose del Importe DNIT no cierra: IVA (%s) + Renta (%s) = %s, '
                    'pero el Importe DNIT total es %s.'
                    % (retencion.importe_dnit_iva, retencion.importe_dnit_renta, suma,
                       retencion.importe_dnit)
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
