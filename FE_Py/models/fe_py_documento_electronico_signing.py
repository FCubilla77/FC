# -*- coding: utf-8 -*-
"""Firma electrónica del XML del DE, con el certificado digital propio de
la Compañía (generado en la Fase 2 vía "Generar Certificados"). Firma
local en el servidor Odoo, sin proveedor externo — mismo criterio que el
módulo de referencia tomado como base para este desarrollo."""
import logging
import os

from lxml import etree

from odoo import exceptions, fields, models

_logger = logging.getLogger(__name__)

try:
    import signxml
    from signxml import XMLSigner, XMLVerifier
except ImportError:  # pragma: no cover
    signxml = None
    XMLSigner = None
    XMLVerifier = None
    _logger.warning(
        "FE_Py: no se encontró la librería 'signxml' en el servidor — la "
        "firma electrónica no va a funcionar hasta instalarla (pip install signxml)."
    )

# Exclusive XML Canonicalization 1.0 — mismo algoritmo que exige SIFEN
# (ver <CanonicalizationMethod> en el XML de ejemplo del Manual Técnico).
C14N_ALGORITHM = 'http://www.w3.org/2001/10/xml-exc-c14n#'


class FePyDocumentoElectronico(models.Model):
    _inherit = 'fe_py.documento_electronico'

    def action_firmar(self):
        """Firma el XML ya generado (estado 'xml_generado') con el
        certificado de la Compañía. Deja el resultado en xml_firmado y
        pasa el estado a 'firmado'."""
        for doc in self:
            if doc.estado != 'xml_generado':
                raise exceptions.UserError(
                    'No se puede firmar: el Documento Electrónico de %s está '
                    'en estado "%s". Primero hay que generar el XML.'
                    % (doc.move_id.display_name, dict(doc._fields['estado'].selection).get(doc.estado))
                )
            doc._fe_py_firmar_xml()
        return True

    def _fe_py_leer_certificado_compania(self):
        self.ensure_one()
        company = self.move_id.company_id
        if not (company.fe_py_cert_path and company.fe_py_private_key_path):
            raise exceptions.UserError(
                'La Compañía "%s" no tiene Certificado generado — ir a Ajustes > '
                'Empresas, cargar el .p12/.pfx y usar el botón "Generar '
                'Certificados".' % company.name
            )
        if not os.path.exists(company.fe_py_cert_path) or not os.path.exists(company.fe_py_private_key_path):
            raise exceptions.UserError(
                'No se encuentran los archivos del Certificado en el servidor '
                '(¿se movieron o se borraron?). Volver a generar los '
                'certificados desde Ajustes > Empresas.'
            )
        try:
            with open(company.fe_py_cert_path, 'rb') as f:
                cert_pem = f.read()
            with open(company.fe_py_private_key_path, 'rb') as f:
                key_pem = f.read()
        except Exception as ex:
            raise exceptions.UserError(
                'No se pudo leer el Certificado del servidor. Detalle técnico: %s' % ex
            )
        return cert_pem, key_pem

    def _fe_py_firmar_xml(self):
        self.ensure_one()
        if XMLSigner is None:
            raise exceptions.UserError(
                'Falta instalar la librería "signxml" en el servidor '
                '(pip install signxml) para poder firmar.'
            )
        if not self.xml_generado:
            raise exceptions.UserError('No hay XML generado para firmar.')

        cert_pem, key_pem = self._fe_py_leer_certificado_compania()

        xml_root = etree.fromstring(self.xml_generado.encode('utf-8'))

        signer = XMLSigner(
            method=signxml.SignatureConstructionMethod.enveloped,
            signature_algorithm='rsa-sha256',
            digest_algorithm='sha256',
            c14n_algorithm=C14N_ALGORITHM,
        )
        # Namespace por defecto del bloque <Signature> — sin esto, signxml
        # genera <ds:Signature> con prefijo, y SIFEN exige el namespace por
        # defecto (sin prefijo), tal cual se ve en el XML de ejemplo.
        signer.namespaces = {None: signxml.namespaces.ds}

        try:
            signed_root = signer.sign(xml_root, key=key_pem, cert=cert_pem, reference_uri=self.cdc)
        except Exception as ex:
            self._fe_py_log_error_firma(ex)
            raise exceptions.UserError('Error al firmar el XML: %s' % ex)

        try:
            XMLVerifier().verify(signed_root, x509_cert=cert_pem)
        except Exception as ex:
            self._fe_py_log_error_firma(ex)
            raise exceptions.UserError(
                'El XML se firmó pero no pasó la verificación inmediata '
                '(no se guarda un XML firmado que no verifica). Detalle: %s' % ex
            )

        xml_firmado_str = etree.tostring(
            signed_root, pretty_print=True, xml_declaration=True, encoding='UTF-8'
        ).decode('utf-8')

        self.write({
            'xml_firmado': xml_firmado_str,
            'estado': 'firmado',
        })
        self.env['fe_py.documento_electronico.log'].sudo().create({
            'documento_id': self.id,
            'tipo_operacion': 'firma',
            'resultado': 'exito',
            'mensaje_resultado': 'XML firmado y verificado correctamente.',
        })

    def _fe_py_log_error_firma(self, ex):
        self.env['fe_py.documento_electronico.log'].sudo().create({
            'documento_id': self.id,
            'tipo_operacion': 'firma',
            'resultado': 'error',
            'mensaje_resultado': str(ex),
        })
