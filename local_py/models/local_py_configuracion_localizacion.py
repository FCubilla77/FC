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
    l10n_py_pagos_proveedores_activo = fields.Boolean(
        string='Activar Pagos - Proveedores', default=True,
        help='Si está desactivado, no se puede crear un Pago a Proveedor por fuera de '
             'Orden de Pago (ni desde el menú de Pagos, ni desde el botón "Registrar '
             'Pago" de una Factura, ni desde la Conciliación Bancaria automática) — '
             'evita que una Retención se omita por error, al forzar que todos los '
             'pagos a Proveedores pasen por Orden de Pago.',
    )
    l10n_py_pagos_clientes_activo = fields.Boolean(
        string='Activar Pagos - Clientes', default=True,
        help='Mismo criterio que "Activar Pagos - Proveedores", para Clientes — cuando '
             'se desactive, va a exigir usar "Recibo Cliente" en su lugar.',
    )
    l10n_py_retencion_iva = fields.Boolean(string='Retención IVA')
    l10n_py_retencion_iva_porcentaje = fields.Float(
        string='Porcentaje Retención Predeterminado (IVA)', digits=(5, 2),
    )
    l10n_py_retencion_iva_minimo = fields.Monetary(
        string='Valor Imponible Mínimo (IVA)', currency_field='company_currency_id',
        help='Monto mínimo de la operación (en la moneda de la empresa) a partir del '
             'cual corresponde retener. Por debajo de este valor, no se retiene.',
    )
    l10n_py_diario_retencion_iva_id = fields.Many2one(
        'account.journal', string='Diario de Retención IVA',
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        help='Diario de tipo Misceláneo. La Retención no genera un Pago (Odoo no lo '
             'permite sobre Diarios Misceláneos) — genera un asiento contable propio, '
             'conciliado directamente contra la factura.',
    )
    l10n_py_concepto_iva_id = fields.Many2one(
        'local_py.concepto_iva', string='Concepto IVA',
        default=lambda self: self.env.ref('local_py.concepto_iva_1', raise_if_not_found=False),
        help='Código exigido por la DNIT (Tesaka) para clasificar la Retención IVA. '
             '"IVA.1 — Pago a cuenta para Contribuyentes obligados" es el que corresponde '
             'al régimen habitual de retención sobre proveedores (el que ya calculamos '
             'en Orden de Pago) — los demás códigos son para situaciones puntuales '
             'distintas (inmuebles, exterior, casos excepcionales).',
    )
    l10n_py_cuenta_gasto_absorcion_id = fields.Many2one(
        'account.account', string='Cuenta de Gasto por Absorción (IVA)',
        domain="[('company_ids', 'in', company_id)]",
        help='Cuenta contable de Gasto donde se absorbe la Retención IVA a proveedores '
             'del exterior, cuando ese Proveedor la tenga configurada como "Se Absorbe '
             'IVA" — a diferencia de la Retención local, no se le descuenta nada al '
             'Proveedor: la retención pasa a ser un costo aparte para la Compañía.',
    )
    l10n_py_retencion_renta = fields.Boolean(string='Retención Renta')
    l10n_py_diario_retencion_renta_id = fields.Many2one(
        'account.journal', string='Diario de Retención Renta',
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        help='Diario de tipo Misceláneo — se usa tanto para la fila de Medios cuando la '
             'Retención Renta se descuenta del Proveedor, como para el asiento paralelo '
             'cuando se absorbe. Tiene que ser distinto al Diario de Retención IVA, '
             'para poder diferenciar una de otra en la grilla de Medios.',
    )
    l10n_py_cuenta_gasto_absorcion_renta_id = fields.Many2one(
        'account.account', string='Cuenta de Gasto por Absorción (Renta)',
        domain="[('company_ids', 'in', company_id)]",
        help='Cuenta contable de Gasto donde se absorbe la Retención Renta a '
             'proveedores del exterior, cuando ese Proveedor la tenga configurada como '
             '"Se Absorbe Renta".',
    )
    company_currency_id = fields.Many2one(related='company_id.currency_id', string='Moneda de la Empresa')
    no_retencion_ids = fields.One2many(
        'local_py.no_retencion', 'config_id', string='Resoluciones de No Retención',
    )
    concepto_renta_no_residente_ids = fields.One2many(
        'local_py.concepto_renta_no_residente', string='Conceptos Renta No Residente',
        compute='_compute_concepto_renta_no_residente_ids', inverse='_inverse_concepto_renta_no_residente_ids',
    )

    def _compute_concepto_renta_no_residente_ids(self):
        conceptos = self.env['local_py.concepto_renta_no_residente'].search([])
        for config in self:
            config.concepto_renta_no_residente_ids = conceptos

    def _inverse_concepto_renta_no_residente_ids(self):
        # No hace falta ninguna acción — es un catálogo global (no por
        # Compañía), la grilla editable ya escribe directo sobre esos
        # registros; este método solo evita que el campo quede de solo
        # lectura por no tener "inverse" definido.
        pass

    @api.constrains('l10n_py_diario_retencion_iva_id', 'l10n_py_diario_retencion_renta_id')
    def _check_diarios_retencion_distintos(self):
        for config in self:
            if (
                config.l10n_py_diario_retencion_iva_id
                and config.l10n_py_diario_retencion_renta_id
                and config.l10n_py_diario_retencion_iva_id == config.l10n_py_diario_retencion_renta_id
            ):
                raise exceptions.ValidationError(
                    'El Diario de Retención IVA y el Diario de Retención Renta tienen que '
                    'ser distintos entre sí (aunque apunten a la misma Cuenta contable) — '
                    'sirve para diferenciar una Retención de la otra en la grilla de Medios '
                    'de la Orden de Pago.'
                )

    _company_uniq = models.Constraint(
        'unique(company_id)',
        'Ya existe una Configuración de Localización para esta compañía.',
    )

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

    @api.constrains(
        'l10n_py_retencion_iva', 'l10n_py_diario_retencion_iva_id', 'l10n_py_concepto_iva_id',
        'l10n_py_cuenta_gasto_absorcion_id',
    )
    def _check_retencion_iva_configuracion_completa(self):
        """No se puede activar Retención IVA sin elegir, al mismo tiempo,
        el Diario de Retención, el Concepto IVA, y la Cuenta de Gasto
        por Absorción — activarlo a medias dejaría Órdenes de Pago
        bloqueadas al Confirmar sin ninguna pista de qué falta hasta
        ese momento."""
        for config in self:
            if config.l10n_py_retencion_iva and (
                not config.l10n_py_diario_retencion_iva_id or not config.l10n_py_concepto_iva_id
                or not config.l10n_py_cuenta_gasto_absorcion_id
            ):
                raise exceptions.ValidationError(
                    'Para activar "Retención IVA" hay que elegir, al mismo tiempo, el Diario de '
                    'Retención IVA, el Concepto IVA, y la Cuenta de Gasto por Absorción (IVA).'
                )

    @api.constrains('l10n_py_retencion_renta', 'l10n_py_diario_retencion_renta_id', 'l10n_py_cuenta_gasto_absorcion_renta_id')
    def _check_retencion_renta_configuracion_completa(self):
        """Mismo criterio que Retención IVA: no se puede activar
        Retención Renta sin el Diario de Retención y la Cuenta de Gasto
        por Absorción completos."""
        for config in self:
            if config.l10n_py_retencion_renta and (
                not config.l10n_py_diario_retencion_renta_id or not config.l10n_py_cuenta_gasto_absorcion_renta_id
            ):
                raise exceptions.ValidationError(
                    'Para activar "Retención Renta" hay que elegir, al mismo tiempo, el Diario de '
                    'Retención Renta y la Cuenta de Gasto por Absorción (Renta).'
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

    _account_config_uniq = models.Constraint(
        'unique(config_id, account_id)',
        'Esta cuenta ya está configurada para detallarse en Libro Inventario.',
    )
