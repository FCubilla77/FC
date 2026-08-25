# -*- coding: utf-8 -*-
import base64
import logging
import os
import re

from odoo import api, exceptions, fields, models

_logger = logging.getLogger(__name__)

try:
    from OpenSSL import crypto
except ImportError:  # pragma: no cover
    crypto = None
    _logger.warning(
        "FE_Py: no se encontró la librería 'pyOpenSSL' en el servidor — el "
        "botón 'Generar Certificados' no va a funcionar hasta instalarla "
        "(pip install pyOpenSSL)."
    )


class ResCompany(models.Model):
    _inherit = 'res.company'

    fe_py_habilitado = fields.Boolean(
        string='Facturador Electrónico',
        help='Activa el circuito de Facturación Electrónica (SIFEN) para esta '
             'Compañía. No se puede activar sin haber generado el Certificado '
             '(botón "Generar Certificados") y completado IdCSC y CSC.',
    )
    fe_py_ambiente = fields.Selection(
        string='Ambiente FE',
        selection=[
            ('simulado', 'Simulado (sin conexión — pruebas internas)'),
            ('test', 'Test (SIFEN — Ambiente de Pruebas DNIT)'),
            ('produccion', 'Producción (SIFEN)'),
        ],
        default='simulado', required=True,
        help='"Simulado": ninguna conexión sale a la red — las respuestas las '
             'genera el Simulador SIFEN interno de Odoo, para poder probar '
             'todo el circuito sin acceso real a la DNIT. "Test"/"Producción": '
             'se conecta de verdad al SIFEN (Ambiente de Pruebas o real, según '
             'corresponda).',
    )

    # ------------------------------------------------------------------
    # Certificado digital: se sube el .p12/.pfx + contraseña, y el botón
    # "Generar Certificados" lo descompone en Certificado y Clave Privada
    # (.pem), dejándolos escritos en el filesystem del servidor Odoo. La
    # Clave Privada NUNCA queda en un campo de la base de datos, solo su
    # ruta en disco — mismo criterio ya validado en producción por el
    # módulo de referencia tomado como base para este desarrollo.
    # ------------------------------------------------------------------
    fe_py_certificado_file = fields.Binary(
        string='Certificado Digital (.p12/.pfx)', copy=False, attachment=True,
        help='Certificado cualificado de firma electrónica del contribuyente, '
             'emitido por un Prestador de Servicios de Certificación habilitado.',
    )
    fe_py_certificado_filename = fields.Char(string='Nombre del Archivo', copy=False)
    fe_py_certificado_password = fields.Char(string='Contraseña del Certificado', copy=False)
    fe_py_cert_path = fields.Char(string='Ruta Certificado (.pem)', copy=False, readonly=True)
    fe_py_private_key_path = fields.Char(string='Ruta Clave Privada (.pem)', copy=False, readonly=True)
    fe_py_public_key_path = fields.Char(string='Ruta Clave Pública (.pem)', copy=False, readonly=True)
    fe_py_certificado_vencimiento = fields.Date(
        string='Vencimiento del Certificado', copy=False, readonly=True,
    )

    # -- CSC / IdCSC — genérico de Ambiente de Test por defecto ------------
    fe_py_idcsc = fields.Char(
        string='IdCSC', default='0001',
        help='Identificador del Código de Seguridad del Contribuyente. Trae '
             'por defecto el genérico del Ambiente de Test de la DNIT — '
             'reemplazar por el propio antes de pasar a Producción.',
    )
    fe_py_csc = fields.Char(
        string='CSC', default='ABCD0000000000000000000000000000',
        help='Código de Seguridad del Contribuyente, usado para generar el QR '
             'del KuDE. Trae por defecto el genérico del Ambiente de Test de '
             'la DNIT — reemplazar por el propio antes de pasar a Producción.',
    )

    @api.constrains('fe_py_habilitado')
    def _check_fe_py_habilitado_configuracion_completa(self):
        for company in self:
            if company.fe_py_habilitado and not (
                company.fe_py_cert_path and company.fe_py_private_key_path
                and company.fe_py_idcsc and company.fe_py_csc
            ):
                raise exceptions.ValidationError(
                    'Para activar "Facturador Electrónico" hay que generar el '
                    'Certificado (botón "Generar Certificados") y completar '
                    'IdCSC y CSC.'
                )

    def fe_py_generar_certificados(self):
        """Descompone el archivo .p12/.pfx subido en Certificado y Clave
        Privada (.pem) y los deja escritos en el filesystem del servidor."""
        if crypto is None:
            raise exceptions.UserError(
                'Falta instalar la librería "pyOpenSSL" en el servidor '
                '(pip install pyOpenSSL) para poder generar los certificados.'
            )
        for company in self:
            if not (company.fe_py_certificado_file and company.fe_py_certificado_password):
                raise exceptions.UserError(
                    'Cargue el archivo del Certificado (.p12/.pfx) y su '
                    'Contraseña antes de generar los certificados.'
                )
            try:
                file_data = base64.b64decode(company.fe_py_certificado_file)
                password = company.fe_py_certificado_password.encode()
                p12 = crypto.load_pkcs12(file_data, password)
            except Exception as ex:
                raise exceptions.UserError(
                    'No se pudo leer el Certificado: verifique el archivo y '
                    'la Contraseña. Detalle técnico: %s' % ex
                )

            home_directory = os.path.expanduser('~')
            clean_name = re.sub(r'[^a-zA-Z0-9]+', '_', company.name or 'compania').strip('_').lower()
            target_dir = os.path.join(
                home_directory, 'fe_py_certificados', '%s_%s' % (company.id, clean_name)
            )
            os.makedirs(target_dir, exist_ok=True)

            private_key = p12.get_privatekey()
            pk_pem = crypto.dump_privatekey(crypto.FILETYPE_PEM, private_key)
            private_key_path = os.path.join(target_dir, 'private_key.pem')
            with open(private_key_path, 'wb') as f:
                f.write(pk_pem)
            os.chmod(private_key_path, 0o600)

            certificate = p12.get_certificate()
            cert_pem = crypto.dump_certificate(crypto.FILETYPE_PEM, certificate)
            cert_path = os.path.join(target_dir, 'cert.pem')
            with open(cert_path, 'wb') as f:
                f.write(cert_pem)

            public_key_pem = crypto.dump_publickey(crypto.FILETYPE_PEM, certificate.get_pubkey())
            public_key_path = os.path.join(target_dir, 'public_key.pem')
            with open(public_key_path, 'wb') as f:
                f.write(public_key_pem)

            vencimiento_date = False
            asn1_vencimiento = certificate.get_notAfter()
            if asn1_vencimiento:
                try:
                    vencimiento_str = asn1_vencimiento.decode()
                    vencimiento_date = '%s-%s-%s' % (
                        vencimiento_str[0:4], vencimiento_str[4:6], vencimiento_str[6:8]
                    )
                except Exception:
                    vencimiento_date = False

            company.write({
                'fe_py_cert_path': cert_path,
                'fe_py_private_key_path': private_key_path,
                'fe_py_public_key_path': public_key_path,
                'fe_py_certificado_vencimiento': vencimiento_date,
            })
            _logger.info(
                "FE_Py: certificado generado para la compañía '%s' en %s",
                company.name, target_dir,
            )
