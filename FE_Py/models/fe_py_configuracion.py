# -*- coding: utf-8 -*-
"""Configuraciones Generales FEPy — una por Compañía.

Reemplaza a la sección de Facturación Electrónica que antes vivía en
Ajustes > Empresas. En la Compañía queda únicamente lo nativo de Odoo.

Sigue el mismo patrón que "Configuraciones Localización Py" de local_py:
un registro por Compañía, con pestañas por tema.
"""
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
except Exception:  # pragma: no cover
    pkcs12 = None
    _logger.warning(
        "FE_Py: no se encontró la librería 'cryptography' en el servidor — "
        "el botón 'Generar Certificados' no va a funcionar hasta instalarla."
    )

# Valores genéricos publicados por la DNIT para el Ambiente de Test.
IDCSC_GENERICO = '0001'
CSC_GENERICO = 'ABCD0000000000000000000000000000'

URLS_POR_DEFECTO = {
    'ws_recibe_test': 'https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl',
    'ws_recibe_prod': 'https://sifen.set.gov.py/de/ws/sync/recibe.wsdl',
    'ws_evento_test': 'https://sifen-test.set.gov.py/de/ws/eventos/evento.wsdl',
    'ws_evento_prod': 'https://sifen.set.gov.py/de/ws/eventos/evento.wsdl',
    'qr_test': 'https://ekuatia.set.gov.py/consultas-test/qr?',
    'qr_prod': 'https://ekuatia.set.gov.py/consultas/qr?',
    'consulta_test': 'https://ekuatia.set.gov.py/consultas-test',
    'consulta_prod': 'https://ekuatia.set.gov.py/consultas',
}


