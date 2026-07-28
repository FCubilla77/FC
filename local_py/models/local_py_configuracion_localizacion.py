# -*- coding: utf-8 -*-

from odoo import api, exceptions, fields, models


class LocalPyConfiguracionLocalizacion(models.Model):
    _name = 'local_py.configuracion_localizacion'
    _description = 'Configuraciones de Localización Paraguay'

    company_id = fields.Many2one(
        'res.company', string='Empresa', required=True,
        default=lambda self: self.env.company,
    )
    renumeracion_ids = fields.One2many(
        'local_py.configuracion_localizacion.renumeracion', 'config_id',
        string='Renumeración de Asiento',
    )
    l10n_py_imputacion_tributaria_ids = fields.Many2many(
        related='company_id.l10n_py_imputacion_tributaria_ids',
        string='Imputación Tributaria',
        readonly=False,
        help='Mismo campo que en Ajustes > Empresas > Empresas: el régimen '
             'tributario de esta Compañía (IVA, IRE, IRP-RSP). "No Imputa" no '
             'puede combinarse con las otras opciones.',
    )
    libro_inventario_detalle_ids = fields.One2many(
        'local_py.libro_inventario.detalle_cuenta', 'config_id',
        string='Detalle Libro Inventario',
    )
    l10n_py_asiento_ajuste_inventario = fields.Boolean(
        string='Generar Asiento por Ajuste de Inventario Físico',
        help='Si está activo, al aplicar un ajuste desde Inventario > Operaciones > '
             'Ajustes > Inventario físico, se genera automáticamente un asiento contable '
             '(Débito/Crédito entre la cuenta de valoración de inventario y la cuenta de '
             'gastos configuradas en la Categoría del producto). Ese asiento queda '
             'protegido: no se puede eliminar ni restablecer a borrador.',
    )

    _sql_constraints = [
        ('company_uniq', 'unique(company_id)',
         'Ya existe una Configuración de Localización para esta compañía.'),
    ]

    @api.constrains('company_id')
    def _check_company_unique(self):
        """Refuerzo a nivel de código de la restricción de unicidad por
        Compañía, independiente de la restricción de base de datos (que en
        algún momento no llegó a aplicarse correctamente en una base ya
        existente)."""
        for rec in self:
            if self.search_count([
                ('id', '!=', rec.id),
                ('company_id', '=', rec.company_id.id),
            ]):
                raise exceptions.ValidationError(
                    'Ya existe una Configuración de Localización para esta compañía.'
                )

    @api.onchange('l10n_py_imputacion_tributaria_ids')
    def _onchange_l10n_py_imputacion_tributaria_ids(self):
        no_imputa = self.env.ref('local_py.imputacion_no_imputa', raise_if_not_found=False)
        if not no_imputa:
            return
        for rec in self:
            current = rec.l10n_py_imputacion_tributaria_ids
            previous = rec._origin.l10n_py_imputacion_tributaria_ids
            added = current - previous
            if no_imputa in added:
                rec.l10n_py_imputacion_tributaria_ids = current.filtered(lambda t: t.id == no_imputa.id)
            elif no_imputa in current and (current - no_imputa):
                rec.l10n_py_imputacion_tributaria_ids = current - no_imputa


class LocalPyConfiguracionLocalizacionRenumeracion(models.Model):
    _name = 'local_py.configuracion_localizacion.renumeracion'
    _description = 'Renumeración de Asiento (por Año)'
    _order = 'anio'

    config_id = fields.Many2one(
        'local_py.configuracion_localizacion', string='Configuración',
        required=True, ondelete='cascade',
    )
    anio = fields.Integer(string='Año')
    numero_inicial = fields.Integer(string='Número Asiento Fiscal Inicial')
    ultimo_nro_utilizado = fields.Integer(string='Ultimo Nro. Utilizado', readonly=True)
    ultima_fecha_procesada = fields.Date(string='Ultima fecha procesada', readonly=True)

    def action_limpiar_numeracion(self):
        self.ensure_one()
        return {
            'name': 'Limpiar numeración',
            'type': 'ir.actions.act_window',
            'res_model': 'local_py.limpiar_numeracion.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_row_id': self.id,
                'default_fecha_hasta': self.ultima_fecha_procesada,
            },
        }


class LocalPyLibroInventarioDetalleCuenta(models.Model):
    _name = 'local_py.libro_inventario.detalle_cuenta'
    _description = 'Detalle de Cuenta para Libro Inventario'

    config_id = fields.Many2one(
        'local_py.configuracion_localizacion', string='Configuración',
        required=True, ondelete='cascade',
    )
    account_id = fields.Many2one('account.account', string='Cuenta', required=True)
    criterio = fields.Selection(
        [('contacto', 'Por Contacto'), ('producto', 'Por Producto')],
        string='Criterio', required=True,
    )
    nivel = fields.Selection(
        [('todos', 'Mostrar todo'), ('top_n', 'Mostrar solo los X mayores')],
        string='Nivel de detalle', required=True, default='todos',
    )
    cantidad_top = fields.Integer(string='Cantidad (X)')

    _sql_constraints = [
        ('account_config_uniq', 'unique(config_id, account_id)',
         'Esta cuenta ya está configurada para detallarse en Libro Inventario.'),
    ]
