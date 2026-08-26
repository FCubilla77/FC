# -*- coding: utf-8 -*-
import base64
import logging

from odoo import exceptions, fields, models

_logger = logging.getLogger(__name__)


class FePyDocumentoElectronicoLog(models.Model):
    _inherit = 'fe_py.documento_electronico.log'

    tipo_operacion = fields.Selection(
        selection_add=[('envio_email', 'Envío por Email al Cliente')],
        ondelete={'envio_email': 'cascade'},
    )


class FePyDocumentoElectronico(models.Model):
    _inherit = 'fe_py.documento_electronico'

    email_enviado = fields.Boolean(string='Email Enviado al Cliente', copy=False)
    fecha_email_enviado = fields.Datetime(string='Fecha Envío Email', copy=False)

    def action_enviar_email_cliente(self):
        """Envía el XML y el KuDE (PDF) al Cliente del comprobante, como
        adjuntos de un correo simple. Requiere que el KuDE ya esté
        generado (botón "Generar KuDE")."""
        for doc in self:
            if doc.estado not in ('aprobado', 'aprobado_observacion'):
                raise exceptions.UserError(
                    'Solo se puede enviar por email un Documento '
                    'Electrónico Aprobado.'
                )
            if not doc.kude_pdf:
                raise exceptions.UserError(
                    'Generá primero el KuDE (botón "Generar KuDE") antes de enviarlo por email.'
                )
            doc._fe_py_enviar_email_cliente()
        return True

    def _fe_py_enviar_email_cliente(self):
        self.ensure_one()
        move = self.move_id
        partner = move.partner_id
        if not partner.email:
            raise exceptions.UserError(
                'El Cliente "%s" no tiene un email cargado.' % partner.display_name
            )

        nombre_base = self._fe_py_get_nombre_base_archivo()
        xml_attachment_name = nombre_base + '.xml'
        kude_attachment_name = self.kude_pdf_filename or (nombre_base + '.pdf')

        attachments = []
        if self.xml_firmado:
            attachments.append((
                xml_attachment_name,
                base64.b64encode(self.xml_firmado.encode('utf-8')),
            ))
        attachments.append((kude_attachment_name, self.kude_pdf))

        asunto = 'Documento Electrónico %s - %s' % (move.name or '', move.company_id.name)
        cuerpo = (
            '<p>Estimado/a %s,</p>'
            '<p>Adjuntamos el Documento Electrónico correspondiente a %s, '
            'CDC: %s.</p>'
            '<p>Saludos,<br/>%s</p>'
        ) % (partner.name or '', move.name or '', self.cdc or '', move.company_id.name)

        mail_values = {
            'subject': asunto,
            'body_html': cuerpo,
            'email_to': partner.email,
            'email_from': move.company_id.email or self.env.user.email,
            'attachment_ids': [
                (0, 0, {
                    'name': name,
                    'datas': datas,
                    'res_model': 'fe_py.documento_electronico',
                    'res_id': self.id,
                })
                for name, datas in attachments
            ],
        }
        mail = self.env['mail.mail'].sudo().create(mail_values)
        mail.send()

        # mail.send() NO propaga una excepción cuando falla el envío SMTP
        # (por defecto la absorbe y la deja registrada en el propio
        # mail.mail) — hay que revisar el estado real, si no se puede
        # terminar marcando "Email Enviado" sin que se haya enviado nada.
        if mail.state == 'exception':
            self.env['fe_py.documento_electronico.log'].sudo().create({
                'documento_id': self.id,
                'tipo_operacion': 'envio_email',
                'resultado': 'error',
                'mensaje_resultado': 'Error al enviar el email: %s' % (mail.failure_reason or 'motivo desconocido'),
            })
            raise exceptions.UserError(
                'No se pudo enviar el email. Detalle: %s\n\n'
                'Revisar la configuración del servidor de correo saliente '
                '(Ajustes > Técnico > Correo Saliente).'
                % (mail.failure_reason or 'motivo desconocido')
            )

        self.write({'email_enviado': True, 'fecha_email_enviado': fields.Datetime.now()})
        self.env['fe_py.documento_electronico.log'].sudo().create({
            'documento_id': self.id,
            'tipo_operacion': 'envio_email',
            'resultado': 'exito',
            'mensaje_resultado': 'XML y KuDE enviados por email a %s.' % partner.email,
        })