class FePyConfiguracion(models.Model):
    _name = 'fe_py.configuracion'
    _description = 'Configuraciones Generales FEPy'
    _rec_name = 'company_id'

    company_id = fields.Many2one(
        'res.company', string='Compañía', required=True,
        default=lambda self: self.env.company, ondelete='cascade', index=True,
    )

    # ------------------------------------------------------------------
    # Habilitación y ambiente
    # ------------------------------------------------------------------
    fe_py_habilitado = fields.Boolean(
        string='Facturador Electrónico',
        help='Activa el circuito de Facturación Electrónica (SIFEN) para esta '
             'Compañía. No se puede activar sin el Certificado generado y el '
             'IdCSC/CSC completos.',
    )
    fe_py_ambiente = fields.Selection(
        string='Ambiente FE',
        selection=[
            ('simulado', 'Simulado (sin conexión — pruebas internas)'),
            ('test', 'Test (SIFEN — Ambiente de Pruebas DNIT)'),
            ('produccion', 'Producción (SIFEN)'),
        ],
        default='simulado', required=True,
        help='"Simulado": ninguna conexión sale a la red. "Test"/"Producción": '
             'se conecta de verdad al SIFEN.',
    )

    # ------------------------------------------------------------------
    # Datos del Emisor (van al grupo gEmis del XML)
    # ------------------------------------------------------------------
    fe_py_tipo_contribuyente = fields.Selection(
        string='FEPy Tipo de Contribuyente',
        selection=[('1', 'Persona Física'), ('2', 'Persona Jurídica')],
        default='2',
        help='Se informa como iTipCont. Es un dato de la empresa emisora.',
    )
    fe_py_tipo_regimen_id = fields.Many2one(
        'fe_py.tipo_regimen', string='FEPy Tipo de Régimen',
        help='Se informa como cTipReg. Distinto de la Imputación Tributaria '
             'de local_py: acá van los 8 regímenes de la Tabla 1 del Manual '
             '(Turismo, Importador, Exportador, Maquila, Ley 60/90, etc.).',
    )
    fe_py_actividad_economica_ids = fields.Many2many(
        'fe_py.actividad_economica', string='FEPy Actividades Económicas',
        help='Actividades tal como están registradas ante la DNIT. Se informan '
             'todas en el XML (el grupo admite varias).',
    )

    # ------------------------------------------------------------------
    # Certificado digital
    # ------------------------------------------------------------------
    fe_py_certificado_file = fields.Binary(string='Certificado (.p12 / .pfx)', attachment=True)
    fe_py_certificado_filename = fields.Char(string='Nombre del Archivo')
    fe_py_certificado_password = fields.Char(string='Contraseña del Certificado')
    fe_py_cert_path = fields.Char(string='Ruta Certificado', readonly=True)
    fe_py_private_key_path = fields.Char(string='Ruta Clave Privada', readonly=True)
    fe_py_public_key_path = fields.Char(string='Ruta Clave Pública', readonly=True)
    fe_py_certificado_vencimiento = fields.Date(string='Vencimiento del Certificado', readonly=True)

    # ------------------------------------------------------------------
    # Código de Seguridad del Contribuyente
    # ------------------------------------------------------------------
    fe_py_idcsc = fields.Char(string='IdCSC', default=IDCSC_GENERICO)
    fe_py_csc = fields.Char(string='CSC', default=CSC_GENERICO)

    # ------------------------------------------------------------------
    # Automatización
    # ------------------------------------------------------------------
    fe_py_envio_automatico = fields.Boolean(
        string='Generar, Firmar y Enviar Automáticamente al Confirmar')
    fe_py_kude_automatico = fields.Boolean(
        string='Generar KuDE Automáticamente al Aprobarse')
    fe_py_email_automatico = fields.Boolean(
        string='Enviar Email al Cliente Automáticamente al Aprobarse')
    fe_py_reintento_automatico = fields.Boolean(
        string='Reintentar Automáticamente Rechazados / Error de Comunicación')

    # ------------------------------------------------------------------
    # URLs de los servicios de SIFEN
    # ------------------------------------------------------------------
    fe_py_ws_recibe_test = fields.Char(
        string='WS Recepción DE (Test)', default=URLS_POR_DEFECTO['ws_recibe_test'])
    fe_py_ws_recibe_prod = fields.Char(
        string='WS Recepción DE (Producción)', default=URLS_POR_DEFECTO['ws_recibe_prod'])
    fe_py_ws_evento_test = fields.Char(
        string='WS Eventos (Test)', default=URLS_POR_DEFECTO['ws_evento_test'])
    fe_py_ws_evento_prod = fields.Char(
        string='WS Eventos (Producción)', default=URLS_POR_DEFECTO['ws_evento_prod'])
    fe_py_qr_test = fields.Char(
        string='URL base del QR (Test)', default=URLS_POR_DEFECTO['qr_test'])
    fe_py_qr_prod = fields.Char(
        string='URL base del QR (Producción)', default=URLS_POR_DEFECTO['qr_prod'])
    fe_py_consulta_test = fields.Char(
        string='URL de consulta del KuDE (Test)', default=URLS_POR_DEFECTO['consulta_test'])
    fe_py_consulta_prod = fields.Char(
        string='URL de consulta del KuDE (Producción)', default=URLS_POR_DEFECTO['consulta_prod'])
    fe_py_timeout = fields.Integer(string='Tiempo de espera (segundos)', default=30)

    # ------------------------------------------------------------------
    # Valores por defecto del XML
    # ------------------------------------------------------------------
    fe_py_sistema_facturacion_id = fields.Many2one(
        'fe_py.sistema_facturacion', string='FEPy Sistema de Facturación',
        help='Se informa como dSisFact en todos los documentos.')
    fe_py_condicion_tipo_cambio_id = fields.Many2one(
        'fe_py.condicion_tipo_cambio', string='FEPy Condición del Tipo de Cambio',
        help='Se informa como dCondTiCam cuando la operación no es en Guaraníes.')
    fe_py_unidad_medida_id = fields.Many2one(
        'fe_py.unidad_medida', string='FEPy Unidad de Medida por Defecto',
        help='Se usa en las líneas de factura que no tienen producto '
             '(cargadas a mano), donde no hay de dónde tomar la unidad.')
    fe_py_tipo_documento_asociado_id = fields.Many2one(
        'fe_py.tipo_documento_asociado', string='FEPy Tipo de Documento Asociado',
        help='Se informa como iTipDocAso al referenciar la factura original '
             'desde una Nota de Crédito/Débito.')
    fe_py_tipo_emision_id = fields.Many2one(
        'fe_py.tipo_emision', string='FEPy Tipo de Emisión por Defecto',
        help='Se informa como iTipEmi. Normalmente "Normal".')

    _company_uniq = models.Constraint(
        'unique(company_id)',
        'Ya existe una Configuración FEPy para esta Compañía.',
    )

    # ------------------------------------------------------------------
    # Acceso desde el resto del módulo
    # ------------------------------------------------------------------
    @api.model
    def _get_config(self, company):
        """Devuelve la configuración de la Compañía, o lanza un error claro
        si todavía no fue creada. Es el único punto de entrada que usa el
        resto del módulo, para no repetir el search en cada archivo."""
        config = self.sudo().search([('company_id', '=', company.id)], limit=1)
        if not config:
            raise exceptions.UserError(
                'La Compañía "%s" no tiene Configuración de Facturación '
                'Electrónica. Crearla en Localización Paraguay > Facturación '
                'Electrónica Py > Configuraciones Generales FEPy.' % company.name
            )
        return config

    def fe_py_get_url(self, servicio):
        """URL del servicio pedido según el ambiente activo. En Simulado se
        devuelven las de Test: no se usan para conectarse (el Simulador no
        sale a la red), pero sí para armar el link del QR del KuDE."""
        self.ensure_one()
        es_prod = self.fe_py_ambiente == 'produccion'
        mapa = {
            'recibe': self.fe_py_ws_recibe_prod if es_prod else self.fe_py_ws_recibe_test,
            'evento': self.fe_py_ws_evento_prod if es_prod else self.fe_py_ws_evento_test,
            'qr': self.fe_py_qr_prod if es_prod else self.fe_py_qr_test,
            'consulta': self.fe_py_consulta_prod if es_prod else self.fe_py_consulta_test,
        }
        return mapa.get(servicio)

    # ------------------------------------------------------------------
    # Validaciones
    # ------------------------------------------------------------------
    @api.constrains('fe_py_habilitado', 'fe_py_cert_path', 'fe_py_idcsc', 'fe_py_csc')
    def _check_habilitado(self):
        for config in self:
            if config.fe_py_habilitado and not (
                config.fe_py_cert_path and config.fe_py_idcsc and config.fe_py_csc
            ):
                raise exceptions.ValidationError(
                    'Para activar "Facturador Electrónico" hay que generar el '
                    'Certificado y completar IdCSC y CSC.'
                )

    @api.onchange('fe_py_ambiente')
    def _onchange_fe_py_ambiente(self):
        """Pasar a Producción propone activar la Automatización, sin forzarla."""
        if self.fe_py_ambiente == 'produccion' and not (
            self.fe_py_envio_automatico or self.fe_py_kude_automatico
            or self.fe_py_email_automatico
        ):
            self.fe_py_envio_automatico = True
            self.fe_py_kude_automatico = True
            self.fe_py_email_automatico = True
            return {
                'warning': {
                    'title': 'Ambiente de Producción',
                    'message': (
                        'Se activó automáticamente "Generar, Firmar y Enviar", '
                        '"Generar KuDE" y "Enviar Email" — es una sugerencia '
                        'inicial, podés apagarlos si preferís empezar en manual.'
                    ),
                }
            }

    # ------------------------------------------------------------------
    # Certificado
    # ------------------------------------------------------------------
    def fe_py_generar_certificados(self):
        """Descompone el .p12/.pfx en Certificado y Clave Privada (.pem) y
        los deja escritos en el filesystem del servidor. La Clave Privada
        nunca queda guardada en la base de datos."""
        if pkcs12 is None:
            raise exceptions.UserError(
                'Falta instalar la librería "cryptography" en el servidor '
                'para poder generar los certificados.'
            )
        for config in self:
            if not (config.fe_py_certificado_file and config.fe_py_certificado_password):
                raise exceptions.UserError(
                    'Cargue el archivo del Certificado (.p12/.pfx) y su '
                    'Contraseña antes de generar los certificados.'
                )
            try:
                file_data = base64.b64decode(config.fe_py_certificado_file)
                password = config.fe_py_certificado_password.encode()
                private_key, certificate, _extra = pkcs12.load_key_and_certificates(
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
                    'No se pudo leer el Certificado: verifique el archivo y la '
                    'Contraseña. Detalle técnico: %s' % ex
                )

            company = config.company_id
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

            cert_path = os.path.join(target_dir, 'cert.pem')
            with open(cert_path, 'wb') as f:
                f.write(certificate.public_bytes(Encoding.PEM))

            public_key_path = os.path.join(target_dir, 'public_key.pem')
            with open(public_key_path, 'wb') as f:
                f.write(certificate.public_key().public_bytes(
                    encoding=Encoding.PEM, format=PublicFormat.SubjectPublicKeyInfo,
                ))

            vencimiento_dt = getattr(certificate, 'not_valid_after_utc', None) or certificate.not_valid_after
            config.write({
                'fe_py_cert_path': cert_path,
                'fe_py_private_key_path': private_key_path,
                'fe_py_public_key_path': public_key_path,
                'fe_py_certificado_vencimiento': vencimiento_dt.date(),
            })
        return True


class FePyTipoRegimen(models.Model):
    """cTipReg (D102) — Tabla 1 del Manual Técnico (8 regímenes)."""
    _name = 'fe_py.tipo_regimen'
    _inherit = 'fe_py.catalogo.base'
    _description = 'FEPy Tipo de Régimen'
