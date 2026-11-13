# -*- coding: utf-8 -*-

from odoo import fields, models


class LocalPyTipoIdentificacionFiscal(models.Model):
    """Correspondencia con la tabla D208 de SIFEN.

    El catálogo de local_py sigue la Tabla 3 de Marangatu, que no coincide
    fila por fila con la tabla de SIFEN — por eso hace falta este mapeo.
    Se dejan como campos editables (no una lista fija) para que, si la
    DNIT agrega un tipo de documento, se pueda cargar sin tocar el módulo.
    """
    _inherit = 'local_py.tipo_identificacion_fiscal'

    fe_py_itipidrec = fields.Char(
        string='FEPy Código de Documento SIFEN',
        help='Código que se informa como iTipIDRec cuando el receptor no '
             'tiene RUC (1=Cédula paraguaya, 2=Pasaporte, 3=Cédula '
             'extranjera, 4=Carnet de residencia, 5=Innominado, 6=Tarjeta '
             'Diplomática, 9=Otro).\n\n'
             'Se deja vacío en "RUC": un receptor con RUC se informa por '
             'dRucRec/dDVRec, no pasa por esta tabla.',
    )
    fe_py_itipidrec_descripcion = fields.Char(
        string='FEPy Descripción del Documento SIFEN',
        help='Texto que se informa como dDTipIDRec. Para el código 9 '
             '("Otro") se usa, en su lugar, la descripción cargada en el '
             'Contacto.',
    )
    fe_py_es_ruc = fields.Boolean(
        string='FEPy Es RUC (contribuyente)',
        help='Marca el registro que corresponde al RUC paraguayo. Un '
             'receptor con este tipo se informa como Contribuyente '
             '(iNatRec=1); cualquier otro, como No Contribuyente.',
    )
