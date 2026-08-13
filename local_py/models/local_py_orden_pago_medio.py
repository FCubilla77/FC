# -*- coding: utf-8 -*-

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class LocalPyOrdenPagoMedio(models.Model):
    _name = 'local_py.orden_pago.medio'
    _description = 'Medio de Pago de una Orden de Pago'

    orden_pago_id = fields.Many2one(
        'local_py.orden_pago', string='Orden de Pago', required=True, ondelete='cascade',
    )
    journal_id = fields.Many2one(
        'account.journal', string='Diario', required=True,
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(related='orden_pago_id.company_id')
    importe = fields.Monetary(string='Importe', currency_field='currency_id')
    currency_id = fields.Many2one(related='orden_pago_id.currency_id')

    # Datos de referencia — hoy son solo texto/fecha libres; más adelante se
    # van a vincular a los modelos reales de Retención.
    fecha_emision = fields.Date(string='Fecha Emisión')
    fecha_vencimiento = fields.Date(string='Fecha Venc.')
    nro_documento = fields.Char(string='Nro. Documento')
    banco = fields.Char(string='Banco')
    chequera_id = fields.Many2one('local_py.chequera', string='Chequera')
    orden_pago_partner_id = fields.Many2one(related='orden_pago_id.partner_id', string='Proveedor (para filtro)')
    cheque_reutilizar_id = fields.Many2one(
        'local_py.chequera.cheque', string='Reutilizar Cheque N°',
        domain="[('chequera_id', '=', chequera_id), ('estado', '=', 'reutilizable'),"
               " ('proveedor_id', '=', orden_pago_partner_id)]",
        help='Solo se pueden reutilizar cheques que hayan sido emitidos originalmente '
             'para el mismo Proveedor de esta Orden de Pago. Al Confirmar, este número '
             'se reactiva directamente (pasa de Reutilizable a Emitido) — no vuelve a '
             'pasar por Impresión Masiva, ya que el papel físico ya se imprimió antes.',
    )
    cuenta_banco = fields.Char(string='Cuenta Banco')
    es_retencion = fields.Boolean(
        string='Es Retención', default=False, copy=False,
        help='Marca las filas que el sistema agregó solo por el cálculo automático de '
             'Retención IVA — no se generan a mano.',
    )
    retencion_move_id = fields.Many2one(
        'account.move', string='Asiento de Retención', readonly=True, copy=False,
        help='La Retención no genera un Pago (Odoo no lo permite sobre Diarios '
             'Misceláneos) — genera este asiento contable propio.',
    )
    retencion_factura_id = fields.Many2one(
        'local_py.orden_pago.factura', string='Factura de la Retención', readonly=True, copy=False,
        help='A qué Factura le corresponde exactamente esta porción de Retención — se '
             'concilia siempre directo contra ella, nunca a través del reparto genérico '
             'entre Facturas y Medios (la Retención no es intercambiable como el '
             'Efectivo: cada porción tiene un destino fijo).',
    )

    payment_ids = fields.One2many(
        'account.payment', 'l10n_py_orden_pago_medio_id', string='Pago(s)',
        help='Pago(s) generado(s) por esta fila al Confirmar la Orden de Pago. Normalmente '
             'es uno solo — si esta fila tuvo que repartirse entre varias facturas (por '
             'ejemplo, un solo cheque que alcanza para pagar dos facturas), va a haber más '
             'de un pago, cada uno por el importe exacto que le corresponde a cada factura.',
    )
    documentos_relacionados = fields.Char(
        string='Doc. relacionados', compute='_compute_documentos_relacionados',
        help='Los Pagos generados por esta fila (Efectivo, Transferencia, Cheque), o el '
             'Asiento Contable de Retención si esta fila es una Retención.',
    )

    @api.depends('payment_ids', 'retencion_move_id')
    def _compute_documentos_relacionados(self):
        for medio in self:
            if medio.es_retencion:
                medio.documentos_relacionados = medio.retencion_move_id.name or ''
            else:
                medio.documentos_relacionados = ', '.join(medio.payment_ids.mapped('name'))

    def _resolver_chequera(self):
        """Asigna/refresca la Chequera Activa de cada fila según su Diario,
        de forma explícita del lado del servidor — no depende únicamente
        de que el evento de interfaz (onchange) se haya disparado y
        guardado correctamente."""
        for medio in self:
            chequera = self.env['local_py.chequera'].search([
                ('diario_id', '=', medio.journal_id.id), ('state', '=', 'activo'),
            ], limit=1)
            vals = {'chequera_id': chequera.id}
            if chequera:
                vals['banco'] = chequera.bank_id.name
                vals['cuenta_banco'] = chequera.cuenta_bancaria_id.display_name
                if not medio.fecha_emision:
                    vals['fecha_emision'] = medio.orden_pago_id.fecha
                if chequera.tipo == 'al_dia':
                    vals['fecha_vencimiento'] = vals.get('fecha_emision', medio.fecha_emision)
            medio.write(vals)

    @api.onchange('journal_id')
    def _onchange_journal_id_chequera(self):
        for medio in self:
            chequera = self.env['local_py.chequera'].search([
                ('diario_id', '=', medio.journal_id.id), ('state', '=', 'activo'),
            ], limit=1)
            medio.chequera_id = chequera
            if chequera:
                medio.banco = chequera.bank_id.name
                medio.cuenta_banco = chequera.cuenta_bancaria_id.display_name
                if not medio.fecha_emision:
                    medio.fecha_emision = medio.orden_pago_id.fecha
                if chequera.tipo == 'al_dia':
                    medio.fecha_vencimiento = medio.fecha_emision

    @api.constrains('importe')
    def _check_importe(self):
        for medio in self:
            if medio.importe <= 0:
                raise ValidationError('El importe de cada Medio de Pago debe ser mayor a cero.')

    @api.constrains('chequera_id', 'currency_id')
    def _check_chequera_moneda(self):
        for medio in self:
            if medio.chequera_id and medio.chequera_id.currency_id != medio.currency_id:
                raise ValidationError(
                    'La Chequera "%s" está en %s, pero la Orden de Pago está en %s. No se '
                    'puede usar esa Chequera acá.'
                    % (medio.chequera_id.name, medio.chequera_id.currency_id.name, medio.currency_id.name)
                )

    @api.constrains('chequera_id', 'fecha_emision', 'fecha_vencimiento')
    def _check_chequera_diferido_requiere_vencimiento(self):
        """La validación de abajo (_check_chequera_tipo_fechas) se salta
        por completo si Fecha de Vencimiento está vacía — hace falta
        esta validación aparte para bloquear justamente ese caso: una
        Chequera "Diferido" sin Fecha de Vencimiento cargada."""
        for medio in self:
            if medio.chequera_id and medio.chequera_id.tipo == 'diferido' and not medio.fecha_vencimiento:
                raise ValidationError(
                    'La Chequera "%s" es "Diferido": complete la Fecha de Vencimiento del '
                    'cheque antes de continuar.' % medio.chequera_id.name
                )

    @api.constrains('chequera_id', 'fecha_emision', 'fecha_vencimiento')
    def _check_chequera_tipo_fechas(self):
        for medio in self:
            if not medio.chequera_id or not medio.fecha_emision or not medio.fecha_vencimiento:
                continue
            if medio.chequera_id.tipo == 'al_dia' and medio.fecha_emision != medio.fecha_vencimiento:
                raise ValidationError(
                    'La Chequera "%s" es "Al día": la Fecha de Emisión y la Fecha de '
                    'Vencimiento del cheque deben ser la misma.' % medio.chequera_id.name
                )
            if medio.chequera_id.tipo == 'diferido' and medio.fecha_vencimiento <= medio.fecha_emision:
                raise ValidationError(
                    'La Chequera "%s" es "Diferido": la Fecha de Vencimiento debe ser '
                    'posterior a la Fecha de Emisión.' % medio.chequera_id.name
                )

    @api.constrains('cheque_reutilizar_id')
    def _check_cheque_reutilizar(self):
        for medio in self:
            if medio.cheque_reutilizar_id and medio.cheque_reutilizar_id.estado != 'reutilizable':
                raise ValidationError(
                    'El cheque N° %s ya se utilizó (estado: %s) y no puede reutilizarse — '
                    'solo se pueden reutilizar cheques en estado "Reutilizable".'
                    % (medio.cheque_reutilizar_id.numero, medio.cheque_reutilizar_id.estado)
                )
