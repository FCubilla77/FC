# -*- coding: utf-8 -*-
"""Catálogos de códigos SIFEN.

Todos los códigos que exige la DNIT viven en estos modelos, NO en el
código del programa. Si mañana la DNIT agrega un valor a cualquiera de
sus tablas, se carga acá sin necesidad de tocar el módulo.

Los catálogos vienen precargados con los datos del Manual Técnico v150,
salvo Actividad Económica, que cada empresa carga con sus propios datos
tal como están registrados ante la DNIT.
"""

from odoo import api, fields, models


class FePyCatalogoBase(models.AbstractModel):
    """Estructura común de todos los catálogos SIFEN: un código (lo que
    va al XML) y una descripción (lo que va al XML como dDes*)."""
    _name = 'fe_py.catalogo.base'
    _description = 'Base de Catálogos SIFEN'
    _order = 'sequence, codigo'

    sequence = fields.Integer(string='Secuencia', default=10)
    codigo = fields.Char(
        string='Código SIFEN', required=True, index=True,
        help='Valor que se informa en el XML. Debe coincidir exactamente '
             'con el código publicado por la DNIT.',
    )
    name = fields.Char(
        string='Descripción SIFEN', required=True, translate=False,
        help='Texto que se informa en el XML junto al código. SIFEN valida '
             'que coincida con su propia descripción — cambiarlo puede '
             'provocar el rechazo del documento.',
    )
    active = fields.Boolean(string='Activo', default=True)

    @api.depends('codigo', 'name')
    def _compute_display_name(self):
        for reg in self:
            reg.display_name = '%s - %s' % (reg.codigo or '', reg.name or '')

    _codigo_uniq = models.Constraint(
        'unique(codigo)',
        'Ya existe un registro con ese Código SIFEN.',
    )


class FePySistemaFacturacion(models.Model):
    """dSisFact (A005) — Sistema de facturación utilizado."""
    _name = 'fe_py.sistema_facturacion'
    _inherit = 'fe_py.catalogo.base'
    _description = 'FEPy Sistema de Facturación'


class FePyTipoEmision(models.Model):
    """iTipEmi (B002) — Tipo de emisión: Normal o Contingencia."""
    _name = 'fe_py.tipo_emision'
    _inherit = 'fe_py.catalogo.base'
    _description = 'FEPy Tipo de Emisión'


class FePyTipoTransaccion(models.Model):
    """iTipTra (D011) — Tipo de transacción (13 valores)."""
    _name = 'fe_py.tipo_transaccion'
    _inherit = 'fe_py.catalogo.base'
    _description = 'FEPy Tipo de Transacción'

    tipo_producto = fields.Selection(
        string='Se propone automáticamente para',
        selection=[
            ('bienes', 'Operaciones solo de bienes'),
            ('servicios', 'Operaciones solo de servicios'),
            ('mixto', 'Operaciones mixtas'),
        ],
        help='Si se completa, este Tipo de Transacción se propone solo al '
             'cargar una operación con esa composición. El usuario siempre '
             'puede cambiarlo por cualquier otro de la tabla.',
    )


class FePyTipoImpuesto(models.Model):
    """iTImp (D013) — Tipo de impuesto afectado."""
    _name = 'fe_py.tipo_impuesto'
    _inherit = 'fe_py.catalogo.base'
    _description = 'FEPy Tipo de Impuesto Afectado'


class FePyCondicionTipoCambio(models.Model):
    """dCondTiCam (D017) — Global o Por ítem."""
    _name = 'fe_py.condicion_tipo_cambio'
    _inherit = 'fe_py.catalogo.base'
    _description = 'FEPy Condición del Tipo de Cambio'


class FePyTipoContribuyenteReceptor(models.Model):
    """iTiContRec (D206) — Persona Física o Jurídica del receptor."""
    _name = 'fe_py.tipo_contribuyente_receptor'
    _inherit = 'fe_py.catalogo.base'
    _description = 'FEPy Tipo de Contribuyente (Receptor)'


