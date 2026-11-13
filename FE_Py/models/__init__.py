# -*- coding: utf-8 -*-
# ORDEN IMPORTANTE: los catálogos primero (otros modelos los referencian),
# y un archivo con _inherit siempre después del que define el _name.

# -- Catálogos y configuración propios de FE_Py ------------------------
from . import fe_py_catalogos
from . import fe_py_configuracion

# -- Campos que FE_Py agrega a modelos nativos de Odoo -----------------
from . import account_tax
from . import res_currency
from . import account_payment_term
from . import product_template
from . import uom_uom
from . import res_partner

# -- Campos que FE_Py agrega a modelos de local_py ---------------------
from . import fe_py_tipo_identificacion_fiscal_ext
from . import fe_py_tipo_fiscal_ext
from . import fe_py_documento_anulado_ext

# -- Documento Electrónico -------------------------------------------
from . import fe_py_cuota
from . import fe_py_documento_electronico_log
from . import fe_py_documento_electronico
from . import fe_py_documento_electronico_xml
from . import fe_py_documento_electronico_signing
from . import fe_py_documento_electronico_envio
from . import fe_py_documento_electronico_kude
from . import fe_py_documento_electronico_email
from . import fe_py_documento_electronico_final

# -- Eventos SIFEN y reintento automático -----------------------------
from . import fe_py_evento
from . import fe_py_evento_procesamiento
from . import fe_py_cron

# -- Campos que FE_Py agrega a los modelos contables de Odoo -----------
from . import res_company
from . import account_journal
from . import account_move
