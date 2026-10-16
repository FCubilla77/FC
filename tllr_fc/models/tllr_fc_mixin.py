# -*- coding: utf-8 -*-
from odoo import models


class TllrFcMixinWizard(models.AbstractModel):
    """Utilidades para abrir los asistentes de excepción y de advertencia."""
    _name = 'tllr_fc.mixin.wizard'
    _description = "Taller: utilidades de asistentes"

    def _tllr_fc_banderas(self):
        """Banderas del módulo del contexto actual (se propagan entre asistentes)."""
        return {
            clave: valor for clave, valor in self.env.context.items()
            if clave.startswith('tllr_fc_')
        }

    def _tllr_fc_abrir_excepcion(self, accion, grupo, descripcion):
        """Abre el asistente de autorización del supervisor (o del administrador)."""
        self.ensure_one()
        contexto = dict(
            self._tllr_fc_banderas(),
            default_res_model=self._name,
            default_res_id=self.id,
            default_accion=accion,
            default_grupo_requerido=grupo,
            default_descripcion=descripcion,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': "Autorización requerida",
            'res_model': 'tllr_fc.wizard.excepcion',
            'view_mode': 'form',
            'target': 'new',
            'context': contexto,
        }

    def _tllr_fc_abrir_advertencia(self, accion, mensaje):
        """Abre el asistente de confirmación de advertencias no bloqueantes."""
        self.ensure_one()
        contexto = dict(
            self._tllr_fc_banderas(),
            default_res_model=self._name,
            default_res_id=self.id,
            default_accion=accion,
            default_mensaje=mensaje,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': "Advertencia",
            'res_model': 'tllr_fc.wizard.confirmar_advertencia',
            'view_mode': 'form',
            'target': 'new',
            'context': contexto,
        }
