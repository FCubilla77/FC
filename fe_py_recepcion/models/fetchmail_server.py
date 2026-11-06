# -*- coding: utf-8 -*-
import logging

from odoo import models

from .fe_py_recepcion_licencia import fe_py_recepcion_licencia_exenta

_logger = logging.getLogger(__name__)

MODELO_RECEPCION = 'fe_py_recepcion.documento'


class FetchmailServer(models.Model):
    _inherit = 'fetchmail.server'

    def _fetch_mail(self, *args, **kwargs):
        """No lee la casilla de recepción si la compañía no tiene licencia válida o si la
        cuenta no está asignada a una compañía: Odoo marca como leído todo correo que
        procesa, y así los correos con las facturas no se perderían sin haberse cargado."""
        servidores = self
        Company = self.env['res.company'].sudo()
        for servidor in self.filtered(lambda s: s.object_id.model == MODELO_RECEPCION):
            company = Company.search([('fe_py_recepcion_fetchmail_id', '=', servidor.id)], limit=1)
            if not company or not (fe_py_recepcion_licencia_exenta(self.env)
                                   or company._fe_py_recepcion_licencia_valida()):
                _logger.warning(
                    'FE_Py Recepción: no se lee la cuenta "%s" (sin compañía asignada o sin '
                    'licencia válida).', servidor.name)
                servidores -= servidor
        return super(FetchmailServer, servidores)._fetch_mail(*args, **kwargs)
