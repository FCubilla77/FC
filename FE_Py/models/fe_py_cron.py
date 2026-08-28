# -*- coding: utf-8 -*-
import logging

from odoo import api, models

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
        docs = self.search([
            ('estado', 'in', ('rechazado', 'error_comunicacion')),
            ('company_id.fe_py_reintento_automatico', '=', True),
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
        eventos = self.search([
            ('estado', 'in', ('rechazado', 'error_comunicacion')),
            ('company_id.fe_py_reintento_automatico', '=', True),
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
