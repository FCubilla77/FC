# -*- coding: utf-8 -*-
from odoo import api, models

from .l10n_py_licencia import l10n_py_licencia_verificar


class L10nPyMixinLicencia(models.AbstractModel):
    """Bloquea la CREACIÓN si la compañía no tiene una licencia válida.

    Se agrega por `_inherit` solo a los modelos propios de l10n_py que lo requieran.
    Nunca se aplica a informes, líneas de detalle ni a modelos nativos de Odoo."""
    _name = 'l10n_py.mixin.licencia'
    _description = "Control de licencia l10n_py: creación"

    @api.model_create_multi
    def create(self, vals_list):
        Company = self.env['res.company']
        for vals in vals_list:
            l10n_py_licencia_verificar(
                self.env, Company.browse(vals['company_id']) if vals.get('company_id') else None)
        return super().create(vals_list)


class L10nPyMixinLicenciaEdicion(models.AbstractModel):
    """Bloquea la EDICIÓN si la compañía no tiene una licencia válida.

    Solo para documentos de trabajo en curso (los que representan una operación
    activa). No se aplica a los maestros: una licencia vencida no debe impedir
    corregir un dato ya cargado."""
    _name = 'l10n_py.mixin.licencia.edicion'
    _description = "Control de licencia l10n_py: edición"

    def write(self, vals):
        if 'company_id' in self._fields:
            for company in self.mapped('company_id') or self.env.company:
                l10n_py_licencia_verificar(self.env, company)
        else:
            l10n_py_licencia_verificar(self.env, None)
        return super().write(vals)
