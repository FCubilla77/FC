# -*- coding: utf-8 -*-
# ORDEN IMPORTANTE: un archivo que extiende un modelo con _inherit debe
# cargarse DESPUÉS del que lo define con _name. Además, los módulos que
# exportan tablas compartidas (res_partner, local_py_tipo_identificacion_fiscal)
# van primero, porque otros importan constantes desde ellos.
from . import res_partner
from . import local_py_tipo_identificacion_fiscal
from . import local_py_tipo_fiscal
from . import local_py_documento_anulado
from . import fe_py_cuota
from . import fe_py_documento_electronico_log
from . import fe_py_documento_electronico
from . import fe_py_documento_electronico_xml
from . import fe_py_documento_electronico_signing
from . import fe_py_documento_electronico_envio
from . import fe_py_documento_electronico_kude
from . import fe_py_documento_electronico_email
from . import fe_py_documento_electronico_final
from . import fe_py_evento
from . import fe_py_evento_procesamiento
from . import fe_py_cron
from . import res_company
from . import account_journal
from . import account_move
