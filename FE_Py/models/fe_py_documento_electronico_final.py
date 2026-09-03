# -*- coding: utf-8 -*-
"""Documento fiscal definitivo y trazabilidad.

Se guardan 3 XML por documento, no uno solo:

  1. xml_generado  - armado, sin firmar
  2. xml_firmado   - con la firma digital
  3. xml_final     - firmado + QR + protocolo de autorización

El tercero es el que corresponde archivar como documento fiscal: es el
único que coincide con lo que SIFEN tiene registrado. Se arma acá y no se
toma de la respuesta de SIFEN, porque la respuesta del WS no devuelve el
XML reconstruido — pero sí tenemos todas las piezas para armarlo.

Además se guarda la respuesta SOAP cruda completa (respuesta_sifen_raw),
aparte del Log, para tener el original sin interpretar.
"""
import logging

from lxml import etree

from odoo import exceptions, fields, models

_logger = logging.getLogger(__name__)

SIFEN_NS = 'http://ekuatia.set.gov.py/sifen/xsd'


class FePyDocumentoElectronico(models.Model):
    _inherit = 'fe_py.documento_electronico'

    protocolo_autorizacion = fields.Char(
        string='Protocolo de Autorización', copy=False, readonly=True,
        help='Número devuelto por SIFEN al aprobar el documento (dProtAut). '
             'Forma parte del XML final.',
    )
    respuesta_sifen_raw = fields.Text(
        string='Respuesta SIFEN (cruda)', copy=False, readonly=True,
        help='Respuesta SOAP completa de SIFEN, tal cual llegó, sin '
             'interpretar. Se guarda aparte del Log para conservar el '
             'original íntegro.',
    )
    xml_final = fields.Text(
        string='XML Final (documento fiscal)', copy=False, readonly=True,
        help='XML firmado + código QR + protocolo de autorización. Es el '
             'documento fiscal definitivo, el que corresponde archivar.',
    )

    def _fe_py_generar_xml_final(self):
        """Reconstruye el XML definitivo sobre la copia ya firmada.

        Estructura, confirmada contra XML reales de producción — los 3
        elementos van DESPUÉS del bloque <Signature>, dentro de <rDE>:

            <gCamFuFD><dCarQR>...</dCarQR></gCamFuFD>
            <dProtAut>...</dProtAut>
            <xContEv></xContEv>

        No modifica el XML firmado original: trabaja sobre una copia, así
        la firma guardada queda intacta para auditoría.
        """
        self.ensure_one()
        if not self.xml_firmado:
            raise exceptions.UserError(
                'No hay XML firmado: no se puede armar el documento final.'
            )

        # El QR se calcula sobre el XML firmado (necesita el DigestValue de
        # la firma), así que se genera acá si todavía no existe.
        qr_url = self.qr_url or self._fe_py_generar_qr_url()
        if not self.qr_url:
            self.qr_url = qr_url

        root = etree.fromstring(self.xml_firmado.encode('utf-8'))

        # Idempotente: si ya se armó antes (por un reintento), se limpian
        # los elementos previos en vez de duplicarlos.
        for tag in ('gCamFuFD', 'dProtAut', 'xContEv'):
            for viejo in root.findall('{%s}%s' % (SIFEN_NS, tag)):
                root.remove(viejo)

        g_qr = etree.SubElement(root, '{%s}gCamFuFD' % SIFEN_NS)
        el_qr = etree.SubElement(g_qr, '{%s}dCarQR' % SIFEN_NS)
        el_qr.text = qr_url

        if self.protocolo_autorizacion:
            el_prot = etree.SubElement(root, '{%s}dProtAut' % SIFEN_NS)
            el_prot.text = self.protocolo_autorizacion

        etree.SubElement(root, '{%s}xContEv' % SIFEN_NS)

        self.xml_final = etree.tostring(
            root, pretty_print=True, xml_declaration=True, encoding='UTF-8'
        ).decode('utf-8')
        return True
