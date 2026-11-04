# -*- coding: utf-8 -*-
from odoo import api, models

from .local_py_licencia import local_py_licencia_verificar


class LocalPyMixinLicencia(models.AbstractModel):
    """Bloquea la CREACIÓN si la compañía no tiene una licencia válida.

    Se agrega por `_inherit` solo a los modelos propios de local_py que lo
    requieran. Nunca se aplica a informes, líneas de detalle ni a modelos nativos
    de Odoo."""
    _name = 'local_py.mixin.licencia'
    _description = "Control de licencia local_py: creación"

    @api.model_create_multi
    def create(self, vals_list):
        Company = self.env['res.company']
        for vals in vals_list:
            local_py_licencia_verificar(
                self.env,
                Company.browse(vals['company_id']) if vals.get('company_id') else None)
        return super().create(vals_list)


class LocalPyMixinLicenciaEdicion(models.AbstractModel):
    """Bloquea la EDICIÓN si la compañía no tiene una licencia válida.

    Solo para documentos de trabajo en curso (los que representan una operación
    activa) y para las Configuraciones Localización Py. No se aplica a los maestros:
    una licencia vencida no debe impedir corregir un dato ya cargado."""
    _name = 'local_py.mixin.licencia.edicion'
    _description = "Control de licencia local_py: edición"

    def write(self, vals):
        if 'company_id' in self._fields:
            for company in self.mapped('company_id') or self.env.company:
                local_py_licencia_verificar(self.env, company)
        else:
            local_py_licencia_verificar(self.env, None)
        return super().write(vals)
