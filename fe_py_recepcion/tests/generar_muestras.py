# -*- coding: utf-8 -*-
"""Genera los XML de prueba de tests/xml con datos 100% FICTICIOS.

Las dos primeras muestras reproducen la ESTRUCTURA y los importes de dos
facturas electrónicas reales de proveedores (una con el DE suelto y descuento
por ítem, otra envuelta en el sobre SOAP de SIFEN, con nodos vacíos y
números como 0E-9), pero ningún dato personal o comercial real: RUC, nombres,
direcciones, teléfonos, correos, timbrados, CDC, firma y certificado son
inventados. Las demás cubren casos que las muestras reales no traen (moneda
extranjera, crédito, cuotas, notas de crédito y débito) y se armaron según el
Manual Técnico v150.

Uso:  python3 generar_muestras.py
"""

import os
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

AQUI = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(AQUI, 'xml')
D = Decimal


def dv_modulo11(numero):
    """Dígito verificador módulo 11 (mismo algoritmo que local_py)."""
    total, k = 0, 2
    for caracter in str(numero)[::-1]:
        if k > 11:
            k = 2
        total += int(caracter) * k
        k += 1
    resto = total % 11
    return 11 - resto if resto > 1 else 0


def armar_cdc(itide, ruc, est, punto, numero, fecha, cod_seguridad='123456789'):
    cuerpo = '%02d%s%s%s%s%s1%s1%s' % (
        itide, ruc.zfill(8), dv_modulo11(ruc), est, punto, numero,
        fecha.strftime('%Y%m%d'), cod_seguridad)
    return cuerpo + str(dv_modulo11(cuerpo))


def n(valor, largo=False, decimales=None):
    """Formatea un número como lo hacen los sistemas emisores."""
    valor = D(valor)
    if largo:
        return '{:.9f}'.format(valor)
    if decimales is not None:
        return '{:.{d}f}'.format(valor, d=decimales)
    if valor == valor.to_integral_value():
        return '{:.1f}'.format(valor)
    return str(valor.normalize())


def redondear(valor, decimales):
    paso = D(1).scaleb(-decimales)
    return D(valor).quantize(paso, rounding=ROUND_HALF_UP)


def item(codigo, desc, cant, precio, tasa, desc_unit=D(0), pct=None, unidad=(77, 'UNI'),
         afect=None, lote=None):
    return dict(codigo=codigo, desc=desc, cant=D(cant), precio=D(precio), tasa=tasa,
                desc_unit=D(desc_unit), pct=pct, unidad=unidad, afect=afect, lote=lote)


def calcular_item(it, decimales):
    total = redondear((it['precio'] - it['desc_unit']) * it['cant'], decimales)
    tasa = it['tasa']
    if tasa == 10:
        base = redondear(total / D('1.1'), decimales)
    elif tasa == 5:
        base = redondear(total / D('1.05'), decimales)
    else:
        base = D(0)
    liq = total - base if tasa in (5, 10) else D(0)
    return total, base, liq


def xml_item(it, decimales, largo, con_porcentaje=True):
    total, base, liq = calcular_item(it, decimales)
    tasa = it['tasa']
    afect = it['afect'] or ('1' if tasa in (5, 10) else '3')
    desc_afect = {'1': 'Gravado IVA', '2': 'Exonerado (Art. 83- Ley 125/91)',
                  '3': 'Exento', '4': 'Gravado parcial (Grav-Exento)'}[afect]
    bruto = it['precio'] * it['cant']
    pct = it['pct']
    if pct is None and it['desc_unit'] > 0:
        pct = (it['desc_unit'] / it['precio'] * 100).quantize(D('0.01'), rounding=ROUND_HALF_UP)
    resta = ''
    if it['desc_unit'] > 0:
        resta += '<dDescItem>%s</dDescItem>' % n(it['desc_unit'], largo)
        if con_porcentaje:
            resta += '<dPorcDesIt>%s</dPorcDesIt>' % n(pct, largo)
    resta += ('<dDescGloItem>0.0</dDescGloItem><dAntPreUniIt>0</dAntPreUniIt>'
              '<dAntGloPreUniIt>0</dAntGloPreUniIt><dTotOpeItem>%s</dTotOpeItem>' % n(total, largo))
    lote = '<gRasMerc><dNumLote>%s</dNumLote></gRasMerc>' % it['lote'] if it['lote'] else ''
    return (
        '<gCamItem><dCodInt>{cod}</dCodInt><dDesProSer>{desc}</dDesProSer>'
        '<cUniMed>{um}</cUniMed><dDesUniMed>{umd}</dDesUniMed><dCantProSer>{cant}</dCantProSer>'
        '<gValorItem><dPUniProSer>{precio}</dPUniProSer><dTotBruOpeItem>{bruto}</dTotBruOpeItem>'
        '<gValorRestaItem>{resta}</gValorRestaItem></gValorItem>'
        '<gCamIVA><iAfecIVA>{afect}</iAfecIVA><dDesAfecIVA>{dafect}</dDesAfecIVA>'
        '<dPropIVA>{prop}</dPropIVA><dTasaIVA>{tasa}</dTasaIVA><dBasGravIVA>{base}</dBasGravIVA>'
        '<dLiqIVAItem>{liq}</dLiqIVAItem></gCamIVA>{lote}</gCamItem>'
    ).format(
        cod=it['codigo'], desc=it['desc'], um=it['unidad'][0], umd=it['unidad'][1],
        cant=n(it['cant'], largo), precio=n(it['precio'], largo), bruto=n(bruto, largo),
        resta=resta, afect=afect, dafect=desc_afect, prop='100' if afect in ('1', '3') else '0',
        tasa=tasa, base=n(base, largo), liq=n(liq, largo), lote=lote)


