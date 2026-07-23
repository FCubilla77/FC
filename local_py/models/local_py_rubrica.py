# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

USO_SELECTION = [
    ('diario', 'L. Diario'),
    ('mayor', 'L. Mayor'),
    ('inventario', 'L. Inventario'),
    ('compras', 'L. Compras'),
    ('ventas', 'L. Ventas'),
]

REQUIRED_FIELD_LABELS = [
    ('company_id', 'Compañía'),
    ('idrubrica', 'Id'),
    ('fecha', 'Fecha'),
    ('uso', 'Uso'),
    ('cantidad_hojas', 'Cant. de hoja'),
    ('nro_entrada', 'Nro. Entrada'),
    ('fecha_entrada', 'Fecha entrada'),
    ('numero_inicial', 'Número Inicial'),
    ('numero_final', 'Número final'),
    ('imagen', 'Imagen'),
    ('primera_hoja', 'Primera hoja'),
]

MAX_6_DIGITS = 999999


class LocalPyRubrica(models.Model):
    _name = 'local_py.rubrica'
    _description = 'Rúbrica de Libros Contables'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fecha desc, id desc'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company, tracking=True,
    )
    idrubrica = fields.Char(string='Id', size=10)
    fecha = fields.Date(string='Fecha')
    uso = fields.Selection(USO_SELECTION, string='Uso')
    cantidad_hojas = fields.Integer(string='Cant. de hoja')
    nro_entrada = fields.Char(string='Nro. Entrada', size=10)
    fecha_entrada = fields.Date(string='Fecha entrada')
    numero_inicial = fields.Integer(string='Número Inicial')
    numero_final = fields.Integer(string='Número final')
    utilizado_hasta = fields.Integer(
        string='Utilizado hasta', readonly=True, copy=False,
        help='Se autocompleta al confirmar con el valor de "Número Inicial". '
             'Se actualiza más adelante mediante otro proceso, a medida que '
             'se van usando hojas del libro.',
    )
    imagen = fields.Binary(
        string='Imagen', attachment=True,
        help='Sello de la rúbrica, para incluir más adelante en los informes rubricados.',
    )
    imagen_filename = fields.Char(string='Nombre de archivo (Imagen)')
    primera_hoja = fields.Binary(
        string='Primera hoja', attachment=True,
        help='Documento/comprobante entregado por la entidad registral (RUN) al rubricar.',
    )
    primera_hoja_filename = fields.Char(string='Nombre de archivo (Primera hoja)')
    state = fields.Selection(
        [('draft', 'Borrador'), ('confirmed', 'Confirmado')],
        string='Estado', default='draft', required=True, copy=False, tracking=True,
    )

    @api.constrains('idrubrica', 'nro_entrada')
    def _check_alfanumerico_10(self):
        for rec in self:
            for fname, label in (('idrubrica', 'Id'), ('nro_entrada', 'Nro. Entrada')):
                value = rec[fname]
                if value and not value.isalnum():
                    raise ValidationError('El campo "%s" solo admite caracteres alfanuméricos.' % label)

    @api.constrains('numero_inicial', 'numero_final', 'utilizado_hasta')
    def _check_max_6_digitos(self):
        for rec in self:
            for fname, label in (
                ('numero_inicial', 'Número Inicial'),
                ('numero_final', 'Número final'),
                ('utilizado_hasta', 'Utilizado hasta'),
            ):
                value = rec[fname]
                if value and (value < 0 or value > MAX_6_DIGITS):
                    raise ValidationError(
                        'El campo "%s" admite hasta 6 dígitos (máximo %s).' % (label, MAX_6_DIGITS)
                    )

    @api.constrains('state', 'company_id', 'idrubrica', 'fecha', 'uso', 'cantidad_hojas',
                     'nro_entrada', 'fecha_entrada', 'numero_inicial', 'numero_final',
                     'imagen', 'primera_hoja')
    def _check_required_on_confirm(self):
        for rec in self:
            if rec.state != 'confirmed':
                continue
            missing = [label for fname, label in REQUIRED_FIELD_LABELS if not rec[fname]]
            if missing:
                raise ValidationError(
                    'No se puede confirmar la rúbrica sin completar: %s.' % ', '.join(missing)
                )
            if rec.numero_final < rec.numero_inicial:
                raise ValidationError('"Número final" debe ser mayor o igual a "Número Inicial".')

    def action_confirm(self):
        for rec in self:
            rec.write({
                'utilizado_hasta': rec.numero_inicial,
                'state': 'confirmed',
            })

    def action_draft(self):
        for rec in self:
            rec.state = 'draft'
            rec.message_post(body='Rúbrica devuelta a Borrador: los datos vuelven a ser editables.')

    def unlink(self):
        for rec in self:
            if rec.utilizado_hasta and rec.numero_inicial and rec.utilizado_hasta > rec.numero_inicial:
                raise UserError(
                    'No se puede eliminar esta rúbrica: "Utilizado hasta" (%s) ya superó a '
                    '"Número Inicial" (%s).' % (rec.utilizado_hasta, rec.numero_inicial)
                )
        return super().unlink()
