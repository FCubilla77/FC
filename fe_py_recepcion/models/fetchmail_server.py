# -*- coding: utf-8 -*-
import logging

from odoo import _, fields, models

from .fe_py_recepcion_licencia import fe_py_recepcion_licencia_exenta

_logger = logging.getLogger(__name__)

MODELO_RECEPCION = 'fe_py_recepcion.documento'


class FetchmailServer(models.Model):
    _inherit = 'fetchmail.server'

    def _fe_py_recepcion_company(self):
        """Compañía a la que pertenece esta cuenta de recepción (vacía si no se sabe).

        Es la compañía que la tiene asignada en Ajustes. Si ninguna cuenta está asignada y el
        sistema tiene una sola compañía, se asigna esa y queda reparado el vínculo."""
        self.ensure_one()
        Company = self.env['res.company'].sudo()
        company = Company.search([('fe_py_recepcion_fetchmail_id', '=', self.id)], limit=1)
        if company or self.object_id.model != MODELO_RECEPCION:
            return company
        if not Company.search_count([('fe_py_recepcion_fetchmail_id', '!=', False)]):
            companias = Company.search([])
            if len(companias) == 1:
                companias.fe_py_recepcion_fetchmail_id = self
                return companias
        return Company

    def _fetch_mail(self, *args, **kwargs):
        """No lee la casilla de recepción si la compañía no tiene licencia válida o si la
        cuenta no está asignada a una compañía: Odoo marca como leído todo correo que
        procesa, y así los correos con las facturas no se perderían sin haberse cargado.
        El motivo queda en "Último mensaje de error" de la cuenta."""
        servidores = self
        for servidor in self.filtered(lambda s: s.object_id.model == MODELO_RECEPCION):
            company = servidor._fe_py_recepcion_company()
            motivo = False
            if not company:
                motivo = _('FE_Py Recepción: la cuenta no está asignada a ninguna compañía. '
                           'Asígnela en Ajustes > Configuración FE_Py Recepción.')
            elif not (fe_py_recepcion_licencia_exenta(self.env)
                      or company._fe_py_recepcion_licencia_valida()):
                motivo = _('FE_Py Recepción: la compañía no tiene una licencia válida.')
            if motivo:
                _logger.warning('FE_Py Recepción: no se lee la cuenta "%s": %s', servidor.name, motivo)
                servidor.sudo().write({'error_date': fields.Datetime.now(), 'error_message': motivo})
                servidores -= servidor
        return super(FetchmailServer, servidores)._fetch_mail(*args, **kwargs)
