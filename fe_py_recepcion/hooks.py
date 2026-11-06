# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Propone el diario de compra y los impuestos de IVA 10%, 5% y exento, solo si
    no hay dudas (una única opción posible).

    Es una ayuda para no empezar con Ajustes vacío: queda todo editable en
    Ajustes > Configuración FE_Py Recepción. Si hay más de una opción posible, no se
    elige ninguna, y nunca se pisa un valor ya cargado.
    """
    Tax = env['account.tax'].sudo()
    Journal = env['account.journal'].sudo()
    for company in env['res.company'].sudo().search([]):
        vals = {}
        diarios = Journal.search([('type', '=', 'purchase'), ('company_id', '=', company.id)])
        if len(diarios) == 1:
            for campo in ('fe_py_recepcion_diario_id', 'fe_py_recepcion_diario_nc_id',
                          'fe_py_recepcion_diario_nd_id'):
                if not company[campo]:
                    vals[campo] = diarios.id
        for campo, tasa in (('fe_py_recepcion_impuesto_iva10_id', 10.0),
                            ('fe_py_recepcion_impuesto_iva5_id', 5.0),
                            ('fe_py_recepcion_impuesto_exento_id', 0.0)):
            if company[campo]:
                continue
            impuestos = Tax.search([
                ('company_id', '=', company.id), ('type_tax_use', '=', 'purchase'),
                ('amount_type', '=', 'percent'), ('amount', '=', tasa),
            ])
            if tasa:
                impuestos = impuestos.filtered('price_include')
            if len(impuestos) == 1:
                vals[campo] = impuestos.id
        if vals:
            company.write(vals)
            _logger.info("FE_Py Recepción: configuración inicial propuesta para %s (%s campo(s)).",
                         company.display_name, len(vals))
