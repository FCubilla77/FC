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
    generacion_ids = fields.One2many(
        'local_py.rubrica.generacion', 'rubrica_id', string='Generaciones Oficiales',
    )

    @api.model
    def _get_rubrica_disponible(self, company_id, uso):
        """Devuelve la Rúbrica Confirmada de esa Compañía y Uso que todavía
        tiene hojas disponibles (Utilizado hasta < Número final, o sin usar
        todavía). Si hay más de una candidata, no elige por su cuenta: pide
        que se revise manualmente (posible problema de datos)."""
        candidatas = self.search([
            ('company_id', '=', company_id),
            ('uso', '=', uso),
            ('state', '=', 'confirmed'),
        ]).filtered(lambda r: not r.utilizado_hasta or r.utilizado_hasta < r.numero_final)
        if not candidatas:
            return self.env['local_py.rubrica']
        if len(candidatas) > 1:
            raise UserError(
                'Hay más de una Rúbrica Confirmada con hojas disponibles para "%s" en esta '
                'compañía (%s). Revise manualmente cuál es la vigente antes de continuar.'
                % (dict(USO_SELECTION).get(uso, uso), ', '.join(candidatas.mapped('idrubrica')))
            )
        return candidatas

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
            esperado_hojas = rec.numero_final - rec.numero_inicial + 1
            if rec.cantidad_hojas != esperado_hojas:
                raise ValidationError(
                    '"Cant. de hoja" (%s) no coincide con "Número final" - "Número Inicial" + 1 '
                    '(debería ser %s).' % (rec.cantidad_hojas, esperado_hojas)
                )

    @api.constrains('company_id', 'idrubrica', 'fecha', 'uso')
    def _check_unique_id_fecha_uso(self):
        for rec in self:
            if not (rec.idrubrica and rec.fecha and rec.uso):
                continue
            duplicado = self.search_count([
                ('id', '!=', rec.id),
                ('company_id', '=', rec.company_id.id),
                ('idrubrica', '=', rec.idrubrica),
                ('fecha', '=', rec.fecha),
                ('uso', '=', rec.uso),
            ])
            if duplicado:
                raise ValidationError(
                    'Ya existe otra rúbrica de esta compañía con la misma combinación de '
                    'Id, Fecha y Uso.'
                )

    @api.constrains('state', 'numero_inicial', 'company_id', 'uso')
    def _check_numeracion_correlativa(self):
        for rec in self:
            if rec.state != 'confirmed':
                continue
            anterior = self.search([
                ('id', '!=', rec.id),
                ('company_id', '=', rec.company_id.id),
                ('uso', '=', rec.uso),
                ('state', '=', 'confirmed'),
            ], order='numero_final desc', limit=1)
            if anterior:
                esperado = anterior.numero_final + 1
                if rec.numero_inicial != esperado:
                    raise ValidationError(
                        'El "Número Inicial" de esta rúbrica debe continuar la numeración de la '
                        'última rúbrica confirmada del mismo Uso (%s): se esperaba %s, no %s.'
                        % (dict(USO_SELECTION).get(rec.uso, rec.uso), esperado, rec.numero_inicial)
                    )

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


class LocalPyRubricaGeneracion(models.Model):
    _name = 'local_py.rubrica.generacion'
    _description = 'Generación Oficial de Libro (Diario/Mayor) sobre una Rúbrica'
    _order = 'pagina_desde'

    rubrica_id = fields.Many2one(
        'local_py.rubrica', string='Rúbrica', required=True, ondelete='cascade',
    )
    fecha_desde = fields.Date(string='Fecha desde', required=True)
    fecha_hasta = fields.Date(string='Fecha hasta', required=True)
    pagina_desde = fields.Integer(string='Página desde', required=True)
    pagina_hasta = fields.Integer(string='Página hasta', required=True)
    pdf_file = fields.Binary(string='PDF Generado', attachment=True, readonly=True)
    pdf_filename = fields.Char(string='Nombre de archivo')

    def action_anular(self):
        """Deshace esta generación (solo si es la más reciente de su
        Rúbrica) y le devuelve las páginas consumidas."""
        for rec in self:
            ultima = rec.rubrica_id.generacion_ids.sorted('pagina_desde')[-1:]
            if rec not in ultima:
                raise UserError(
                    'Solo se puede anular la generación más reciente de cada Rúbrica '
                    '(para no dejar huecos en la numeración de páginas).'
                )
            rubrica = rec.rubrica_id
            anteriores = rubrica.generacion_ids - rec
            if anteriores:
                nueva_ultima = anteriores.sorted('pagina_hasta')[-1]
                rubrica.utilizado_hasta = nueva_ultima.pagina_hasta
            else:
                rubrica.utilizado_hasta = False
            rec.unlink()
