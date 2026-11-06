# -*- coding: utf-8 -*-
from odoo import api, models

from .fe_py_recepcion_licencia import fe_py_recepcion_licencia_verificar

# Campos técnicos de mail.thread que Odoo escribe solo al adjuntar archivos al chatter:
# no son una edición del documento y no deben bloquearse.
CAMPOS_TECNICOS_LIBRES = {'message_main_attachment_id'}


class FePyRecepcionMixinLicencia(models.AbstractModel):
    """Bloquea la CREACIÓN si la compañía no tiene una licencia válida.

    Se agrega por `_inherit` solo a los modelos propios del módulo que lo requieran.
    Nunca se aplica a líneas de detalle, cuotas ni a modelos nativos de Odoo."""
    _name = 'fe_py_recepcion.mixin.licencia'
    _description = "Control de licencia FE_Py Recepción: creación"

    @api.model_create_multi
    def create(self, vals_list):
        Company = self.env['res.company']
        for vals in vals_list:
            fe_py_recepcion_licencia_verificar(
                self.env,
                Company.browse(vals['company_id']) if vals.get('company_id') else None)
        return super().create(vals_list)


class FePyRecepcionMixinLicenciaEdicion(models.AbstractModel):
    """Bloquea la EDICIÓN si la compañía no tiene una licencia válida.

    Solo para los documentos de trabajo en curso (las recepciones). No se aplica a los
    maestros: una licencia vencida no debe impedir corregir un dato ya cargado."""
    _name = 'fe_py_recepcion.mixin.licencia.edicion'
    _description = "Control de licencia FE_Py Recepción: edición"

    def write(self, vals):
        if vals and set(vals) <= CAMPOS_TECNICOS_LIBRES:
            return super().write(vals)
        if 'company_id' in self._fields:
            for company in self.mapped('company_id') or self.env.company:
                fe_py_recepcion_licencia_verificar(self.env, company)
        else:
            fe_py_recepcion_licencia_verificar(self.env, None)
        return super().write(vals)