class FePyTipoOperacion(models.Model):
    """iTiOpe (D202) — B2B, B2C, B2G, B2F."""
    _name = 'fe_py.tipo_operacion'
    _inherit = 'fe_py.catalogo.base'
    _description = 'FEPy Tipo de Operación'

    es_b2g = fields.Boolean(
        string='Es venta al Estado (B2G)',
        help='Marca el registro que corresponde a operaciones con Organismos '
             'del Estado. Se usa para exigir los datos de Compras Públicas.',
    )
    es_b2f = fields.Boolean(
        string='Es venta al exterior (B2F)',
        help='Marca el registro de operaciones con el exterior. Se usa para '
             'omitir Departamento/Distrito/Ciudad del receptor, que SIFEN '
             'no acepta en ese caso.',
    )


class FePyIndicadorPresencia(models.Model):
    """iIndPres (E011) — Presencial, electrónica, cíclica, etc."""
    _name = 'fe_py.indicador_presencia'
    _inherit = 'fe_py.catalogo.base'
    _description = 'FEPy Indicador de Presencia'


class FePyMotivoEmision(models.Model):
    """iMotEmi (E401) — Motivo de emisión de Nota de Crédito/Débito."""
    _name = 'fe_py.motivo_emision'
    _inherit = 'fe_py.catalogo.base'
    _description = 'FEPy Motivo de Emisión (NC/ND)'


class FePyTipoDocumentoAsociado(models.Model):
    """iTipDocAso (H002) — Electrónico, impreso o constancia."""
    _name = 'fe_py.tipo_documento_asociado'
    _inherit = 'fe_py.catalogo.base'
    _description = 'FEPy Tipo de Documento Asociado'


class FePyUnidadMedida(models.Model):
    """cUniMed (E708) — Tabla 5 del Manual Técnico (32 unidades).

    Ojo con las dos descripciones: al XML va la REPRESENTACIÓN corta
    (dDesUniMed = 'UNI', 'kg', 'LT'), no el nombre largo.
    """
    _name = 'fe_py.unidad_medida'
    _inherit = 'fe_py.catalogo.base'
    _description = 'FEPy Unidad de Medida'

    name = fields.Char(
        string='Representación SIFEN', required=True,
        help='Abreviatura que se informa en el XML (dDesUniMed): UNI, kg, '
             'LT, m, etc. Es este texto el que viaja, no la descripción larga.',
    )
    descripcion_larga = fields.Char(
        string='Descripción', help='Nombre completo, solo para identificarla '
                                   'con comodidad en las pantallas.',
    )

    @api.depends('codigo', 'name', 'descripcion_larga')
    def _compute_display_name(self):
        for reg in self:
            reg.display_name = '%s - %s' % (reg.codigo or '', reg.descripcion_larga or reg.name or '')


class FePyAfectacionIva(models.Model):
    """iAfecIVA (E731) — Tabla 6: Gravado, Exonerado, Exento, Gravado parcial.

    El catálogo se carga con los 4 códigos oficiales, pero Exonerado y
    Gravado parcial quedan marcados como NO disponibles: su cálculo
    (total exonerado, proporción gravada y base exenta por línea) todavía
    no está implementado, y usarlos generaría un XML internamente
    inconsistente. Habilitarlos más adelante es destildar la marca.
    """
    _name = 'fe_py.afectacion_iva'
    _inherit = 'fe_py.catalogo.base'
    _description = 'FEPy Código de Afectación IVA'

    disponible = fields.Boolean(
        string='Disponible para usar', default=True,
        help='Si está destildado, el código existe en el catálogo (fiel a la '
             'tabla de la DNIT) pero no puede asignarse a un impuesto '
             'todavía, porque su cálculo no está implementado.',
    )
    proporcion_gravada = fields.Integer(
        string='Proporción Gravada (%)', default=100,
        help='dPropIVA que se informa en cada línea con este código. '
             '100 para Gravado, 0 para Exento y Exonerado.',
    )


class FePyActividadEconomica(models.Model):
    """cActEco (D103) — Tabla 3, publicada por la DNIT vía servicio web.

    No se precarga: cada empresa carga sus propias actividades tal como
    están registradas en la DNIT, con el texto exacto.
    """
    _name = 'fe_py.actividad_economica'
    _inherit = 'fe_py.catalogo.base'
    _description = 'FEPy Actividad Económica'

    name = fields.Text(
        string='Descripción de la Actividad', required=True,
        help='Debe coincidir EXACTAMENTE con el texto registrado en la DNIT.',
    )
