# -*- coding: utf-8 -*-
from odoo import fields, models


class TllrFcOtAprobacion(models.Model):
    """Aprobación (o rechazo) del cliente de trabajos adicionales."""
    _name = 'tllr_fc.ot.aprobacion'
    _description = "Aprobación de trabajos adicionales"
    _order = 'fecha desc, id desc'

    ot_id = fields.Many2one(
        'tllr_fc.ot', string="OT", required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía", related='ot_id.company_id',
        store=True, index=True)
    medio = fields.Selection([
        ('telefono', "Teléfono"),
        ('mensaje', "Mensaje"),
        ('presencial', "Presencial"),
        ('otro', "Otro"),
    ], string="Medio", required=True, default='telefono')
    persona = fields.Char(string="Quién aprobó", required=True)
    fecha = fields.Datetime(string="Fecha", required=True, default=fields.Datetime.now)
    estado = fields.Selection([
        ('aprobado', "Aprobado"),
        ('rechazado', "Rechazado"),
    ], string="Resultado", required=True, default='aprobado')
    servicio_ids = fields.Many2many(
        'tllr_fc.ot.servicio', 'tllr_fc_ot_aprobacion_servicio_rel', 'aprobacion_id',
        'servicio_id', string="Servicios")
    producto_ids = fields.Many2many(
        'tllr_fc.ot.producto', 'tllr_fc_ot_aprobacion_producto_rel', 'aprobacion_id',
        'producto_id', string="Repuestos, insumos y accesorios")
    detalle = fields.Text(
        string="Líneas cubiertas", readonly=True,
        help="Descripción de las líneas: se conserva aunque la línea se elimine.")
    notas = fields.Text(string="Notas")
    registrado_por_id = fields.Many2one(
        'res.users', string="Registrado por", default=lambda self: self.env.user, readonly=True)
