# -*- coding: utf-8 -*-
"""Documentos Anulados de FE_Py: números electrónicos inutilizados.

Tabla propia, separada de la que administra la localización. No es una
duplicación: son dos conjuntos disjuntos de números, cada uno con su
procedimiento de numeración.

  * La localización numera los Diarios de timbrado FÍSICO y lleva su
    propia tabla de documentos anulados.
  * FE_Py numera los Diarios ELECTRÓNICOS y lleva esta.

Ninguno de los dos consulta al otro: cada uno decide por un dato propio
—la localización por su marca de timbrado físico, FE_Py por el Tipo de
Documento Electrónico del Diario—. Por eso FE_Py puede instalarse sin
ninguna localización, y la localización funciona sin FE_Py.

Un número entra acá cuando un Evento de Inutilización lo reserva, y se
reserva ANTES de enviar el evento a SIFEN: así la numeración no vuelve a
ofrecerlo mientras el trámite está en curso. Si SIFEN rechaza el evento,
se intenta liberar — pero no se libera si la numeración real ya lo
superó, porque eso dejaría un hueco imposible de llenar.
"""

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class FePyDocumentoAnulado(models.Model):
    _name = 'fe_py.documento_anulado'
    _inherit = ['fe_py.mixin.licencia']
    _description = 'FEPy Documento Anulado (número electrónico inutilizado)'
    _order = 'journal_id, numero'

    journal_id = fields.Many2one(
        'account.journal', string='Diario', required=True, index=True,
        ondelete='cascade',
        domain="[('type', '=', 'sale'), ('fe_py_es_electronico', '=', True)]",
        help='Solo Diarios que emiten Documentos Electrónicos. Los números '
             'de un Diario de timbrado físico los administra la '
             'localización, en su propia tabla.',
    )
    company_id = fields.Many2one(
        related='journal_id.company_id', string='Compañía', store=True)
    numero = fields.Char(
        string='Número', size=15, required=True, index=True,
        help='Formato completo 001-001-0000001. Comparte Establecimiento y '
             'Punto de Expedición con el Diario.',
    )
    timbrado = fields.Integer(
        string='Timbrado', copy=False,
        help='Timbrado vigente en el Diario al momento de reservar el '
             'número. Queda congelado: no se actualiza si el Diario cambia '
             'de timbrado después.',
    )
    tipo_documento_id = fields.Many2one(
        'fe_py.tipo_documento', string='Tipo de Documento Electrónico',
        help='Se completa solo, desde el Diario, al registrar.',
    )
    motivo = fields.Char(string='Motivo', required=True)
    fecha_registro = fields.Date(
        string='Fecha de Registro', required=True,
        default=fields.Date.context_today,
    )
    evento_id = fields.Many2one(
        'fe_py.evento', string='Evento SIFEN', copy=False, index=True,
        ondelete='set null',
        help='Evento de Inutilización que reservó este número. Vacío si se '
             'cargó a mano.',
    )

    _journal_numero_uniq = models.Constraint(
        'unique(journal_id, numero)',
        'Ese número ya está registrado como anulado para ese Diario.',
    )

    @api.depends('numero', 'journal_id')
    def _compute_display_name(self):
        for reg in self:
            reg.display_name = '%s %s' % (reg.journal_id.name or '', reg.numero or '')

    @api.constrains('numero')
    def _check_fe_py_formato_numero(self):
        for reg in self:
            partes = (reg.numero or '').split('-')
            if (len(partes) != 3 or len(partes[0]) != 3 or len(partes[1]) != 3
                    or len(partes[2]) != 7 or not all(p.isdigit() for p in partes)):
                raise ValidationError(_(
                    'El número "%s" no tiene el formato 001-001-0000001.',
                    reg.numero or ''))

    @api.constrains('journal_id')
    def _check_fe_py_diario_electronico(self):
        for reg in self:
            if not reg.journal_id.fe_py_es_electronico:
                raise ValidationError(_(
                    'El Diario "%s" no emite Documentos Electrónicos. Los '
                    'números anulados de un Diario de timbrado físico los '
                    'administra la localización, en su propia tabla.',
                    reg.journal_id.name))

    @api.model_create_multi
    def create(self, vals_list):
        Journal = self.env['account.journal']
        for vals in vals_list:
            journal = Journal.browse(vals.get('journal_id'))
            if journal:
                mapa = self.env['fe_py.mapeo']._mapa()
                vals.setdefault('timbrado', self.env['fe_py.mapeo']._leer(
                    journal, 'journal_timbrado', mapa) or 0)
                vals.setdefault('tipo_documento_id',
                                journal.fe_py_tipo_documento_id.id)
        registros = super().create(vals_list)
        registros._check_fe_py_numero_no_usado()
        return registros

    def _check_fe_py_numero_no_usado(self):
        """Un número ya emitido en un comprobante real no se puede
        inutilizar: ese documento existe ante SIFEN."""
        Mapeo = self.env['fe_py.mapeo']
        campo = Mapeo._mapa().get('move_nro_documento')
        if not campo or campo not in self.env['account.move']._fields:
            return
        for reg in self:
            usado = self.env['account.move'].sudo().search_count([
                ('journal_id', '=', reg.journal_id.id),
                (campo, '=', reg.numero),
                ('state', '!=', 'cancel'),
            ])
            if usado:
                raise UserError(_(
                    'El número %(numero)s ya fue utilizado en un comprobante '
                    'del Diario "%(diario)s". No se puede inutilizar un '
                    'número que ya se emitió.',
                    numero=reg.numero, diario=reg.journal_id.name))

    def unlink(self):
        """No se libera un número que la numeración real ya superó:
        liberarlo dejaría un hueco imposible de volver a llenar."""
        for reg in self:
            maximo = reg.journal_id._fe_py_correlativo_maximo_usado()
            correlativo = reg.journal_id._fe_py_correlativo(reg.numero)
            if maximo is not None and correlativo is not None and correlativo <= maximo:
                raise UserError(_(
                    'No se puede liberar el número %(numero)s: la numeración '
                    'del Diario "%(diario)s" ya lo superó. Liberarlo dejaría '
                    'un hueco que no se puede volver a llenar.',
                    numero=reg.numero, diario=reg.journal_id.name))
        return super().unlink()
