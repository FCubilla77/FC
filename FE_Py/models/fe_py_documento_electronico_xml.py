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

from .res_partner import INDICADOR_PRESENCIA, TIPO_IMPUESTO
from .local_py_tipo_identificacion_fiscal import DESCRIPCION_ITIPIDREC

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
            # Se sincroniza siempre desde el comprobante antes de validar —
            # así, si el usuario corrigió el Motivo de Emisión después de
            # un Rechazo (antes de "Reescribir XML y Reenviar"), toma el
            # valor actual y no uno viejo copiado solo al Confirmar.
            if doc.move_id.fe_py_es_nc_nd:
                doc.motivo_emision = doc.move_id.fe_py_motivo_emision
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
        faltantes = move._fe_py_validar_datos_electronicos()
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

        i_timp = move.fe_py_itimp or '1'
        _sub(g, 'iTImp', i_timp)
        _sub(g, 'dDesTImp', dict(TIPO_IMPUESTO).get(i_timp, 'IVA'))

        moneda = move.currency_id.name or 'PYG'
        _sub(g, 'cMoneOpe', moneda)
        _sub(g, 'dDesMoneOpe', NOMBRE_MONEDA.get(moneda, moneda))
        # Moneda extranjera: tipo de cambio global para todo el DE (D017=1).
        # No se informa nada de esto cuando la operación es en Guaraníes.
        if moneda != 'PYG':
            _sub(g, 'dCondTiCam', '1')
            _sub(g, 'dTiCam', round(self._fe_py_tipo_cambio(move), 4))

    def _fe_py_tipo_cambio(self, move):
        """Cotización de la moneda de la operación expresada en Guaraníes.

        Se toma la que Odoo dejó guardada en la propia factura al
        confirmarla (invoice_currency_rate), no una cotización recalculada
        al momento de generar el XML — así el XML y la contabilidad
        siempre informan exactamente el mismo valor."""
        company_currency = move.company_id.currency_id
        if move.currency_id == company_currency:
            return 1.0
        rate = getattr(move, 'invoice_currency_rate', 0) or 0
        if rate:
            # invoice_currency_rate va de moneda de la compañía a moneda del
            # documento; SIFEN quiere el inverso (cuántos Gs vale 1 USD).
            return 1.0 / rate
        # Respaldo si el campo no existiera o quedara en cero.
        return move.currency_id._convert(
            1.0, company_currency, move.company_id,
            move.invoice_date or fields.Date.context_today(move),
        )

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
        # Distrito del emisor — estaba faltando (detectado comparando contra
        # XML reales de producción, que sí lo traen).
        distrito_emi = company.city_id.district_id if company.city_id else False
        _sub(g, 'cDisEmi', distrito_emi.code if distrito_emi else False)
        _sub(g, 'dDesDisEmi', distrito_emi.name if distrito_emi else False)
        _sub(g, 'cCiuEmi', company.city_id.code if company.city_id else False)
        _sub(g, 'dDesCiuEmi', company.city_id.name if company.city_id else False)
        _sub(g, 'dTelEmi', company.phone)
        _sub(g, 'dEmailE', company.email)
        g_act = etree.SubElement(g, '{%s}gActEco' % SIFEN_NS)
        _sub(g_act, 'cActEco', company.fe_py_actividad_economica_codigo)
        _sub(g_act, 'dDesActEco', company.fe_py_actividad_economica_desc)

    def _fe_py_xml_gDatRec(self, parent, partner):
        """Datos del receptor.

        Orden de campos y reglas de omisión confirmados contra 4 XML
        reales de producción aprobados por SIFEN (local, Estado,
        exterior y organismo internacional).

        Nota sobre una contradicción del Manual: la regla D208/D210 dice
        "No informar si D202=4" (B2F), pero los XML reales de exportación
        aprobados por SIFEN SÍ informan iTipIDRec/dNumIDRec. Se sigue la
        evidencia de producción, no la letra del manual.
        """
        move = self.move_id
        g = etree.SubElement(parent, '{%s}gDatRec' % SIFEN_NS)

        es_contribuyente = move._fe_py_receptor_es_contribuyente()
        tipo_operacion = move.fe_py_tipo_operacion or '1'
        es_b2f = tipo_operacion == '4'

        _sub(g, 'iNatRec', '1' if es_contribuyente else '2')
        _sub(g, 'iTiOpe', tipo_operacion)
        cod_pais = partner.country_id.code_alpha3 or 'PRY'
        _sub(g, 'cPaisRec', cod_pais)
        _sub(g, 'dDesPaisRe', partner.country_id.name or 'Paraguay')

        if es_contribuyente:
            # iTiContRec solo se informa para contribuyentes ("No informar
            # si D201 = 2").
            _sub(g, 'iTiContRec', '2' if partner.fe_py_tipo_persona == 'juridica' else '1')
            ruc_rec, dv_rec = self._fe_py_split_ruc_dv(partner.vat, partner.display_name)
            _sub(g, 'dRucRec', ruc_rec)
            _sub(g, 'dDVRec', dv_rec)
        else:
            tipo_ident = partner.l10n_py_tipo_identificacion_fiscal_id
            codigo = tipo_ident.fe_py_itipidrec if tipo_ident else False
            if not codigo:
                raise exceptions.UserError(
                    'El Tipo de Identificación Fiscal "%s" del Cliente "%s" no '
                    'tiene mapeado su código SIFEN equivalente. Completarlo en '
                    'Localización Paraguay > Tipos de Identificación Fiscal.'
                    % (tipo_ident.name if tipo_ident else '(vacío)', partner.display_name)
                )
            _sub(g, 'iTipIDRec', codigo)
            # Para el código 9 ("Otro") SIFEN espera la descripción real del
            # documento en vez del texto genérico de la tabla.
            if codigo == '9':
                _sub(g, 'dDTipIDRec', partner.fe_py_identificacion_texto or 'Otro')
            else:
                _sub(g, 'dDTipIDRec', DESCRIPCION_ITIPIDREC.get(codigo, ''))
            # Innominado: el manual pide completar con 0.
            _sub(g, 'dNumIDRec', partner.vat or ('0' if codigo == '5' else ''))

        _sub(g, 'dNomRec', partner.name)
        _sub(g, 'dDirRec', partner.street)
        _sub(g, 'dNumCasRec', getattr(partner, 'street_number', False) or '0')

        # Departamento / Distrito / Ciudad: "no se debe informar cuando
        # D202 = 4" (B2F). Confirmado también en los XML reales de
        # exportación, que no los traen.
        if not es_b2f:
            _sub(g, 'cDepRec', partner.state_id.code if partner.state_id else False)
            _sub(g, 'dDesDepRec', partner.state_id.name if partner.state_id else False)
            distrito = partner.city_id.district_id if partner.city_id else False
            _sub(g, 'cDisRec', distrito.code if distrito else False)
            _sub(g, 'dDesDisRec', distrito.name if distrito else False)
            _sub(g, 'cCiuRec', partner.city_id.code if partner.city_id else False)
            _sub(g, 'dDesCiuRec', partner.city_id.name if partner.city_id else False)

        _sub(g, 'dTelRec', partner.phone)
        _sub(g, 'dCelRec', partner.phone)
        _sub(g, 'dEmailRec', partner.email)

    def _fe_py_linea_tasa_iva(self, line):
        rates = line.tax_ids.mapped('amount')
        if any(abs(r - 10) < 0.001 for r in rates):
            return 10, '1', 'Gravado IVA'
        if any(abs(r - 5) < 0.001 for r in rates):
            return 5, '1', 'Gravado IVA'
        return 0, '3', 'Exento'

    def _fe_py_xml_gDtipDE(self, de, move):
        g = etree.SubElement(de, '{%s}gDtipDE' % SIFEN_NS)
        i_tide, _desc = TIDE_POR_TIPO_FISCAL.get(move.local_py_tipo_fiscal_id.name, ('1', ''))

        # gCamFE es EXCLUSIVO de la Factura Electrónica: "Obligatorio si
        # C002=1, No informar si C002≠1". Antes se generaba siempre, también
        # para NC/ND — corregido acá.
        if i_tide == '1':
            g_fe = etree.SubElement(g, '{%s}gCamFE' % SIFEN_NS)
            ind_pres = move.fe_py_indicador_presencia or '1'
            _sub(g_fe, 'iIndPres', ind_pres)
            _sub(g_fe, 'dDesIndPres', dict(INDICADOR_PRESENCIA).get(ind_pres, 'Operación presencial'))
            self._fe_py_xml_gCompPub(g_fe, move)

        self._fe_py_xml_gCamCond(g, move)

        lineas = move.invoice_line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note'))
        for line in lineas:
            self._fe_py_xml_gCamItem(g, line)

        if move.local_py_tipo_fiscal_id.name in NOMBRES_NC_ND:
            g_ncde = etree.SubElement(g, '{%s}gCamNCDE' % SIFEN_NS)
            _sub(g_ncde, 'iMotEmi', self.motivo_emision)
            _sub(g_ncde, 'dDesMotEmi', dict(self._fields['motivo_emision'].selection).get(self.motivo_emision))

    def _fe_py_xml_gCompPub(self, parent, move):
        """Compras Públicas (E020-E029) — dentro de gCamFE.

        Obligatorio para B2G salvo que se haya marcado "Venta Directa"
        (venta al Estado sin licitación de por medio). El Tipo de Operación
        sigue siendo B2G igual: SIFEN lo exige para todo receptor que sea
        un Organismo del Estado (Nota Técnica N° 20)."""
        if move.fe_py_tipo_operacion != '3' or move.fe_py_venta_directa:
            return
        g = etree.SubElement(parent, '{%s}gCompPub' % SIFEN_NS)
        _sub(g, 'dModCont', move.fe_py_dmodcont)
        _sub(g, 'dEntCont', move.fe_py_dentcont)
        _sub(g, 'dAnoCont', move.fe_py_danocont)
        _sub(g, 'dSecCont', move.fe_py_dseccont)
        _sub(g, 'dFeCodCont', move.fe_py_dfecodcont)

    def _fe_py_xml_gCamCond(self, parent, move):
        """Condición de la operación (E600-E699): contado o crédito.

        Contado -> gPaConEIni (forma de pago) es OBLIGATORIO.
        Crédito  -> gPagCred, con plazo o con detalle de cuotas.
        """
        condicion = move.invoice_payment_term_id.l10n_py_condicion if move.invoice_payment_term_id else False
        moneda = move.currency_id.name or 'PYG'
        g_cond = etree.SubElement(parent, '{%s}gCamCond' % SIFEN_NS)

        if condicion == 'credito':
            _sub(g_cond, 'iCondOpe', '2')
            _sub(g_cond, 'dDCondOpe', 'Crédito')
            g_pag = etree.SubElement(g_cond, '{%s}gPagCred' % SIFEN_NS)
            if move.fe_py_condicion_credito == '2':
                _sub(g_pag, 'iCondCred', '2')
                _sub(g_pag, 'dDCondCred', 'Cuota')
                _sub(g_pag, 'dCuotas', len(move.fe_py_cuota_ids))
                for cuota in move.fe_py_cuota_ids:
                    g_cuota = etree.SubElement(g_pag, '{%s}gCuotas' % SIFEN_NS)
                    _sub(g_cuota, 'cMoneCuo', moneda)
                    _sub(g_cuota, 'dDMoneCuo', NOMBRE_MONEDA.get(moneda, moneda))
                    _sub(g_cuota, 'dMonCuota', round(cuota.monto, 4))
                    _sub(g_cuota, 'dVencCuo', cuota.fecha_vencimiento)
            else:
                _sub(g_pag, 'iCondCred', '1')
                _sub(g_pag, 'dDCondCred', 'Plazo')
                plazo = 0
                if move.invoice_date_due and move.invoice_date:
                    plazo = (move.invoice_date_due - move.invoice_date).days
                # SIFEN espera texto con la unidad ("30 días"), no un número
                # pelado — confirmado en los XML reales de producción.
                _sub(g_pag, 'dPlazoCre', '%s días' % plazo)
        else:
            _sub(g_cond, 'iCondOpe', '1')
            _sub(g_cond, 'dDCondOpe', 'Contado')
            # gPaConEIni es obligatorio para toda venta al contado (E605).
            #
            # LIMITACIÓN CONOCIDA: el método de cobro real vive en el Pago,
            # que en el flujo actual se registra DESPUÉS de generar el XML.
            # Por eso, por ahora, toda venta contado se informa como
            # Efectivo. Resolverlo bien exige invertir la secuencia (exigir
            # el Pago registrado antes de permitir Generar XML) y agregar
            # los subgrupos de tarjeta (gPagTarCD) y cheque (gPagCheq).
            g_pago = etree.SubElement(g_cond, '{%s}gPaConEIni' % SIFEN_NS)
            _sub(g_pago, 'iTiPago', '1')
            _sub(g_pago, 'dDesTiPag', 'Efectivo')
            _sub(g_pago, 'dMonTiPag', round(move.amount_total, 4))
            _sub(g_pago, 'cMoneTiPag', moneda)
            _sub(g_pago, 'dDMoneTiPag', NOMBRE_MONEDA.get(moneda, moneda))
            if moneda != 'PYG':
                _sub(g_pago, 'dTiCamTiPag', round(self._fe_py_tipo_cambio(move), 4))

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
        # Base exenta por ítem (E737). Con dPropIVA=100 (gravado total) la
        # fórmula de la NT 013 da siempre 0; se informa igual porque el
        # campo debe existir. Solo sería distinto de 0 en "Gravado parcial"
        # (iAfecIVA=4), que este módulo todavía no genera.
        _sub(g_iva, 'dBasExe', 0)

    def _fe_py_xml_gTotSub(self, de, move):
        """Subtotales y totales (F001-F037).

        Las fórmulas siguen la Nota Técnica N° 001 (oct-2019), que CORRIGE
        al Manual base (sep-2019):
            Manual:  F014 = F008 - F011 - F012 - F013
            NT 001:  F014 = F008 - F013 + F025   <-- la que se aplica acá
        """
        montos = move._l10n_py_mkt_montos_por_tasa()
        base_10 = montos['10'] / 1.10 if montos['10'] else 0
        iva_10 = montos['10'] - base_10
        base_5 = montos['5'] / 1.05 if montos['5'] else 0
        iva_5 = montos['5'] - base_5

        lineas = move.invoice_line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note'))
        # F009: suma de (descuento por ítem x cantidad) — fórmula NT 001.
        total_desc = sum(
            (l.price_unit * (l.discount or 0) / 100) * l.quantity for l in lineas
        )
        # F008: total bruto = suma de los subtotales por tasa.
        total_ope = montos['exento'] + montos['5'] + montos['10']

        # F013 (redondeo): se toma la diferencia que Odoo YA produjo entre
        # la suma de subtotales y el total del comprobante, en vez de
        # aplicar por nuestra cuenta la regla SEDECO de múltiplos de 50 Gs.
        #
        # Motivo: si redondeáramos acá por separado, el XML informaría un
        # total distinto del que quedó contabilizado en Odoo. Si se quiere
        # el redondeo SEDECO automático, hay que configurarlo en Odoo
        # (redondeo de efectivo) para que contabilidad y XML coincidan.
        redondeo = total_ope - move.amount_total
        comision = 0.0

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
        _sub(g, 'dDescTotal', round(total_desc, 8))   # F011 = F009 + F033
        _sub(g, 'dAnticipo', 0)                        # F012 = F034 + F035
        _sub(g, 'dRedon', round(redondeo, 8))
        # dComi (F025) va SIEMPRE, aunque sea 0 — así lo hacen los 4 XML
        # reales de producción.
        _sub(g, 'dComi', round(comision, 8))
        total_general = total_ope - redondeo + comision
        # F014 = F008 - F013 + F025 (NT 001, que corrige al Manual base)
        _sub(g, 'dTotGralOpe', round(total_general, 8))
        _sub(g, 'dIVA5', round(iva_5, 8))
        _sub(g, 'dIVA10', round(iva_10, 8))
        # dLiqTotIVA5/dLiqTotIVA10 (F036/F037), dIVAComi (F026) y dTotComi
        # (F024) son opcionales y NO se emiten: los XML reales de
        # producción no los traen en ningún caso — ni siquiera cuando hay
        # redondeo distinto de cero. Solo tendrían sentido con comisiones,
        # que este módulo todavía no maneja.
        _sub(g, 'dTotIVA', round(iva_5 + iva_10, 8))
        _sub(g, 'dBaseGrav5', round(base_5, 8))
        _sub(g, 'dBaseGrav10', round(base_10, 8))
        _sub(g, 'dTBasGraIVA', round(base_5 + base_10, 8))
        # F023: solo existe si la operación NO es en Guaraníes.
        if (move.currency_id.name or 'PYG') != 'PYG':
            _sub(g, 'dTotalGs', round(total_general * self._fe_py_tipo_cambio(move), 8))

    def _fe_py_xml_gCamDEAsoc(self, de, move):
        doc_asociado = self.env['fe_py.documento_electronico'].search([
            ('move_id', '=', move.reversed_entry_id.id)
        ], limit=1)
        g = etree.SubElement(de, '{%s}gCamDEAsoc' % SIFEN_NS)
        _sub(g, 'iTipDocAso', '1')
        _sub(g, 'dDesTipDocAso', 'Electrónico')
        _sub(g, 'dCdCDERef', doc_asociado.cdc)
