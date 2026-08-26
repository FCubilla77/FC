# -*- coding: utf-8 -*-
"""Generación de CDC y armado del XML del Documento Electrónico (DE), sin
firmar todavía (la firma es la Fase 4).

ALCANCE DE ESTA FASE:

  Cubre:
    - Factura Electrónica y Nota de Débito Electrónica (move_type=out_invoice)
    - Nota de Crédito Electrónica (move_type=out_refund), incluyendo el
      grupo "Documento Asociado" (gCamDEAsoc) referenciando el CDC de la
      Factura Electrónica original (que debe tener ya su propio Documento
      Electrónico con CDC asignado).
    - Receptor CON RUC (contribuyente) - persona fisica o juridica.
    - Condicion de venta Contado/Credito, IVA 10%/5%/Exento por linea,
      descuento por linea (%).

  NO cubre todavia (fuera de alcance de esta fase):
    - Receptor SIN RUC (Cedula/Pasaporte/Innominado).
    - Autofactura Electronica y Nota de Remision Electronica.
    - Grupos especiales (gCamEsp) y de transporte (gTransp).
    - Descuento global sobre el total, anticipos, moneda extranjera con
      tipo de cambio.
"""
import random
from datetime import datetime

from lxml import etree

from odoo import exceptions, fields, models

SIFEN_NS = 'http://ekuatia.set.gov.py/sifen/xsd'
XSI_NS = 'http://www.w3.org/2001/XMLSchema-instance'
NSMAP = {None: SIFEN_NS, 'xsi': XSI_NS}

TIDE_POR_TIPO_FISCAL = {
    'Factura Electronica': ('1', 'Factura electrónica'),
    'Nota de Credito Electronica': ('5', 'Nota de crédito electrónica'),
    'Nota de Debito Electronica': ('6', 'Nota de débito electrónica'),
}

# El Manual Técnico exige el grupo gCamNCDE (Motivo de Emisión) tanto para
# Nota de Crédito como para Nota de Débito Electrónica (C002 = 5 o 6) — no
# solo para Nota de Crédito. El "Comprobante Asociado" (gCamDEAsoc) sí
# queda limitado a Nota de Crédito por ahora, porque es la única que tiene
# un campo nativo en Odoo (reversed_entry_id) para referenciar la factura
# original — Nota de Débito no tiene un mecanismo equivalente todavía.
NOMBRES_NC_ND = ('Nota de Credito Electronica', 'Nota de Debito Electronica')

NOMBRE_MONEDA = {'PYG': 'Guarani', 'USD': 'Dolar americano', 'EUR': 'Euro'}


def _sub(parent, tag, value):
    """Crea un sub-elemento con texto, solo si value no es None/''."""
    if value is None or value == '':
        return None
    el = etree.SubElement(parent, '{%s}%s' % (SIFEN_NS, tag))
    el.text = str(value)
    return el


