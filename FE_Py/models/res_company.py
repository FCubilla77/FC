# -*- coding: utf-8 -*-
import base64
import logging
import os
import re

from odoo import api, exceptions, fields, models

_logger = logging.getLogger(__name__)

try:
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, PublicFormat, pkcs12,
    )
except ImportError:  # pragma: no cover
    pkcs12 = None
    _logger.warning(
        "FE_Py: no se encontró la librería 'cryptography' en el servidor — "
        "el botón 'Generar Certificados' no va a funcionar hasta instalarla "
        "(pip install cryptography)."
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

    @api.onchange('fe_py_ambiente')
    def _onchange_fe_py_ambiente(self):
        """Pasar a Producción PROPONE activar la Automatización (para que
        no haga falta acordarse de prenderla aparte) — pero no la fuerza:
        sigue siendo editable de forma independiente después, para poder
        arrancar Producción en modo manual unos días, o frenar todo de
        urgencia sin tener que salir de Producción."""
        if self.fe_py_ambiente == 'produccion' and not (
            self.fe_py_envio_automatico or self.fe_py_kude_automatico or self.fe_py_email_automatico
        ):
            self.fe_py_envio_automatico = True
            self.fe_py_kude_automatico = True
            self.fe_py_email_automatico = True
            return {
                'warning': {
                    'title': 'Ambiente de Producción',
                    'message': (
                        'Se activó automáticamente "Generar, Firmar y Enviar", '
                        '"Generar KuDE" y "Enviar Email" — es solo una '
                        'sugerencia inicial, podés apagarlos de nuevo acá '
                        'mismo si preferís empezar Producción en modo manual.'
                    ),
                }
            }

    # ------------------------------------------------------------------
    # Automatización — todos apagados por defecto (modo manual, el que se
    # usó durante el desarrollo/pruebas). Se prenden cuando se quiera pasar
    # al comportamiento de producción (el usuario solo Confirma, el resto
    # es automático). Separados en 3, no uno solo, para poder automatizar
    # la parte técnica sin necesariamente automatizar también el envío de
    # email al cliente.
    # ------------------------------------------------------------------
    fe_py_envio_automatico = fields.Boolean(
        string='Generar, Firmar y Enviar Automáticamente al Confirmar',
        help='Si está activo, al Confirmar una Factura/NC/ND Electrónica se '
             'genera el XML, se firma y se envía a SIFEN automáticamente, '
             'sin usar los botones manuales. Si algún paso falla, la '
             'Confirmación de la factura NO se ve afectada — el Documento '
             'Electrónico queda en el estado correspondiente (Error de '
             'Comunicación / Rechazado), listo para reintentar a mano con '
             '"Reescribir XML y Reenviar".',
    )
    fe_py_kude_automatico = fields.Boolean(
        string='Generar KuDE Automáticamente al Aprobarse',
        help='Solo tiene efecto si "Enviar Automáticamente" también está '
             'activo. Genera el KuDE apenas el envío da Aprobado o '
             'Aprobado con Observación.',
    )
    fe_py_email_automatico = fields.Boolean(
        string='Enviar Email al Cliente Automáticamente al Aprobarse',
        help='Solo tiene efecto si "Enviar Automáticamente" también está '
             'activo. Requiere que el KuDE se haya podido generar (a mano, '
             'o con "Generar KuDE Automáticamente" también activo).',
    )
    fe_py_reintento_automatico = fields.Boolean(
        string='Reintentar Automáticamente Rechazados/Error de Comunicación',
        help='Activa un proceso programado (cada 30 minutos por defecto — '
             'editable en Ajustes > Técnico > Acciones Planificadas) que '
             'reintenta solo (Regenerar XML/Firmar/Enviar) todos los '
             'Documentos Electrónicos y Eventos en estado Rechazado o Error '
             'de Comunicación de esta Compañía. Si el dato que causó el '
             'problema todavía no se corrigió, simplemente vuelve a fallar '
             'y sigue esperando el próximo ciclo.',
    )

    # ------------------------------------------------------------------
    # Datos del Emisor exigidos por el XML del DE (grupo gEmis) que no
    # existen en local_py — este módulo no cubre datos de "papel", solo
    # los que la DNIT exige específicamente para SIFEN.
    # ------------------------------------------------------------------
    fe_py_tipo_contribuyente = fields.Selection(
        string='Tipo de Contribuyente',
        selection=[('1', 'Persona Física'), ('2', 'Persona Jurídica')],
        default='2',
        help='Va tal cual en el CDC y en el XML del DE (iTipCont/gEmis).',
    )
    fe_py_tipo_regimen = fields.Selection(
        string='Tipo de Régimen',
        selection=[
            ('1', 'Régimen de Turismo'),
            ('2', 'Importador'),
            ('3', 'Exportador'),
            ('4', 'Maquila'),
            ('5', 'Ley N° 60/90'),
            ('6', 'Régimen del Pequeño Productor'),
            ('7', 'Régimen del Mediano Productor'),
            ('8', 'Régimen Contable'),
        ],
        default='8',
        help='Va en el XML del DE (cTipReg/gEmis).',
    )
    fe_py_actividad_economica_codigo = fields.Char(
        string='Código de Actividad Económica',
        help='Según Tabla de Actividades Económicas de la DNIT — debe '
             'corresponder a lo declarado en el RUC. Va en el XML del DE '
             '(gActEco/cActEco).',
    )
    fe_py_actividad_economica_desc = fields.Char(
        string='Descripción de Actividad Económica',
        help='Va en el XML del DE (gActEco/dDesActEco), referida al código de arriba.',
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
        if pkcs12 is None:
            raise exceptions.UserError(
                'Falta instalar la librería "cryptography" en el servidor '
                '(pip install cryptography) para poder generar los certificados.'
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
                private_key, certificate, _extra_certs = pkcs12.load_key_and_certificates(
                    file_data, password
                )
                if private_key is None or certificate is None:
                    raise exceptions.UserError(
                        'El archivo no contiene clave privada y/o certificado.'
                    )
            except exceptions.UserError:
                raise
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

            pk_pem = private_key.private_bytes(
                encoding=Encoding.PEM,
                format=PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=NoEncryption(),
            )
            private_key_path = os.path.join(target_dir, 'private_key.pem')
            with open(private_key_path, 'wb') as f:
                f.write(pk_pem)
            os.chmod(private_key_path, 0o600)

            cert_pem = certificate.public_bytes(Encoding.PEM)
            cert_path = os.path.join(target_dir, 'cert.pem')
            with open(cert_path, 'wb') as f:
                f.write(cert_pem)

            public_key_pem = certificate.public_key().public_bytes(
                encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo,
            )
            public_key_path = os.path.join(target_dir, 'public_key.pem')
            with open(public_key_path, 'wb') as f:
                f.write(public_key_pem)

            # not_valid_after_utc es la API vigente (cryptography >= 42); en
            # versiones más viejas del paquete todavía hay que usar
            # not_valid_after (naive, sin timezone) — se soportan ambas.
            vencimiento_dt = getattr(certificate, 'not_valid_after_utc', None) or certificate.not_valid_after
            vencimiento_date = vencimiento_dt.date()

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
