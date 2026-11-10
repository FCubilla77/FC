# -*- coding: utf-8 -*-
from odoo import api, models

MODELO_RECEPCION = 'fe_py_recepcion.documento'


class MailThread(models.AbstractModel):
    _inherit = 'mail.thread'

    @api.model
    def message_process(self, model, message, custom_values=None, save_original=False,
                        strip_attachments=False, thread_id=None):
        """Si la compañía eligió no registrar los correos sin XML, un correo de la casilla de
        recepción que no trae XML (ni dentro de un ZIP) se lee y se descarta sin dejar registro.
        Odoo igual lo marca como leído. En cualquier otro caso el proceso es el estándar."""
        if model == MODELO_RECEPCION and not thread_id \
                and self.env.context.get('default_fetchmail_server_id') \
                and self.env[MODELO_RECEPCION]._correo_se_ignora(message):
            return False
        return super().message_process(
            model, message, custom_values=custom_values, save_original=save_original,
            strip_attachments=strip_attachments, thread_id=thread_id)
