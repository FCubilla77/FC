# -*- coding: utf-8 -*-

from odoo import fields, models

from .local_py_libro_report import fmt_pyg


class LocalPyStockValorizadoLinea(models.TransientModel):
    """Tabla temporal (se limpia sola, como cualquier TransientModel) que
    guarda el detalle ya calculado de Movimiento de Stock Valorizado, para
    poder mostrarlo como una lista nativa de Odoo (agrupable, con
    subtotales automáticos), en vez de un documento HTML armado a mano.

    El orden es siempre el de creación (columna "sequence", fija). Las
    columnas Fecha, Fecha Sistema, Valor Acumulado, Cantidad Acumulada y
    Costo Promedio son "saldos corrientes": solo tienen sentido en el
    orden en que se calcularon, por eso se muestran con un campo
    calculado no almacenado (no se pueden reordenar haciendo clic), igual
    mecanismo que ya usamos en Asientos Fiscales para Nro. Fiscal."""
    _name = 'local_py.stock_valorizado.linea'
    _description = 'Línea de Movimiento de Stock Valorizado (temporal)'
    _order = 'sequence'

    wizard_id = fields.Many2one(
        'local_py.stock_valorizado.wizard', string='Asistente', ondelete='cascade',
    )
    sequence = fields.Integer(string='Secuencia')
    producto_id = fields.Many2one('product.product', string='Producto')
    cuenta_id = fields.Many2one('account.account', string='Cuenta')

    referencia = fields.Char(string='Referencia')
    nro_fiscal = fields.Integer(string='Nro. Fiscal')
    cantidad = fields.Float(string='Cantidad', digits=(16, 2))
    costo_unitario = fields.Float(string='Costo Unitario', digits=(16, 2))
    costo_total = fields.Float(string='Costo Total')
    debe = fields.Float(string='Débito')
    haber = fields.Float(string='Crédito')

    fecha_real = fields.Datetime(string='Fecha (real)')
    fecha_sistema_real = fields.Datetime(string='Fecha Sistema (real)')
    valor_acumulado_real = fields.Float(string='Valor Acumulado (real)')
    cantidad_acumulada_real = fields.Float(string='Cantidad Acumulada (real)')
    costo_promedio_real = fields.Float(string='Costo Promedio (real)')

    fecha = fields.Char(string='Fecha', compute='_compute_display', store=False)
    fecha_sistema = fields.Char(string='Fecha Sistema', compute='_compute_display', store=False)
    valor_acumulado = fields.Char(string='Valor Acumulado', compute='_compute_display', store=False)
    cantidad_acumulada = fields.Char(string='Cantidad Acumulada', compute='_compute_display', store=False)
    costo_promedio = fields.Char(string='Costo Promedio', compute='_compute_display', store=False)

    def _compute_display(self):
        for linea in self:
            linea.fecha = linea.fecha_real.strftime('%d/%m/%Y') if linea.fecha_real else ''
            linea.fecha_sistema = (
                linea.fecha_sistema_real.strftime('%d/%m/%Y %H:%M:%S') if linea.fecha_sistema_real else ''
            )
            linea.valor_acumulado = fmt_pyg(linea.valor_acumulado_real)
            linea.cantidad_acumulada = fmt_pyg(linea.cantidad_acumulada_real, 2)
            linea.costo_promedio = fmt_pyg(linea.costo_promedio_real, 2) if linea.costo_promedio_real else ''