def construir(*, itide=1, est='001', punto='001', numero='0000001', timbrado='12345678',
              emision=date(2026, 11, 3), hora='10:00:00', ruc_emisor='80000010',
              ruc_receptor='80000020', nombre_emisor='EMPRESA DE PRUEBA A S.A.',
              nombre_receptor='COMPRADOR DE PRUEBA S.A.', items=(), moneda=('PYG', 'Guarani'),
              tipo_cambio=None, condicion=1, plazo=None, cuotas=None, motivo=None,
              asociado=None, soap=False, largo=False, nodos_vacios=False, decimales=0,
              total_gs=None):
    cdc = armar_cdc(itide, ruc_emisor, est, punto, numero, emision)
    descripcion_tipo = {1: 'Factura electrónica', 5: 'Nota de crédito electrónica',
                        6: 'Nota de débito electrónica', 7: 'Nota de remisión electrónica'}[itide]
    calculos = [calcular_item(i, decimales) for i in items]
    sub = {10: D(0), 5: D(0), 0: D(0)}
    iva = {10: D(0), 5: D(0)}
    descuento = D(0)
    for it, (total, _base, liq) in zip(items, calculos):
        sub[it['tasa'] if it['tasa'] in (5, 10) else 0] += total
        if it['tasa'] in (5, 10):
            iva[it['tasa']] += liq
        descuento += it['desc_unit'] * it['cant']
    total_general = sum(sub.values())
    base5 = sub[5] - iva[5]
    base10 = sub[10] - iva[10]
    total_iva = iva[5] + iva[10]
    redon = '0E-9' if largo else '0.0'
    vacio = '<dCompDir1/>' if nodos_vacios else ''

    # --- condición ---------------------------------------------------------
    if condicion == 1:
        if nodos_vacios:
            pago = ('<gPaConEIni><iTiPago>99</iTiPago><dDesTiPag/><dMonTiPag>%s</dMonTiPag>'
                    '<cMoneTiPag>%s</cMoneTiPag><dDMoneTiPag>%s</dDMoneTiPag></gPaConEIni>'
                    % (n(total_general, largo), moneda[0], moneda[1]))
        else:
            pago = ('<gPaConEIni><iTiPago>1</iTiPago><dDesTiPag>Efectivo</dDesTiPag>'
                    '<dMonTiPag>%s</dMonTiPag><cMoneTiPag>%s</cMoneTiPag>'
                    '<dDMoneTiPag>%s</dDMoneTiPag></gPaConEIni>'
                    % (n(total_general, largo), moneda[0], moneda[1]))
        cond = '<gCamCond><iCondOpe>1</iCondOpe><dDCondOpe>Contado</dDCondOpe>%s</gCamCond>' % pago
    else:
        if cuotas:
            detalle = ''.join(
                '<gCuotas><cMoneCuo>%s</cMoneCuo><dDMoneCuo>%s</dDMoneCuo><dMonCuota>%s</dMonCuota>'
                '<dVencCuo>%s</dVencCuo></gCuotas>' % (moneda[0], moneda[1], n(m, decimales=2), v.isoformat())
                for m, v in cuotas)
            cred = ('<gPagCred><iCondCred>2</iCondCred><dDCondCred>Cuota</dDCondCred>'
                    '<dCuotas>%s</dCuotas><dMonEnt>0</dMonEnt>%s</gPagCred>' % (len(cuotas), detalle))
        else:
            cred = ('<gPagCred><iCondCred>1</iCondCred><dDCondCred>Plazo</dDCondCred>'
                    '<dPlazoCre>%s</dPlazoCre></gPagCred>' % plazo)
        cond = '<gCamCond><iCondOpe>2</iCondOpe><dDCondOpe>Crédito</dDCondOpe>%s</gCamCond>' % cred

    # --- operación comercial ------------------------------------------------
    extranjera = ''
    if moneda[0] != 'PYG':
        extranjera = '<dCondTiCam>1</dCondTiCam><dTiCam>%s</dTiCam>' % n(tipo_cambio, decimales=4)
    ope = ('<gOpeCom><iTipTra>2</iTipTra><dDesTipTra>Prestación de servicios</dDesTipTra>'
           '<iTImp>1</iTImp><dDesTImp>IVA</dDesTImp><cMoneOpe>{m}</cMoneOpe>'
           '<dDesMoneOpe>{md}</dDesMoneOpe>{ext}</gOpeCom>').format(m=moneda[0], md=moneda[1], ext=extranjera)

    # --- NC / ND y documento asociado ---------------------------------------
    ncde = ''
    if motivo:
        ncde = ('<gCamNCDE><iMotEmi>%s</iMotEmi><dDesMotEmi>%s</dDesMotEmi></gCamNCDE>'
                % (motivo[0], motivo[1]))
    asoc = ''
    if asociado:
        if asociado['tipo'] == 1:
            asoc = ('<gCamDEAsoc><iTipDocAso>1</iTipDocAso><dDesTipDocAso>Electrónico</dDesTipDocAso>'
                    '<dCdCDERef>%s</dCdCDERef></gCamDEAsoc>' % asociado['cdc'])
        else:
            asoc = ('<gCamDEAsoc><iTipDocAso>2</iTipDocAso><dDesTipDocAso>Impreso</dDesTipDocAso>'
                    '<dNTimDI>{t}</dNTimDI><dEstDocAso>{e}</dEstDocAso><dPExpDocAso>{p}</dPExpDocAso>'
                    '<dNumDocAso>{nu}</dNumDocAso><iTipoDocAso>1</iTipoDocAso>'
                    '<dDTipoDocAso>Factura</dDTipoDocAso><dFecEmiDI>{f}</dFecEmiDI></gCamDEAsoc>'
                    ).format(t=asociado['timbrado'], e=asociado['est'], p=asociado['punto'],
                             nu=asociado['numero'], f=asociado['fecha'])

    total_gs_xml = ''
    if total_gs is not None:
        total_gs_xml = '<dTotalGs>%s</dTotalGs>' % n(total_gs, decimales=0)

    gfe = ''
    if itide == 1:
        gfe = ('<gCamFE><iIndPres>1</iIndPres><dDesIndPres>Operación presencial</dDesIndPres></gCamFE>')

    cuerpo_items = ''.join(xml_item(i, decimales, largo) for i in items)
    de = (
        '<DE Id="{cdc}"><dDVId>{dv}</dDVId><dFecFirma>{fecha}T{hora}</dFecFirma><dSisFact>1</dSisFact>'
        '<gOpeDE><iTipEmi>1</iTipEmi><dDesTipEmi>Normal</dDesTipEmi><dCodSeg>123456789</dCodSeg></gOpeDE>'
        '<gTimb><iTiDE>{itide}</iTiDE><dDesTiDE>{dtipo}</dDesTiDE><dNumTim>{timbrado}</dNumTim>'
        '<dEst>{est}</dEst><dPunExp>{punto}</dPunExp><dNumDoc>{numero}</dNumDoc>'
        '<dFeIniT>2026-01-15</dFeIniT></gTimb>'
        '<gDatGralOpe><dFeEmiDE>{fecha}T{hora}</dFeEmiDE>{ope}'
        '<gEmis><dRucEm>{rucem}</dRucEm><dDVEmi>{dvem}</dDVEmi><iTipCont>1</iTipCont>'
        '<dNomEmi>{nomem}</dNomEmi><dDirEmi>CALLE DE PRUEBA 123</dDirEmi><dNumCas>0</dNumCas>{vacio}'
        '<cDepEmi>12</cDepEmi><dDesDepEmi>CENTRAL</dDesDepEmi><cCiuEmi>6113</cCiuEmi>'
        '<dDesCiuEmi>CIUDAD DE PRUEBA</dDesCiuEmi><dTelEmi>+595210000000</dTelEmi>'
        '<dEmailE>facturas@proveedor-prueba.example</dEmailE>'
        '<gActEco><cActEco>47721</cActEco><dDesActEco>ACTIVIDAD DE PRUEBA</dDesActEco></gActEco></gEmis>'
        '<gDatRec><iNatRec>1</iNatRec><iTiOpe>2</iTiOpe><cPaisRec>PRY</cPaisRec>'
        '<dDesPaisRe>Paraguay</dDesPaisRe><iTiContRec>1</iTiContRec><dRucRec>{rucre}</dRucRec>'
        '<dDVRec>{dvre}</dDVRec><dNomRec>{nomre}</dNomRec>'
        '<dEmailRec>compras@comprador-prueba.example</dEmailRec></gDatRec></gDatGralOpe>'
        '<gDtipDE>{gfe}{cond}{items}{ncde}</gDtipDE>'
        '<gTotSub><dSubExe>{exe}</dSubExe><dSubExo>0</dSubExo><dSub5>{s5}</dSub5><dSub10>{s10}</dSub10>'
        '<dTotOpe>{tot}</dTotOpe><dTotDesc>{desc}</dTotDesc><dTotDescGlotem>0</dTotDescGlotem>'
        '<dTotAntItem>0</dTotAntItem><dTotAnt>0</dTotAnt><dPorcDescTotal>0</dPorcDescTotal>'
        '<dDescTotal>0.0</dDescTotal><dAnticipo>0</dAnticipo><dRedon>{redon}</dRedon>'
        '<dTotGralOpe>{tot}</dTotGralOpe><dIVA5>{i5}</dIVA5><dIVA10>{i10}</dIVA10>'
        '<dLiqTotIVA5>0</dLiqTotIVA5><dLiqTotIVA10>0</dLiqTotIVA10><dTotIVA>{iva}</dTotIVA>'
        '<dBaseGrav5>{b5}</dBaseGrav5><dBaseGrav10>{b10}</dBaseGrav10>'
        '<dTBasGraIVA>{bt}</dTBasGraIVA>{tgs}</gTotSub>{asoc}</DE>'
    ).format(
        cdc=cdc, dv=cdc[-1], fecha=emision.isoformat(), hora=hora, itide=itide,
        dtipo=descripcion_tipo, timbrado=timbrado, est=est, punto=punto, numero=numero,
        ope=ope, rucem=ruc_emisor, dvem=dv_modulo11(ruc_emisor), nomem=nombre_emisor, vacio=vacio,
        rucre=ruc_receptor, dvre=dv_modulo11(ruc_receptor), nomre=nombre_receptor, gfe=gfe,
        cond=cond, items=cuerpo_items, ncde=ncde, exe=n(sub[0], largo), s5=n(sub[5], largo),
        s10=n(sub[10], largo), tot=n(total_general, largo), desc=n(descuento, decimales=0),
        redon=redon, i5=n(iva[5], largo), i10=n(iva[10], largo), iva=n(total_iva, largo),
        b5=n(base5, largo), b10=n(base10, largo), bt=n(base5 + base10, largo), tgs=total_gs_xml,
        asoc=asoc)

    firma = (
        '<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"><SignedInfo>'
        '<CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>'
        '<SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>'
        '<Reference URI="#{cdc}"><DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>'
        '<DigestValue>FIRMA-DE-PRUEBA</DigestValue></Reference></SignedInfo>'
        '<SignatureValue>FIRMA-DE-PRUEBA</SignatureValue><KeyInfo><X509Data>'
        '<X509Certificate>CERTIFICADO-DE-PRUEBA</X509Certificate></X509Data></KeyInfo></Signature>'
    ).format(cdc=cdc)
    qr = ('<gCamFuFD><dCarQR>https://ekuatia.set.gov.py/consultas/qr?nVersion=150&amp;Id={cdc}'
          '&amp;cHashQR=PRUEBA</dCarQR></gCamFuFD>').format(cdc=cdc)
    rde = ('<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd" '
           'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
           'xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd">'
           '<dVerFor>150</dVerFor>%s%s%s</rDE>') % (de, firma, qr)
    if soap:
        rde = rde.replace(' xmlns="http://ekuatia.set.gov.py/sifen/xsd"', '', 1)
        return (
            '<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
            '<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope"><env:Header/><env:Body>'
            '<rEnviDe xmlns="http://ekuatia.set.gov.py/sifen/xsd"><dId>1</dId><xDE>%s</xDE>'
            '</rEnviDe></env:Body></env:Envelope>') % rde, cdc
    return '<?xml version="1.0" encoding="UTF-8"?>' + rde, cdc


