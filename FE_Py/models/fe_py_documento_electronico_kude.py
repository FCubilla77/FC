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
except Exception:  # pragma: no cover
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

# URL "humana" que se imprime como texto junto al CDC en el KuDE (distinta
# de la URL completa del QR, que lleva todos los parámetros/hash).
CONSULTA_BASE_URLS = {
    'test': 'https://ekuatia.set.gov.py/consultas-test',
    'produccion': 'https://ekuatia.set.gov.py/consultas',
    'simulado': 'https://ekuatia.set.gov.py/consultas-test',
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
            'kude_pdf_filename': self._fe_py_get_nombre_base_archivo() + '.pdf',
        })
        self.env['fe_py.documento_electronico.log'].sudo().create({
            'documento_id': self.id,
            'tipo_operacion': 'generacion_xml',
            'resultado': 'exito',
            'mensaje_resultado': 'KuDE generado (QR + PDF).',
        })

    def _fe_py_get_nombre_base_archivo(self):
        """Nombre base (sin extensión) usado tanto para el KuDE como para
        el XML adjunto por email: '<Tipo Fiscal> <Nro Documento>' — ej.
        'Factura Electronica 001-001-0000123'."""
        self.ensure_one()
        tipo = self.tipo_fiscal_id.name or 'Documento Electronico'
        nro = self.move_id.l10n_py_nro_documento or self.move_id.name or str(self.move_id.id)
        return '%s %s' % (tipo, nro)

    def _fe_py_get_tipo_operacion_desc(self):
        """Misma clasificación (bienes/servicios/mixto) que ya se usa al
        armar iTipTra en el XML (Fase 3) — se replica acá para mostrar la
        misma descripción en el KuDE, sin duplicar la fuente de verdad del
        cálculo en sí (llama al mismo criterio)."""
        self.ensure_one()
        lineas = self.move_id.invoice_line_ids.filtered(
            lambda l: l.display_type not in ('line_section', 'line_note')
        )
        tipos_producto = set(lineas.mapped('product_id.type'))
        if tipos_producto and tipos_producto <= {'service'}:
            return 'Prestación de servicios'
        if tipos_producto and 'service' not in tipos_producto:
            return 'Venta de mercadería'
        return 'Mixto (Venta de mercadería y servicios)'

    def _fe_py_get_cdc_formateado(self):
        self.ensure_one()
        cdc = self.cdc or ''
        return ' '.join(cdc[i:i + 4] for i in range(0, len(cdc), 4))

    def _fe_py_get_total_descuento(self):
        self.ensure_one()
        lineas = self.move_id.invoice_line_ids.filtered(
            lambda l: l.display_type not in ('line_section', 'line_note')
        )
        return sum((l.price_unit * l.quantity) * (l.discount or 0) / 100 for l in lineas)

    def _fe_py_get_redondeo(self):
        """Diferencia entre la suma de los subtotales por tasa (antes de
        redondear) y el Total General ya redondeado por Odoo. No
        implementa la regla de redondeo SEDECO en sí (a la denominación
        más chica disponible en Guaraníes) — solo muestra la diferencia
        que ya exista entre ambos montos, si la hay."""
        self.ensure_one()
        montos = self.move_id._l10n_py_mkt_montos_por_tasa()
        subtotal = montos['10'] + montos['5'] + montos['exento']
        return subtotal - self.move_id.amount_total

    def _fe_py_get_consulta_url_base(self):
        self.ensure_one()
        config = self.env['fe_py.configuracion']._get_config(self.move_id.company_id)
        return config.fe_py_get_url('consulta')

    def _fe_py_get_tipo_fiscal_display(self):
        """Nombre del Tipo Fiscal con tildes, solo para mostrar en el KuDE
        — el catálogo en sí (local_py.tipo_fiscal) usa nombres sin tilde
        por convención técnica, no se toca acá."""
        self.ensure_one()
        nombres = {
            'Factura Electronica': 'Factura electrónica',
            'Nota de Credito Electronica': 'Nota de crédito electrónica',
            'Nota de Debito Electronica': 'Nota de débito electrónica',
        }
        nombre = self.tipo_fiscal_id.name or ''
        return nombres.get(nombre, nombre)

    def _fe_py_formato_gs(self, valor):
        """Formato numérico paraguayo: punto como separador de miles, sin
        decimales (el Guaraní no usa centavos en la práctica)."""
        return '{:,.0f}'.format(valor or 0).replace(',', '.')

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
        # Receptor: con RUC va dRucRec; sin RUC (exterior, diplomático,
        # innominado) va dNumIDRec — cambia el nombre del parámetro, no
        # solo el valor. Confirmado contra los QR de los XML reales de
        # producción (exterior y organismo internacional usan dNumIDRec).
        el_ruc_rec = de.find('.//s:gDatRec/s:dRucRec', ns)
        if el_ruc_rec is not None and el_ruc_rec.text:
            clave_receptor, valor_receptor = 'dRucRec', el_ruc_rec.text
        else:
            el_num_id = de.find('.//s:gDatRec/s:dNumIDRec', ns)
            if el_num_id is None or not el_num_id.text:
                raise exceptions.UserError(
                    'El XML firmado no tiene ni dRucRec ni dNumIDRec en los '
                    'datos del receptor — no se puede armar el QR.'
                )
            clave_receptor, valor_receptor = 'dNumIDRec', el_num_id.text
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
        qpd[clave_receptor] = valor_receptor
        qpd['dTotGralOpe'] = d_tot_gral_ope
        qpd['dTotIVA'] = d_tot_iva
        qpd['cItems'] = str(c_items)
        qpd['DigestValue'] = digest_value.encode('utf-8').hex()
        qpd['IdCSC'] = idcsc

        qpar = '&'.join('%s=%s' % (k, v) for k, v in qpd.items())
        qparsec = qpar + csc
        c_hash_qr = hashlib.sha256(qparsec.encode('utf-8')).hexdigest()
        qpar_final = qpar + '&cHashQR=' + c_hash_qr

        config = self.env['fe_py.configuracion']._get_config(company)
        return config.fe_py_get_url('qr') + qpar_final

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
