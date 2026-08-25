# -*- coding: utf-8 -*-
"""Generación del Código QR (algoritmo del Manual Técnico v150, cap.
13.8.4 — verificado computacionalmente contra el ejemplo oficial paso a
paso antes de escribir este archivo) y del KuDE en PDF.

Todos los valores del QR se extraen del propio xml_firmado (no se
recalculan por separado desde el comprobante), para garantizar que el QR
siempre valide exactamente contra lo que ya se firmó y se envió — esto
evita cualquier desincronización si el XML y el cálculo del QR se
obtuvieran de fuentes distintas.
"""
import base64
import hashlib
import logging
from collections import OrderedDict
from io import BytesIO

from lxml import etree

from odoo import exceptions, fields, models

_logger = logging.getLogger(__name__)

try:
    import qrcode
except ImportError:  # pragma: no cover
    qrcode = None
    _logger.warning(
        "FE_Py: no se encontró la librería 'qrcode' en el servidor — la "
        "generación del KuDE no va a funcionar hasta instalarla (pip "
        "install qrcode)."
    )

SIFEN_NS = 'http://ekuatia.set.gov.py/sifen/xsd'
DS_NS = 'http://www.w3.org/2000/09/xmldsig#'

QR_BASE_URLS = {
    'test': 'https://ekuatia.set.gov.py/consultas-test/qr?',
    'produccion': 'https://ekuatia.set.gov.py/consultas/qr?',
    # En Simulado no existe una consulta real detrás de este link, pero se
    # arma igual (con la URL de Test) para poder generar y ver el KuDE
    # completo, con QR, sin depender de tener Ambiente real configurado.
    'simulado': 'https://ekuatia.set.gov.py/consultas-test/qr?',
}


class FePyDocumentoElectronico(models.Model):
    _inherit = 'fe_py.documento_electronico'

    qr_image = fields.Binary(string='Imagen QR', copy=False, attachment=True)

    def action_generar_kude(self):
        for doc in self:
            if doc.estado not in ('aprobado', 'aprobado_observacion'):
                raise exceptions.UserError(
                    'Solo se puede generar el KuDE de un Documento '
                    'Electrónico Aprobado (estado actual de %s: %s).'
                    % (doc.move_id.display_name,
                       dict(doc._fields['estado'].selection).get(doc.estado))
                )
            doc._fe_py_generar_kude()
        return True

    def _fe_py_generar_kude(self):
        self.ensure_one()
        if qrcode is None:
            raise exceptions.UserError(
                'Falta instalar la librería "qrcode" en el servidor '
                '(pip install qrcode) para poder generar el KuDE.'
            )
        qr_url = self._fe_py_generar_qr_url()
        qr_image_b64 = self._fe_py_generar_imagen_qr(qr_url)

        self.write({'qr_url': qr_url, 'qr_image': qr_image_b64})

        report = self.env.ref('FE_Py.action_report_kude')
        pdf_content, _report_type = report._render_qweb_pdf(
            report.report_name, res_ids=self.ids
        )
        self.write({
            'kude_pdf': base64.b64encode(pdf_content),
            'kude_pdf_filename': 'KuDE_%s.pdf' % (self.cdc or self.move_id.id),
        })
        self.env['fe_py.documento_electronico.log'].sudo().create({
            'documento_id': self.id,
            'tipo_operacion': 'generacion_xml',
            'resultado': 'exito',
            'mensaje_resultado': 'KuDE generado (QR + PDF).',
        })

    # ------------------------------------------------------------------
    # Algoritmo del QR — Manual Técnico v150, cap. 13.8.4
    # ------------------------------------------------------------------
    def _fe_py_generar_qr_url(self):
        self.ensure_one()
        if not self.xml_firmado:
            raise exceptions.UserError('No hay XML firmado para generar el QR.')

        root = etree.fromstring(self.xml_firmado.encode('utf-8'))
        ns = {'s': SIFEN_NS, 'ds': DS_NS}

        de = root.find('.//s:DE', ns)
        d_fe_emi_de = de.find('.//s:gDatGralOpe/s:dFeEmiDE', ns).text
        d_ruc_rec = de.find('.//s:gDatRec/s:dRucRec', ns).text
        d_tot_gral_ope = de.find('.//s:gTotSub/s:dTotGralOpe', ns).text
        d_tot_iva = de.find('.//s:gTotSub/s:dTotIVA', ns).text
        c_items = len(de.findall('.//s:gCamItem', ns))
        digest_el = root.find('.//ds:DigestValue', ns)
        if digest_el is None or not digest_el.text:
            raise exceptions.UserError(
                'No se encontró el DigestValue de la firma dentro del XML firmado.'
            )
        digest_value = digest_el.text

        company = self.move_id.company_id
        journal = self.move_id.journal_id
        idcsc, csc = journal.fe_py_get_idcsc_csc()
        if not (idcsc and csc):
            raise exceptions.UserError(
                'Falta configurar IdCSC/CSC (Compañía o Diario) para poder generar el QR.'
            )

        qpd = OrderedDict()
        qpd['nVersion'] = self.version_formato or '150'
        qpd['Id'] = self.cdc
        qpd['dFeEmiDE'] = d_fe_emi_de.encode('utf-8').hex()
        qpd['dRucRec'] = d_ruc_rec
        qpd['dTotGralOpe'] = d_tot_gral_ope
        qpd['dTotIVA'] = d_tot_iva
        qpd['cItems'] = str(c_items)
        qpd['DigestValue'] = digest_value.encode('utf-8').hex()
        qpd['IdCSC'] = idcsc

        qpar = '&'.join('%s=%s' % (k, v) for k, v in qpd.items())
        qparsec = qpar + csc
        c_hash_qr = hashlib.sha256(qparsec.encode('utf-8')).hexdigest()
        qpar_final = qpar + '&cHashQR=' + c_hash_qr

        ambiente = company.fe_py_ambiente
        base_url = QR_BASE_URLS.get(ambiente, QR_BASE_URLS['test'])
        return base_url + qpar_final

    def _fe_py_generar_imagen_qr(self, url):
        """Devuelve la imagen QR como PNG en base64 (para el campo Binary
        y para embeber en el KuDE)."""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=6,
            border=2,  # ~10% del ancho, cumple el "quiet zone" mínimo exigido
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color='black', back_color='white')
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue())
