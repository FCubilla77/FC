# -*- coding: utf-8 -*-
import logging

from odoo import api, models

from .fe_py_licencia import fe_py_licencia_vigente

_logger = logging.getLogger(__name__)


class FePyDocumentoElectronico(models.Model):
    _inherit = 'fe_py.documento_electronico'

    @api.model
    def _cron_reintentar_pendientes(self):
        """Reintenta (Generar XML -> Firmar -> Enviar) todos los Documentos
        Electrónicos en Rechazado o Error de Comunicación, de las
        Compañías con "Reintentar Automáticamente" activo. Si el dato que
        causó el problema todavía no se corrigió, el reintento simplemente
        vuelve a fallar (queda registrado en el Log, como cualquier otro
        intento) y sigue esperando el próximo ciclo — no hace falta ningún
        marcador de "ya corregido"."""
        # Las compañías con reintento activo se resuelven contra el modelo
        # de configuración: en res.company esos campos son un espejo NO
        # almacenado, y Odoo no puede filtrar por campos así.
        companias = self.env['fe_py.configuracion'].sudo().search([
            ('reintento_automatico', '=', True),
        ]).mapped('company_id')
        # El cron omite en silencio las compañías sin licencia válida de FE_Py:
        # no tiene sentido reintentar un envío que el control de licencia va a
        # rechazar, y un cron no es el lugar para avisarle nada al usuario (el
        # aviso lo da la pantalla de Licencia y el bloqueo al confirmar).
        companias = companias.filtered(
            lambda c: fe_py_licencia_vigente(self.env, c))
        if not companias:
            return
        docs = self.search([
            ('estado', 'in', ('rechazado', 'error_comunicacion')),
            ('company_id', 'in', companias.ids),
        ])
        for doc in docs:
            try:
                doc.action_generar_xml()
                doc.action_firmar()
                doc.action_enviar()
            except Exception:
                _logger.warning(
                    "FE_Py: el cron de reintento no pudo procesar el "
                    "Documento Electrónico %s (comprobante %s) — sigue "
                    "esperando el próximo ciclo.",
                    doc.id, doc.move_id.display_name, exc_info=True,
                )


class FePyEvento(models.Model):
    _inherit = 'fe_py.evento'

    @api.model
    def _cron_reintentar_pendientes(self):
        """Mismo criterio que el de Documento Electrónico, para Eventos
        (Cancelación e Inutilización) en Rechazado o Error de
        Comunicación."""
        companias = self.env['fe_py.configuracion'].sudo().search([
            ('reintento_automatico', '=', True),
        ]).mapped('company_id')
        # El cron omite en silencio las compañías sin licencia válida de FE_Py:
        # no tiene sentido reintentar un envío que el control de licencia va a
        # rechazar, y un cron no es el lugar para avisarle nada al usuario (el
        # aviso lo da la pantalla de Licencia y el bloqueo al confirmar).
        companias = companias.filtered(
            lambda c: fe_py_licencia_vigente(self.env, c))
        if not companias:
            return
        eventos = self.search([
            ('estado', 'in', ('rechazado', 'error_comunicacion')),
            ('company_id', 'in', companias.ids),
        ])
        for evento in eventos:
            try:
                evento.action_enviar()
            except Exception:
                _logger.warning(
                    "FE_Py: el cron de reintento no pudo procesar el Evento "
                    "%s — sigue esperando el próximo ciclo.",
                    evento.id, exc_info=True,
                )