class FePyDocumentoElectronico(models.Model):
    _inherit = 'fe_py.documento_electronico'

    def _fe_py_split_ruc_dv(self, vat, etiqueta):
        vat = (vat or '').strip()
        partes = vat.split('-')
        if len(partes) != 2 or not partes[0].isdigit() or not partes[1].isdigit():
            raise exceptions.UserError(
                'El RUC de %s ("%s") no tiene el formato esperado '
                '"NNNNNNNN-D".' % (etiqueta, vat or '(vacío)')
            )
        return partes[0], partes[1]

    def _fe_py_digito_verificador_modulo11(self, texto):
        total = 0
        base_max = 11
        k = 2
        for ch in reversed(str(texto)):
            if k > base_max:
                k = 2
            total += int(ch) * k
            k += 1
        resto = total % base_max
        return str(base_max - resto) if resto > 1 else '0'

    def _fe_py_generar_codigo_seguridad(self):
        return '%09d' % random.randint(0, 999999999)

    def _fe_py_obtener_ite_ide(self, move):
        tipo_fiscal = move.local_py_tipo_fiscal_id
        datos = TIDE_POR_TIPO_FISCAL.get(tipo_fiscal.name)
        if not datos:
            raise exceptions.UserError(
                'El Tipo Fiscal "%s" no está soportado todavía por el '
                'generador de XML de FE_Py (fase actual: Factura, Nota de '
                'Crédito y Nota de Débito Electrónica).' % (tipo_fiscal.name or '(vacío)')
            )
        return datos

    def _fe_py_generar_cdc(self):
        self.ensure_one()
        move = self.move_id
        company = move.company_id

        i_tide, _desc = self._fe_py_obtener_ite_ide(move)
        ruc_em, dv_em = self._fe_py_split_ruc_dv(company.vat, 'la Compañía')

        nro_doc = move.l10n_py_nro_documento or ''
        partes = nro_doc.split('-')
        if len(partes) != 3:
            raise exceptions.UserError(
                'El Nro. Documento del comprobante ("%s") no tiene el '
                'formato esperado "999-999-9999999", necesario para armar '
                'el CDC.' % nro_doc
            )
        d_est, d_pun_exp, d_num_doc = partes

        if not move.invoice_date:
            raise exceptions.UserError('Falta la Fecha del comprobante para armar el CDC.')
        fecha_emi = move.invoice_date.strftime('%Y%m%d')

        tipo_emi_codigo = '1' if self.tipo_emision != 'contingencia' else '2'
        # Siempre se genera un código de seguridad NUEVO acá — no se
        # reutiliza el de un intento anterior. "Generar/Regenerar XML" es
        # justamente el botón para reintentar tras un Rechazo/Error, y cada
        # intento debe tener un CDC genuinamente distinto (evita cualquier
        # riesgo de que SIFEN interprete un reenvío como CDC duplicado).
        cod_seg = self._fe_py_generar_codigo_seguridad()

        cdc_sin_dv = ''.join([
            i_tide.zfill(2),
            ruc_em.zfill(8),
            dv_em,
            d_est.zfill(3),
            d_pun_exp.zfill(3),
            d_num_doc.zfill(7),
            company.fe_py_tipo_contribuyente or '2',
            fecha_emi,
            tipo_emi_codigo,
            cod_seg,
        ])
        if len(cdc_sin_dv) != 43:
            raise exceptions.UserError(
                'Error interno armando el CDC: longitud %s en vez de 43 '
                '(antes del dígito verificador).' % len(cdc_sin_dv)
            )
        dv_final = self._fe_py_digito_verificador_modulo11(cdc_sin_dv)
        cdc = cdc_sin_dv + dv_final
        return cdc, cod_seg, dv_final

    def action_generar_xml(self):
        estados_permitidos = ('borrador', 'xml_generado', 'error_comunicacion', 'rechazado')
        for doc in self:
            if doc.estado not in estados_permitidos:
                raise exceptions.UserError(
                    'No se puede generar el XML: el Documento Electrónico de %s '
                    'está en estado "%s". Solo se puede generar/regenerar en '
                    'Borrador, o luego de un Error de Comunicación o Rechazo.'
                    % (doc.move_id.display_name, dict(doc._fields['estado'].selection).get(doc.estado))
                )
            doc._fe_py_validar_datos_para_generar()
            cdc, cod_seg, dv_final = doc._fe_py_generar_cdc()
            xml_root = doc._fe_py_construir_xml(cdc, cod_seg)
            xml_str = etree.tostring(
                xml_root, pretty_print=True, xml_declaration=True, encoding='UTF-8'
            ).decode('utf-8')

            doc.write({
                'cdc': cdc,
                'codigo_seguridad': cod_seg,
                'digito_verificador_cdc': dv_final,
                'xml_generado': xml_str,
                'xml_firmado': False,
                'estado': 'xml_generado',
                'fecha_generacion': fields.Datetime.now(),
            })
            doc.env['fe_py.documento_electronico.log'].sudo().create({
                'documento_id': doc.id,
                'tipo_operacion': 'generacion_xml',
                'resultado': 'exito',
                'mensaje_resultado': 'XML generado. CDC: %s' % cdc,
                'response_payload': xml_str,
            })
        return True

    def _fe_py_validar_datos_para_generar(self):
        self.ensure_one()
        move = self.move_id
        company = move.company_id
        partner = move.partner_id

        faltantes = []
        if not company.vat:
            faltantes.append('RUC de la Compañía')
        if not company.fe_py_actividad_economica_codigo:
            faltantes.append('Código de Actividad Económica (Compañía)')
        if not company.street:
            faltantes.append('Dirección de la Compañía')
        if not company.state_id:
            faltantes.append('Departamento de la Compañía')
        if not company.city_id:
            faltantes.append('Ciudad de la Compañía')
        if not move.journal_id.l10n_py_inicio_vigencia_timbrado:
            faltantes.append('Inicio de Vigencia del Timbrado (Diario)')
        if not partner.vat:
            faltantes.append(
                'RUC del Cliente (receptor sin RUC todavía no está soportado en esta fase)'
            )
        if not partner.country_id:
            faltantes.append('País del Cliente')
        if not partner.street:
            faltantes.append('Dirección del Cliente')
        if not partner.state_id:
            faltantes.append('Departamento del Cliente')
        if not partner.city_id:
            faltantes.append('Ciudad del Cliente')
        if move.local_py_tipo_fiscal_id.name in NOMBRES_NC_ND and not self.motivo_emision:
            faltantes.append('Motivo de Emisión (obligatorio en Nota de Crédito/Débito)')
        if move.move_type == 'out_refund' and not move.reversed_entry_id:
            faltantes.append('Comprobante Asociado (obligatorio en Nota de Crédito)')
        if move.move_type == 'out_refund' and move.reversed_entry_id:
            doc_asociado = self.env['fe_py.documento_electronico'].search([
                ('move_id', '=', move.reversed_entry_id.id)
            ], limit=1)
            if not doc_asociado or not doc_asociado.cdc:
                faltantes.append(
                    'CDC de la Factura Electrónica asociada (todavía no fue generado)'
                )

        if faltantes:
            raise exceptions.UserError(
                'Faltan datos para generar el XML de %s:\n- %s'
                % (move.display_name, '\n- '.join(faltantes))
            )

    def _fe_py_construir_xml(self, cdc, cod_seg):
        self.ensure_one()
        move = self.move_id
        company = move.company_id
        partner = move.partner_id
        journal = move.journal_id
        i_tide, d_des_tide = self._fe_py_obtener_ite_ide(move)

        rde = etree.Element('{%s}rDE' % SIFEN_NS, nsmap=NSMAP)
        rde.set('{%s}schemaLocation' % XSI_NS, 'https://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd')
        _sub(rde, 'dVerFor', self.version_formato or '150')

        de = etree.SubElement(rde, '{%s}DE' % SIFEN_NS)
        de.set('Id', cdc)

        ahora = fields.Datetime.now()
        _sub(de, 'dDVId', cdc[-1])
        _sub(de, 'dFecFirma', ahora.strftime('%Y-%m-%dT%H:%M:%S'))
        _sub(de, 'dSisFact', '1')

        self._fe_py_xml_gOpeDE(de, cod_seg)
        self._fe_py_xml_gTimb(de, journal, i_tide, d_des_tide)
        self._fe_py_xml_gDatGralOpe(de, move, company, partner)
        self._fe_py_xml_gDtipDE(de, move)
        self._fe_py_xml_gTotSub(de, move)
        if move.move_type == 'out_refund':
            self._fe_py_xml_gCamDEAsoc(de, move)

        return rde

    def _fe_py_xml_gOpeDE(self, de, cod_seg):
        g = etree.SubElement(de, '{%s}gOpeDE' % SIFEN_NS)
        tipo_emi_codigo = '1' if self.tipo_emision != 'contingencia' else '2'
        _sub(g, 'iTipEmi', tipo_emi_codigo)
        _sub(g, 'dDesTipEmi', 'Normal' if tipo_emi_codigo == '1' else 'Contingencia')
        _sub(g, 'dCodSeg', cod_seg)

    def _fe_py_xml_gTimb(self, de, journal, i_tide, d_des_tide):
        move = self.move_id
        g = etree.SubElement(de, '{%s}gTimb' % SIFEN_NS)
        _sub(g, 'iTiDE', i_tide)
        _sub(g, 'dDesTiDE', d_des_tide)
        _sub(g, 'dNumTim', '%08d' % (move.l10n_py_timbrado or 0))
        d_est, d_pun_exp, d_num_doc = move.l10n_py_nro_documento.split('-')
        _sub(g, 'dEst', d_est.zfill(3))
        _sub(g, 'dPunExp', d_pun_exp.zfill(3))
        _sub(g, 'dNumDoc', d_num_doc.zfill(7))
        _sub(g, 'dFeIniT', journal.l10n_py_inicio_vigencia_timbrado.strftime('%Y-%m-%d'))

    def _fe_py_xml_gDatGralOpe(self, de, move, company, partner):
        g = etree.SubElement(de, '{%s}gDatGralOpe' % SIFEN_NS)
        fecha_hora_emi = datetime.combine(move.invoice_date, datetime.now().time())
        _sub(g, 'dFeEmiDE', fecha_hora_emi.strftime('%Y-%m-%dT%H:%M:%S'))

        self._fe_py_xml_gOpeCom(g, move)
        self._fe_py_xml_gEmis(g, company)
        self._fe_py_xml_gDatRec(g, partner)

    def _fe_py_xml_gOpeCom(self, parent, move):
        g = etree.SubElement(parent, '{%s}gOpeCom' % SIFEN_NS)
        lineas = move.invoice_line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note'))
        tipos_producto = set(lineas.mapped('product_id.type'))
        if tipos_producto and tipos_producto <= {'service'}:
            i_tip_tra, d_desc = '2', 'Prestación de servicios'
        elif tipos_producto and 'service' not in tipos_producto:
            i_tip_tra, d_desc = '1', 'Venta de mercadería'
        else:
            i_tip_tra, d_desc = '3', 'Mixto (Venta de mercadería y servicios)'
        _sub(g, 'iTipTra', i_tip_tra)
        _sub(g, 'dDesTipTra', d_desc)
        _sub(g, 'iTImp', '1')
        _sub(g, 'dDesTImp', 'IVA')
        moneda = move.currency_id.name or 'PYG'
        _sub(g, 'cMoneOpe', moneda)
        _sub(g, 'dDesMoneOpe', NOMBRE_MONEDA.get(moneda, moneda))

    def _fe_py_xml_gEmis(self, parent, company):
        g = etree.SubElement(parent, '{%s}gEmis' % SIFEN_NS)
        ruc_em, dv_em = self._fe_py_split_ruc_dv(company.vat, 'la Compañía')
        _sub(g, 'dRucEm', ruc_em)
        _sub(g, 'dDVEmi', dv_em)
        _sub(g, 'iTipCont', company.fe_py_tipo_contribuyente or '2')
        _sub(g, 'cTipReg', company.fe_py_tipo_regimen or '8')
        _sub(g, 'dNomEmi', company.name)
        _sub(g, 'dDirEmi', company.street)
        _sub(g, 'dNumCas', getattr(company, 'street_number', False) or '0')
        _sub(g, 'cDepEmi', company.state_id.code if company.state_id else False)
        _sub(g, 'dDesDepEmi', company.state_id.name if company.state_id else False)
        _sub(g, 'cCiuEmi', company.city_id.code if company.city_id else False)
        _sub(g, 'dDesCiuEmi', company.city_id.name if company.city_id else False)
        _sub(g, 'dTelEmi', company.phone)
        _sub(g, 'dEmailE', company.email)
        g_act = etree.SubElement(g, '{%s}gActEco' % SIFEN_NS)
        _sub(g_act, 'cActEco', company.fe_py_actividad_economica_codigo)
        _sub(g_act, 'dDesActEco', company.fe_py_actividad_economica_desc)

    def _fe_py_xml_gDatRec(self, parent, partner):
        g = etree.SubElement(parent, '{%s}gDatRec' % SIFEN_NS)
        _sub(g, 'iNatRec', '1')
        _sub(g, 'iTiOpe', self.tipo_operacion or '1')
        cod_pais = partner.country_id.code_alpha3 or 'PRY'
        _sub(g, 'cPaisRec', cod_pais)
        _sub(g, 'dDesPaisRe', partner.country_id.name or 'Paraguay')
        _sub(g, 'iTiContRec', '2' if partner.is_company else '1')
        ruc_rec, dv_rec = self._fe_py_split_ruc_dv(partner.vat, partner.display_name)
        _sub(g, 'dRucRec', ruc_rec)
        _sub(g, 'dDVRec', dv_rec)
        _sub(g, 'dNomRec', partner.name)
        _sub(g, 'dDirRec', partner.street)
        _sub(g, 'dNumCasRec', getattr(partner, 'street_number', False) or '0')
        _sub(g, 'cDepRec', partner.state_id.code if partner.state_id else False)
        _sub(g, 'dDesDepRec', partner.state_id.name if partner.state_id else False)
        distrito = partner.city_id.district_id if partner.city_id else False
        _sub(g, 'cDisRec', distrito.code if distrito else False)
        _sub(g, 'dDesDisRec', distrito.name if distrito else False)
        _sub(g, 'cCiuRec', partner.city_id.code if partner.city_id else False)
        _sub(g, 'dDesCiuRec', partner.city_id.name if partner.city_id else False)
        _sub(g, 'dTelRec', partner.phone or partner.mobile)

    def _fe_py_linea_tasa_iva(self, line):
        rates = line.tax_ids.mapped('amount')
        if any(abs(r - 10) < 0.001 for r in rates):
            return 10, '1', 'Gravado IVA'
        if any(abs(r - 5) < 0.001 for r in rates):
            return 5, '1', 'Gravado IVA'
        return 0, '3', 'Exento'

    def _fe_py_xml_gDtipDE(self, de, move):
        g = etree.SubElement(de, '{%s}gDtipDE' % SIFEN_NS)

        g_fe = etree.SubElement(g, '{%s}gCamFE' % SIFEN_NS)
        _sub(g_fe, 'iIndPres', '1')
        _sub(g_fe, 'dDesIndPres', 'Operación presencial')

        condicion = move.invoice_payment_term_id.l10n_py_condicion if move.invoice_payment_term_id else False
        g_cond = etree.SubElement(g, '{%s}gCamCond' % SIFEN_NS)
        if condicion == 'credito':
            _sub(g_cond, 'iCondOpe', '2')
            _sub(g_cond, 'dDCondOpe', 'Crédito')
            g_pag = etree.SubElement(g_cond, '{%s}gPagCred' % SIFEN_NS)
            _sub(g_pag, 'iCondCred', '1')
            _sub(g_pag, 'dDCondCred', 'Plazo')
            plazo = 0
            if move.invoice_date_due and move.invoice_date:
                plazo = (move.invoice_date_due - move.invoice_date).days
            _sub(g_pag, 'dPlazoCre', plazo)
        else:
            _sub(g_cond, 'iCondOpe', '1')
            _sub(g_cond, 'dDCondOpe', 'Contado')

        lineas = move.invoice_line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note'))
        for line in lineas:
            self._fe_py_xml_gCamItem(g, line)

        if move.local_py_tipo_fiscal_id.name in NOMBRES_NC_ND:
            g_ncde = etree.SubElement(g, '{%s}gCamNCDE' % SIFEN_NS)
            _sub(g_ncde, 'iMotEmi', self.motivo_emision)
            _sub(g_ncde, 'dDesMotEmi', dict(self._fields['motivo_emision'].selection).get(self.motivo_emision))

    def _fe_py_xml_gCamItem(self, parent, line):
        g = etree.SubElement(parent, '{%s}gCamItem' % SIFEN_NS)
        _sub(g, 'dCodInt', line.product_id.default_code or str(line.product_id.id))
        _sub(g, 'dDesProSer', line.name or line.product_id.display_name)
        _sub(g, 'cUniMed', '77')
        _sub(g, 'dDesUniMed', 'UNI')
        _sub(g, 'dCantProSer', line.quantity)

        g_val = etree.SubElement(g, '{%s}gValorItem' % SIFEN_NS)
        total_bruto = line.price_unit * line.quantity
        _sub(g_val, 'dPUniProSer', round(line.price_unit, 8))
        _sub(g_val, 'dTotBruOpeItem', round(total_bruto, 8))

        g_resta = etree.SubElement(g_val, '{%s}gValorRestaItem' % SIFEN_NS)
        descuento_monto = total_bruto * (line.discount or 0) / 100
        total_neto_item = total_bruto - descuento_monto
        _sub(g_resta, 'dDescItem', round(descuento_monto, 8))
        _sub(g_resta, 'dPorcDesIt', line.discount or 0)
        _sub(g_resta, 'dDescGloItem', 0)
        _sub(g_resta, 'dTotOpeItem', round(total_neto_item, 8))

        tasa, i_afec, d_desc = self._fe_py_linea_tasa_iva(line)
        g_iva = etree.SubElement(g, '{%s}gCamIVA' % SIFEN_NS)
        _sub(g_iva, 'iAfecIVA', i_afec)
        _sub(g_iva, 'dDesAfecIVA', d_desc)
        _sub(g_iva, 'dPropIVA', 100)
        _sub(g_iva, 'dTasaIVA', tasa)
        if tasa:
            base = total_neto_item / (1 + tasa / 100.0)
            iva = total_neto_item - base
        else:
            base, iva = 0, 0
        _sub(g_iva, 'dBasGravIVA', round(base, 8))
        _sub(g_iva, 'dLiqIVAItem', round(iva, 8))

    def _fe_py_xml_gTotSub(self, de, move):
        montos = move._l10n_py_mkt_montos_por_tasa()
        base_10 = montos['10'] / 1.10 if montos['10'] else 0
        iva_10 = montos['10'] - base_10
        base_5 = montos['5'] / 1.05 if montos['5'] else 0
        iva_5 = montos['5'] - base_5

        lineas = move.invoice_line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note'))
        total_desc = sum(
            (l.price_unit * l.quantity) * (l.discount or 0) / 100 for l in lineas
        )
        total_ope = sum(l.price_unit * l.quantity for l in lineas)

        g = etree.SubElement(de, '{%s}gTotSub' % SIFEN_NS)
        _sub(g, 'dSubExe', round(montos['exento'], 8))
        _sub(g, 'dSubExo', 0)
        _sub(g, 'dSub5', round(montos['5'], 8))
        _sub(g, 'dSub10', round(montos['10'], 8))
        _sub(g, 'dTotOpe', round(total_ope, 8))
        _sub(g, 'dTotDesc', round(total_desc, 8))
        _sub(g, 'dTotDescGlotem', 0)
        _sub(g, 'dTotAntItem', 0)
        _sub(g, 'dTotAnt', 0)
        _sub(g, 'dPorcDescTotal', 0)
        _sub(g, 'dDescTotal', 0.0)
        _sub(g, 'dAnticipo', 0)
        _sub(g, 'dRedon', 0.0)
        _sub(g, 'dTotGralOpe', round(move.amount_total, 8))
        _sub(g, 'dIVA5', round(iva_5, 8))
        _sub(g, 'dIVA10', round(iva_10, 8))
        _sub(g, 'dTotIVA', round(iva_5 + iva_10, 8))
        _sub(g, 'dBaseGrav5', round(base_5, 8))
        _sub(g, 'dBaseGrav10', round(base_10, 8))
        _sub(g, 'dTBasGraIVA', round(base_5 + base_10, 8))

    def _fe_py_xml_gCamDEAsoc(self, de, move):
        doc_asociado = self.env['fe_py.documento_electronico'].search([
            ('move_id', '=', move.reversed_entry_id.id)
        ], limit=1)
        g = etree.SubElement(de, '{%s}gCamDEAsoc' % SIFEN_NS)
        _sub(g, 'iTipDocAso', '1')
        _sub(g, 'dDesTipDocAso', 'Electrónico')
        _sub(g, 'dCdCDERef', doc_asociado.cdc)