def escribir(nombre, xml):
    with open(os.path.join(SALIDA, nombre), 'w', encoding='utf-8') as archivo:
        archivo.write(xml)


def main():
    os.makedirs(SALIDA, exist_ok=True)

    # Muestra A: DE suelto, IVA 5%, descuento por ítem del 20%, contado en efectivo.
    xml_a, cdc_a = construir(
        est='001', punto='002', numero='0007105', timbrado='12345001', ruc_emisor='80000010',
        ruc_receptor='80000020', nombre_emisor='FARMACIA DE PRUEBA S.A.',
        emision=date(2026, 11, 3), hora='17:39:02',
        items=[item('1001', 'PRODUCTO DE PRUEBA A X 20 GR.', 1, 26250, 5, desc_unit=5250, pct=D('20.0'),
                    lote='173')])
    escribir('muestra_a_factura_iva5_descuento.xml', xml_a)

    # Muestra B: sobre SOAP, números con 9 decimales, 0E-9, nodos vacíos, RUC con cero inicial.
    xml_b, _ = construir(
        est='001', punto='002', numero='0000464', timbrado='12345002', ruc_emisor='08000030',
        ruc_receptor='80000020', nombre_emisor='PROVEEDOR PERSONA DE PRUEBA',
        emision=date(2026, 11, 5), hora='00:00:00', soap=True, largo=True, nodos_vacios=True,
        items=[item('1', 'Servicio de prueba', 1, 550000, 10)])
    escribir('muestra_b_factura_iva10_soap.xml', xml_b)

    # USD, crédito a 30 días, tipo de cambio global, total en guaraníes.
    xml, _ = construir(
        numero='0000101', emision=date(2026, 11, 2), moneda=('USD', 'Dolar americano'), tipo_cambio=7300,
        decimales=2, condicion=2, plazo='30 días', total_gs=1825000,
        items=[item('A1', 'Licencia de prueba', 2, 100, 10), item('B2', 'Soporte de prueba', 1, 50, 5)])
    escribir('sintetica_usd_credito_plazo.xml', xml)

    # Crédito en 3 cuotas, mezcla de IVA 10, IVA 5 y exento.
    emision = date(2026, 11, 2)
    xml, _ = construir(
        numero='0000102', emision=emision, condicion=2,
        cuotas=[(D('81666'), emision + timedelta(days=30)), (D('81667'), emision + timedelta(days=60)),
                (D('81667'), emision + timedelta(days=90))],
        items=[item('X1', 'Producto gravado 10', 1, 110000, 10),
               item('X2', 'Producto gravado 5', 2, 52500, 5),
               item('X3', 'Producto exento', 1, 30000, 0)])
    escribir('sintetica_credito_cuotas_mixta.xml', xml)

    # Nota de crédito electrónica asociada a la factura A (por CDC).
    xml, _ = construir(
        itide=5, numero='0000050', timbrado='12345001', motivo=(2, 'Devolución'),
        asociado={'tipo': 1, 'cdc': cdc_a}, emision=date(2026, 11, 10),
        items=[item('1001', 'PRODUCTO DE PRUEBA A X 20 GR.', 1, 26250, 5, desc_unit=5250, pct=D('20.0'))])
    escribir('sintetica_nota_credito.xml', xml)

    # Nota de débito asociada a una factura impresa.
    xml, _ = construir(
        itide=6, numero='0000051', motivo=(8, 'Ajuste de precio'),
        asociado={'tipo': 2, 'timbrado': '11111111', 'est': '001', 'punto': '001',
                  'numero': '0000999', 'fecha': '2025-12-01'},
        items=[item('AJ', 'Ajuste de precio', 1, 11000, 10)])
    escribir('sintetica_nota_debito_impresa.xml', xml)

    # Descuento por ítem que Odoo no puede reproducir con 2 decimales.
    xml, _ = construir(
        numero='0000103', items=[item('D1', 'Producto con descuento raro', 1, 99999, 10,
                                       desc_unit=8765, pct=D('8.77'))])
    escribir('sintetica_descuento_no_exacto.xml', xml)

    # Casos que deben rechazarse.
    xml, _ = construir(itide=7, numero='0000200', items=[item('R1', 'Remision', 1, 1000, 10)])
    escribir('invalida_remision.xml', xml)
    escribir('invalida_dtd.xml',
             '<?xml version="1.0"?><!DOCTYPE rDE [<!ENTITY x "x">]><rDE><DE Id="1"/></rDE>')
    escribir('invalida_no_es_de.xml', '<?xml version="1.0"?><factura><total>1</total></factura>')
    print('Muestras generadas en', SALIDA)


if __name__ == '__main__':
    main()
