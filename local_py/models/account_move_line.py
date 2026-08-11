# -*- coding: utf-8 -*-

from odoo import fields, models


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    l10n_py_comentario = fields.Char(
        related='move_id.l10n_py_comentario', string='Comentario', store=False,
    )
    l10n_py_nro_asiento_libro = fields.Char(
        related='move_id.l10n_py_nro_asiento_libro', string='Nro. Asiento', store=False,
    )
    l10n_py_nro_fiscal = fields.Integer(
        related='move_id.l10n_py_nro_fiscal', string='Nro. Fiscal', store=False,
    )
    l10n_py_iva_5_cubierto = fields.Monetary(
        string='IVA 5% ya cubierto (Retención)', currency_field='currency_id', copy=False,
        help='Cuánto del IVA al 5% de esta cuota (en su propia moneda) ya fue incluido '
             'en algún cálculo de Retención IVA anterior — sea una Orden de Pago normal '
             'o una "Orden de Pago Retención". Evita retener dos veces sobre lo mismo.',
    )
    l10n_py_iva_10_cubierto = fields.Monetary(
        string='IVA 10% ya cubierto (Retención)', currency_field='currency_id', copy=False,
        help='Mismo criterio que "IVA 5% ya cubierto", para el tramo al 10%.',
    )
    l10n_py_renta_importe_cubierto = fields.Monetary(
        string='Importe ya cubierto (Retención Renta)', currency_field='currency_id', copy=False,
        help='Cuánto del Total Original de esta cuota (en su propia moneda) ya fue '
             'incluido en algún cálculo de Retención Renta No Residente anterior. Se '
             'guarda en base al importe de la cuota (no al monto ya retenido en sí) '
             'para que el control siga siendo correcto aunque el Porcentaje configurado '
             'cambie entre una Orden de Pago y la siguiente.',
    )
