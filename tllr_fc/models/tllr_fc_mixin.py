# -*- coding: utf-8 -*-
from odoo import fields, models


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


class TllrFcMixinCubierta(models.AbstractModel):
    """Control de adicionales por cantidad (repuestos y servicios de la OT).

    Cada línea recuerda hasta qué cantidad está cubierta (por el inicio de la OT, por el
    presupuesto o por una aprobación). Lo que la supera después de iniciada la OT es un
    excedente pendiente de aprobación: no se utiliza (si la aprobación es obligatoria) ni
    se factura hasta aprobarlo.
    """
    _name = 'tllr_fc.mixin.cubierta'
    _description = "Taller: cantidad cubierta de una línea"

    cantidad_cubierta = fields.Float(
        string="Cantidad cubierta", copy=False, readonly=True, digits='Product Unit',
        help="Cantidad cubierta por el inicio de la OT, el presupuesto o una aprobación. "
             "Subir la cantidad por encima genera un excedente pendiente de aprobación.")

    def _tllr_fc_cantidad_pedida(self):
        """Cantidad que se controla (la define cada modelo)."""
        raise NotImplementedError()

    def _tllr_fc_aplica_aprobacion(self):
        """El control de excedentes rige con la OT iniciada, en OT de cliente y, en garantía,
        solo en lo que se cobra al cliente."""
        self.ensure_one()
        ot = self.ot_id
        if ot.state == 'espera':
            return False
        return ot.tipo == 'cliente' or (ot.tipo == 'garantia' and self.cobrar_cliente)

    def _tllr_fc_calcular_excedente(self):
        self.ensure_one()
        if not self._tllr_fc_aplica_aprobacion():
            return 0.0
        excedente = self._tllr_fc_cantidad_pedida() - self.cantidad_cubierta
        return excedente if excedente > 1e-6 else 0.0

    def _tllr_fc_cantidad_aprobada(self, cantidad):
        """Parte de `cantidad` que se puede presupuestar y facturar (la cubierta)."""
        self.ensure_one()
        if self.state_aprobacion == 'pendiente':
            return 0.0
        if self._tllr_fc_aplica_aprobacion():
            return max(min(cantidad, self.cantidad_cubierta), 0.0)
        return cantidad

    def _tllr_fc_iniciar_cubierta(self):
        """Al crear la línea: cubierta salvo que nazca pendiente de aprobación."""
        for linea in self:
            linea.with_context(tllr_fc_permitir_write=True).cantidad_cubierta = (
                0.0 if linea.state_aprobacion == 'pendiente' else linea._tllr_fc_cantidad_pedida())

    def _tllr_fc_seguir_cantidad_en_espera(self):
        """Con la OT en espera la cantidad cubierta acompaña a la cantidad (cambios libres)."""
        for linea in self:
            if linea.ot_id.state == 'espera' and linea.state_aprobacion != 'pendiente':
                linea.with_context(tllr_fc_permitir_write=True).cantidad_cubierta = (
                    linea._tllr_fc_cantidad_pedida())

    def _tllr_fc_cubrir(self):
        """Aprobado o autorizado: la cantidad cubierta llega a lo pedido."""
        for linea in self:
            linea.with_context(tllr_fc_permitir_write=True).cantidad_cubierta = (
                linea._tllr_fc_cantidad_pedida())

    def _tllr_fc_ajustar_a_presupuesto(self):
        """El presupuesto actualizado pasa a ser lo acordado: la cubierta lo sigue hacia abajo."""
        for linea in self:
            if linea.state_aprobacion == 'pendiente':
                continue
            pedida = linea._tllr_fc_cantidad_pedida()
            if linea.cantidad_cubierta - pedida > 1e-6:
                linea.with_context(tllr_fc_permitir_write=True).cantidad_cubierta = pedida
