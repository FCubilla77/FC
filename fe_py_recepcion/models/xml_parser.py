# -*- coding: utf-8 -*-
"""Lectura del XML de un Documento Electrónico (SIFEN, versión 150) recibido
de un proveedor.

Este archivo NO depende de Odoo (solo de lxml) para poder probarse solo.

Criterio del módulo: el XML lo emite y firma el PROVEEDOR, así que acá
solamente se LEE y se guarda lo que trae. No se genera ni se valida el CDC,
no se verifica la firma digital, no se valida contra el XSD y no se consulta
a SIFEN. Lo único que se rechaza es un archivo que no se puede leer, que no
es un Documento Electrónico, que es de un tipo no soportado, o al que le
falta un dato imprescindible para poder cargar la factura.

Nombres de nodos: tomados del Manual Técnico v150 y confirmados contra XML
reales de proveedores (no contra "Estructura_DE xsd.xml" del proyecto, que
usa otros nombres).
"""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from lxml import etree

# Tipos de Documento Electrónico (iTiDE) que puede recibir un contribuyente
# de un proveedor y que generan un comprobante de compra.
TIPOS_SOPORTADOS = {
    1: 'Factura electrónica',
    5: 'Nota de crédito electrónica',
    6: 'Nota de débito electrónica',
}

TAMANO_MAXIMO = 5 * 1024 * 1024  # 5 MB: un DE real pesa unos pocos KB


class XmlRecepcionError(Exception):
    """El archivo no se pudo leer o le falta un dato imprescindible."""


# ---------------------------------------------------------------------------
# Utilidades de lectura
# ---------------------------------------------------------------------------
def _hijo(nodo, *ruta):
    """Baja por la ruta de nombres locales, ignorando el namespace."""
    for segmento in ruta:
        if nodo is None:
            return None
        nodo = nodo.find('{*}%s' % segmento)
    return nodo


def _txt(nodo, *ruta):
    """Texto del nodo de la ruta, o '' si no existe o está vacío."""
    destino = _hijo(nodo, *ruta)
    if destino is None or destino.text is None:
        return ''
    return destino.text.strip()


def _dec(texto, defecto=None):
    """Decimal tolerante: '21000.0', '550000.000000000', '0E-9', '0'."""
    if texto is None:
        return defecto
    texto = texto.strip()
    if not texto:
        return defecto
    try:
        return Decimal(texto)
    except InvalidOperation:
        return defecto


def _entero(texto, defecto=None):
    valor = _dec(texto)
    if valor is None:
        return defecto
    return int(valor)


