# -*- coding: utf-8 -*-

from odoo import api, fields, models, exceptions


class LocalPyDocumentoAnulado(models.Model):
    _name = 'local_py.documento_anulado'
    _description = 'Documento Anulado (número no utilizado, a omitir en la numeración)'
    _order = 'diario_id, numero'

    diario_id = fields.Many2one(
        'account.journal', string='Diario', required=True,
        domain="[('type', '=', 'sale')]",
    )
    company_id = fields.Many2one(related='diario_id.company_id', string='Compañía', store=True)
    timbrado = fields.Integer(
        string='Timbrado', copy=False,
        help='Se completa solo desde el Timbrado configurado en el Diario, al momento '
             'de registrar — queda como estaba en ese momento, no se actualiza solo si '
             'el Diario cambia de Timbrado después.',
    )
    numero = fields.Char(
        string='Número', size=15, required=True,
        help='Formato completo 999-999-9999999 — tiene que compartir Establecimiento y '
             'Punto de Expedición con el Diario elegido, y caer dentro de su rango '
             '(Nro. Documento a Nro. Documento Final).',
    )
    tipo_fiscal_id = fields.Many2one(
        'local_py.tipo_fiscal', string='Tipo de Documento Fiscal',
        help='Se completa solo desde el Tipo Fiscal configurado en el Diario, al '
             'momento de registrar.',
    )
    motivo = fields.Char(string='Motivo', required=True)
    fecha_registro = fields.Date(
        string='Fecha de Registro', required=True, default=fields.Date.context_today,
    )

    _sql_constraints = [
        ('diario_numero_unique', 'unique(diario_id, numero)',
         'Ya existe un Documento Anulado registrado con ese Diario y Número.'),
    ]

    @api.onchange('diario_id')
    def _onchange_diario_id(self):
        for doc in self:
            if doc.diario_id:
                doc.timbrado = doc.diario_id.l10n_py_timbrado
                doc.tipo_fiscal_id = doc.diario_id.local_py_tipo_fiscal_id

    @api.constrains('diario_id', 'numero')
    def _check_numero_dentro_de_rango(self):
        for doc in self:
            if doc.diario_id and doc.numero:
                doc.diario_id.l10n_py_verificar_dentro_de_rango(doc.numero)

    @api.constrains('diario_id', 'numero')
    def _check_numero_no_usado(self):
        for doc in self:
            if doc.diario_id and doc.numero:
                if self.env['account.move'].search_count([
                    ('journal_id', '=', doc.diario_id.id),
                    ('l10n_py_nro_documento', '=', doc.numero),
                ]):
                    raise exceptions.ValidationError(
                        'El Número %s ya fue utilizado en una Factura/Nota de Crédito/Débito '
                        'del Diario "%s" — no se puede registrar como Anulado.'
                        % (doc.numero, doc.diario_id.name)
                    )

    def _esta_bloqueado(self):
        """Un Documento Anulado queda bloqueado (Diario y Número dejan de ser
        editables/eliminables) desde el momento en que la numeración real de
        su Diario ya alcanzó o superó su Número — Motivo y Fecha de Registro
        siempre se pueden editar."""
        self.ensure_one()
        if not self.diario_id or not self.numero:
            return False
        maximo = self.diario_id.l10n_py_correlativo_maximo_usado()
        correlativo = self.diario_id._l10n_py_correlativo(self.numero)
        return maximo is not None and correlativo is not None and correlativo <= maximo

    def write(self, vals):
        if 'diario_id' in vals or 'numero' in vals:
            for doc in self:
                if doc._esta_bloqueado():
                    raise exceptions.UserError(
                        'No se puede modificar el Diario ni el Número de este Documento '
                        'Anulado — la numeración real de "%s" ya alcanzó el Número %s. '
                        'Motivo y Fecha de Registro sí se pueden editar.'
                        % (doc.diario_id.name, doc.numero)
                    )
        return super().write(vals)

    def unlink(self):
        for doc in self:
            if doc._esta_bloqueado():
                raise exceptions.UserError(
                    'No se puede eliminar este Documento Anulado — la numeración real de '
                    '"%s" ya alcanzó el Número %s.' % (doc.diario_id.name, doc.numero)
                )
        return super().unlink()
