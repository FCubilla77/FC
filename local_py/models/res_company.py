# -*- coding: utf-8 -*-

from odoo import models, fields, api, exceptions


class ResCompany(models.Model):
    _inherit = 'res.company'

    city_id = fields.Many2one(
        'res.city', string='Ciudad', domain="[('state_id', '=', state_id)]",
    )

    l10n_py_imputacion_tributaria_ids = fields.Many2many(
        'local_py.imputacion_tributaria',
        string='Imputación Tributaria',
        help='Régimen(es) tributario(s) bajo el/los que opera la compañía '
             '(IVA, IRE, IRP-RSP). "No Imputa" no puede combinarse con las '
             'otras opciones.',
    )

    @api.onchange('l10n_py_imputacion_tributaria_ids')
    def _onchange_l10n_py_imputacion_tributaria_ids(self):
        no_imputa = self.env.ref('local_py.imputacion_no_imputa', raise_if_not_found=False)
        if not no_imputa:
            return
        for company in self:
            current = company.l10n_py_imputacion_tributaria_ids
            previous = company._origin.l10n_py_imputacion_tributaria_ids
            added = current - previous
            if no_imputa in added:
                company.l10n_py_imputacion_tributaria_ids = current.filtered(lambda t: t.id == no_imputa.id)
            elif no_imputa in current and (current - no_imputa):
                company.l10n_py_imputacion_tributaria_ids = current - no_imputa

    @api.constrains('l10n_py_imputacion_tributaria_ids')
    def _check_l10n_py_imputacion_tributaria_exclusiva(self):
        no_imputa = self.env.ref('local_py.imputacion_no_imputa', raise_if_not_found=False)
        if not no_imputa:
            return
        for company in self:
            tags = company.l10n_py_imputacion_tributaria_ids
            if no_imputa in tags and len(tags) > 1:
                raise exceptions.ValidationError(
                    '"No Imputa" no puede combinarse con IVA, IRE o IRP-RSP en la '
                    'imputación tributaria de la compañía.'
                )