def _fecha(texto):
    """Fecha (sin hora) de '2026-11-05' o '2026-11-05T00:00:00'."""
    if not texto:
        return None
    try:
        return datetime.strptime(texto.strip()[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def normalizar_ruc(ruc, dv=''):
    """(base, dv) sin ceros a la izquierda ni signos: '08000030' -> '8000030'."""
    base = re.sub(r'\D', '', ruc or '').lstrip('0')
    dv = re.sub(r'\D', '', dv or '')
    return base, dv


def normalizar_vat(vat):
    """(base, dv) a partir de un RUC con formato 'NNNNNNN-D' o sin DV."""
    vat = (vat or '').strip()
    if '-' in vat:
        base, _sep, dv = vat.partition('-')
        return normalizar_ruc(base, dv)
    return normalizar_ruc(vat, '')


def formatear_ruc(base, dv):
    """'8000030' + '4' -> '8000030-4' (formato de RUC de local_py)."""
    if base and dv:
        return '%s-%s' % (base, dv)
    return base or ''


def componentes_cdc(cdc):
    """Parte el CDC en sus bloques. SOLO LECTURA: no lo valida.

    Estructura (Manual Técnico): tipo de DE (2) + RUC emisor (8) + DV (1) +
    establecimiento (3) + punto (3) + número (7) + tipo de contribuyente (1) +
    fecha (8) + tipo de emisión (1) + código de seguridad (9) + DV (1).
    """
    if not cdc or len(cdc) != 44 or not cdc.isdigit():
        return {}
    return {
        'tipo': cdc[0:2],
        'ruc': cdc[2:10],
        'dv': cdc[10],
        'establecimiento': cdc[11:14],
        'punto': cdc[14:17],
        'numero': cdc[17:24],
    }


# ---------------------------------------------------------------------------
# Lectura del documento
# ---------------------------------------------------------------------------
def _buscar_rde(contenido):
    """Devuelve el nodo rDE, venga suelto o dentro del sobre SOAP / lote."""
    if not contenido or not contenido.strip():
        raise XmlRecepcionError('El archivo está vacío.')
    if len(contenido) > TAMANO_MAXIMO:
        raise XmlRecepcionError('El archivo es demasiado grande para ser un Documento Electrónico.')
    muestra = contenido.upper()
    if b'<!DOCTYPE' in muestra or b'<!ENTITY' in muestra:
        # Un DE de SIFEN no lleva DTD. Se rechaza para evitar expansión de
        # entidades (XXE / "billion laughs").
        raise XmlRecepcionError('El archivo contiene una definición DTD, que no corresponde a un Documento Electrónico.')
    parser = etree.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False,
        dtd_validation=False, remove_comments=True, huge_tree=False,
    )
    try:
        raiz = etree.fromstring(contenido, parser)
    except etree.XMLSyntaxError as error:
        raise XmlRecepcionError('El archivo no es un XML válido: %s' % error)

    candidatos = [
        nodo for nodo in raiz.iter()
        if isinstance(nodo.tag, str) and etree.QName(nodo).localname == 'rDE'
    ]
    if not candidatos:
        if etree.QName(raiz).localname == 'DE':
            return raiz
        raise XmlRecepcionError('El archivo no contiene un Documento Electrónico de SIFEN (nodo rDE).')
    if len(candidatos) > 1:
        raise XmlRecepcionError(
            'El archivo contiene %s documentos; se admite uno por archivo.' % len(candidatos))
    return candidatos[0]


def _leer_item(nodo, orden):
    valor = _hijo(nodo, 'gValorItem')
    resta = _hijo(valor, 'gValorRestaItem')
    iva = _hijo(nodo, 'gCamIVA')
    cantidad = _dec(_txt(nodo, 'dCantProSer'), Decimal(0))
    precio = _dec(_txt(valor, 'dPUniProSer'), Decimal(0))
    total = _dec(_txt(resta, 'dTotOpeItem'))
    if total is None:
        total = _dec(_txt(valor, 'dTotBruOpeItem'))
    if total is None:
        total = precio * cantidad
    return {
        'orden': orden,
        'codigo': _txt(nodo, 'dCodInt'),
        'descripcion': _txt(nodo, 'dDesProSer'),
        'unidad_codigo': _txt(nodo, 'cUniMed'),
        'unidad_desc': _txt(nodo, 'dDesUniMed'),
        'cantidad': cantidad,
        'precio': precio,
        'total_bruto': _dec(_txt(valor, 'dTotBruOpeItem')),
        'descuento_item': _dec(_txt(resta, 'dDescItem'), Decimal(0)),
        'descuento_pct': _dec(_txt(resta, 'dPorcDesIt'), Decimal(0)),
        'descuento_global': _dec(_txt(resta, 'dDescGloItem'), Decimal(0)),
        'total': total,
        'afectacion': _txt(iva, 'iAfecIVA'),
        'afectacion_desc': _txt(iva, 'dDesAfecIVA'),
        'proporcion': _dec(_txt(iva, 'dPropIVA')),
        'tasa': _entero(_txt(iva, 'dTasaIVA'), 0),
        'base_gravada': _dec(_txt(iva, 'dBasGravIVA'), Decimal(0)),
        'liq_iva': _dec(_txt(iva, 'dLiqIVAItem'), Decimal(0)),
        'lote': _txt(nodo, 'gRasMerc', 'dNumLote'),
    }


def _leer_asociado(nodo):
    tipo = _entero(_txt(nodo, 'iTipDocAso'))
    return {
        'tipo': tipo,  # 1 electrónico, 2 impreso, 3 constancia electrónica
        'tipo_desc': _txt(nodo, 'dDesTipDocAso'),
        'cdc': _txt(nodo, 'dCdCDERef'),
        'timbrado': _txt(nodo, 'dNTimDI'),
        'establecimiento': _txt(nodo, 'dEstDocAso'),
        'punto': _txt(nodo, 'dPExpDocAso'),
        'numero': _txt(nodo, 'dNumDocAso'),
        'tipo_impreso': _entero(_txt(nodo, 'iTipoDocAso')),
        'fecha': _fecha(_txt(nodo, 'dFecEmiDI')),
    }


def parsear(contenido):
    """Lee el XML (bytes) y devuelve un diccionario con sus datos.

    Los importes se devuelven como Decimal. Lanza XmlRecepcionError si el
    archivo no se puede leer o le falta un dato imprescindible.
    """
    rde = _buscar_rde(contenido)
    de = rde if etree.QName(rde).localname == 'DE' else _hijo(rde, 'DE')
    if de is None:
        raise XmlRecepcionError('El documento no tiene el nodo DE.')

    cdc = (de.get('Id') or '').strip()
    if not cdc:
        raise XmlRecepcionError('El documento no informa el CDC (atributo Id del nodo DE).')

    timbre = _hijo(de, 'gTimb')
    itide = _entero(_txt(timbre, 'iTiDE'))
    if itide is None:
        raise XmlRecepcionError('El documento no informa el tipo de documento (iTiDE).')
    if itide not in TIPOS_SOPORTADOS:
        raise XmlRecepcionError(
            'Tipo de documento no soportado: %s (%s). Solo se reciben factura, '
            'nota de crédito y nota de débito electrónicas.'
            % (itide, _txt(timbre, 'dDesTiDE') or 'sin descripción'))

    timbrado = _txt(timbre, 'dNumTim')
    est = _txt(timbre, 'dEst')
    punto = _txt(timbre, 'dPunExp')
    numero = _txt(timbre, 'dNumDoc')
    for etiqueta, valor in (('timbrado (dNumTim)', timbrado), ('establecimiento (dEst)', est),
                            ('punto de expedición (dPunExp)', punto), ('número (dNumDoc)', numero)):
        if not valor:
            raise XmlRecepcionError('El documento no informa el %s.' % etiqueta)
    nro_documento = '%s-%s-%s' % (est.zfill(3), punto.zfill(3), numero.zfill(7))

    general = _hijo(de, 'gDatGralOpe')
    emision_texto = _txt(general, 'dFeEmiDE')
    fecha_emision = _fecha(emision_texto)
    if not fecha_emision:
        raise XmlRecepcionError('El documento no informa la fecha de emisión (dFeEmiDE).')

    # -- Emisor -----------------------------------------------------------
    emis = _hijo(general, 'gEmis')
    ruc_em, dv_em = normalizar_ruc(_txt(emis, 'dRucEm'), _txt(emis, 'dDVEmi'))
    if not ruc_em or not _txt(emis, 'dNomEmi'):
        raise XmlRecepcionError('El documento no informa el RUC o el nombre del emisor.')
    emisor = {
        'ruc': ruc_em,
        'dv': dv_em,
        'ruc_dv': formatear_ruc(ruc_em, dv_em),
        'nombre': _txt(emis, 'dNomEmi'),
        'fantasia': _txt(emis, 'dNomFanEmi'),
        'direccion': _txt(emis, 'dDirEmi'),
        'telefono': _txt(emis, 'dTelEmi'),
        'email': _txt(emis, 'dEmailE'),
        'departamento': _txt(emis, 'dDesDepEmi'),
        'ciudad': _txt(emis, 'dDesCiuEmi'),
        'actividad': _txt(emis, 'gActEco', 'dDesActEco'),
    }

    # -- Receptor ---------------------------------------------------------
    rec = _hijo(general, 'gDatRec')
    ruc_rec, dv_rec = normalizar_ruc(_txt(rec, 'dRucRec'), _txt(rec, 'dDVRec'))
    receptor = {
        'ruc': ruc_rec,
        'dv': dv_rec,
        'ruc_dv': formatear_ruc(ruc_rec, dv_rec),
        'nombre': _txt(rec, 'dNomRec'),
        'naturaleza': _txt(rec, 'iNatRec'),
    }

    # -- Operación --------------------------------------------------------
    ope = _hijo(general, 'gOpeCom')
    moneda = _txt(ope, 'cMoneOpe') or 'PYG'
    dtipo = _hijo(de, 'gDtipDE')
    cond = _hijo(dtipo, 'gCamCond')
    condicion = _entero(_txt(cond, 'iCondOpe'), 1)
    pagos = [
        {
            'tipo': _txt(p, 'iTiPago'),
            'descripcion': _txt(p, 'dDesTiPag'),
            'monto': _dec(_txt(p, 'dMonTiPag'), Decimal(0)),
        }
        for p in (cond.findall('{*}gPaConEIni') if cond is not None else [])
    ]
    cred = _hijo(cond, 'gPagCred')
    credito = None
    if cred is not None:
        credito = {
            'tipo': _entero(_txt(cred, 'iCondCred')),  # 1 plazo, 2 cuota
            'plazo': _txt(cred, 'dPlazoCre'),
            'cantidad_cuotas': _entero(_txt(cred, 'dCuotas')),
            'entrega_inicial': _dec(_txt(cred, 'dMonEnt'), Decimal(0)),
            'cuotas': [
                {
                    'monto': _dec(_txt(c, 'dMonCuota'), Decimal(0)),
                    'vencimiento': _fecha(_txt(c, 'dVencCuo')),
                    'moneda': _txt(c, 'cMoneCuo'),
                }
                for c in cred.findall('{*}gCuotas')
            ],
        }

    # -- Ítems ------------------------------------------------------------
    nodos_item = dtipo.findall('{*}gCamItem') if dtipo is not None else []
    items = [_leer_item(n, i) for i, n in enumerate(nodos_item, start=1)]
    if not items:
        raise XmlRecepcionError('El documento no tiene ítems (gCamItem).')

    # -- Nota de crédito / débito y documentos asociados -----------------
    motivo = _hijo(dtipo, 'gCamNCDE')
    asociados = [_leer_asociado(n) for n in de.iter('{*}gCamDEAsoc')]

    # -- Totales ----------------------------------------------------------
    tot = _hijo(de, 'gTotSub')
    if tot is None:
        raise XmlRecepcionError('El documento no tiene los totales (gTotSub).')
    total_general = _dec(_txt(tot, 'dTotGralOpe'))
    if total_general is None:
        raise XmlRecepcionError('El documento no informa el total general de la operación (dTotGralOpe).')

    return {
        'cdc': cdc,
        'version': _txt(rde, 'dVerFor'),
        'itide': itide,
        'tipo_documento': TIPOS_SOPORTADOS[itide],
        'timbrado': timbrado,
        'timbrado_inicio': _fecha(_txt(timbre, 'dFeIniT')),
        'establecimiento': est.zfill(3),
        'punto': punto.zfill(3),
        'numero': numero.zfill(7),
        'nro_documento': nro_documento,
        'fecha_emision': fecha_emision,
        'fecha_emision_xml': emision_texto,
        'tipo_transaccion': _txt(ope, 'dDesTipTra'),
        'moneda': moneda,
        'moneda_desc': _txt(ope, 'dDesMoneOpe'),
        'condicion_tipo_cambio': _txt(ope, 'dCondTiCam'),
        'tipo_cambio': _dec(_txt(ope, 'dTiCam')),
        'emisor': emisor,
        'receptor': receptor,
        'condicion': condicion,  # 1 contado, 2 crédito
        'condicion_desc': _txt(cond, 'dDCondOpe'),
        'pagos': pagos,
        'credito': credito,
        'items': items,
        'motivo_codigo': _entero(_txt(motivo, 'iMotEmi')),
        'motivo_desc': _txt(motivo, 'dDesMotEmi'),
        'asociados': asociados,
        'totales': {
            'exento': _dec(_txt(tot, 'dSubExe'), Decimal(0)),
            'exonerado': _dec(_txt(tot, 'dSubExo'), Decimal(0)),
            'sub5': _dec(_txt(tot, 'dSub5'), Decimal(0)),
            'sub10': _dec(_txt(tot, 'dSub10'), Decimal(0)),
            'descuento': _dec(_txt(tot, 'dTotDesc'), Decimal(0)),
            'total_general': total_general,
            'iva': _dec(_txt(tot, 'dTotIVA'), Decimal(0)),
            'total_gs': _dec(_txt(tot, 'dTotalGs')),
        },
    }
