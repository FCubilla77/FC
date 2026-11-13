# -*- coding: utf-8 -*-
"""Control de licencia del módulo FE_Py (Facturación Electrónica Paraguay), 2026.19.013.

La licencia se emite fuera de este módulo, con una herramienta propia de FC_Py que
conserva la clave privada de firma (nunca viaja con el módulo). Este archivo solo
contiene la clave PÚBLICA, que permite VERIFICAR un código de licencia, nunca generar
uno nuevo: tenerla no alcanza para falsificar una licencia válida. La misma clave
firma las licencias de todos los productos de FC_Py (Taller, local_py, l10n_py,
FE_Py); el código de licencia identifica a qué producto corresponde (campo `p`), así
que el código de un producto no sirve para activar otro. El control de este módulo es
independiente del de local_py: aunque FE_Py dependa de local_py para funcionar, cada
uno exige su propio código, y este archivo no importa nada de otros módulos de FC_Py.

El código de licencia tiene el formato "FC_PY1.<datos>.<firma>" (base64 URL-safe),
con los datos: producto (`p`, debe ser "fe_py"), identificador de la base de datos
(`database.uuid`), nombre del cliente, fecha de vencimiento y versión de Odoo
autorizada (`m`). `fe_py_decodificar_licencia` lo valida.

Versión de Odoo autorizada: el código queda atado al número central de la versión del
módulo (el "19" de "2026.19.013"), no a la versión completa. Mientras ese número no
cambie, cualquier cantidad de correcciones o ajustes menores no afectan la licencia
vigente. Si el módulo pasa a otra versión de Odoo, el código emitido para la anterior
queda en estado "otra_version" y hay que pedir uno nuevo, sin ningún paso manual
adicional: la comparación es automática, cada vez que se calcula el estado.

Qué bloquea la licencia (ver también models/fe_py_licencia_mixin.py):
  * La CONFIRMACIÓN de una Factura, Nota de Crédito o Nota de Débito de Cliente cuyo
    Diario tenga un Tipo Fiscal electrónico: el comprobante queda en Borrador, igual
    que cuando faltan datos de Facturación Electrónica. Sin licencia no se emiten
    documentos electrónicos — pero la facturación por Diarios NO electrónicos
    (timbrado físico/preimpreso) sigue funcionando sin ninguna restricción, porque
    ese camino no pasa por FE_Py.
  * Creación de los catálogos DNIT propios (Sistema de Facturación, Tipos de Emisión,
    Régimen, Operación, Transacción e Impuesto, Indicador de Presencia, Motivo de
    Emisión, Documento Asociado, Tipo de Contribuyente Receptor, Condición del Tipo
    de Cambio, Afectación IVA, Actividad Económica y Unidad de Medida).
  * Creación y edición de las Configuraciones Generales FEPy — y, por lo tanto, de
    los catálogos editados desde sus pestañas — y de los Eventos SIFEN.
  * Generar/Regenerar XML, Firmar y Enviar a SIFEN, y el envío de un Evento.
  * El cron de reintento automático omite las compañías sin licencia válida.
Nunca bloquea: lectura, informes, el Log de Operaciones, las cuotas de un documento,
la edición de un catálogo ya creado, la facturación no electrónica, ni la pantalla de
Ajustes. Tampoco bloquea Generar KuDE ni Enviar Email al Cliente: son la impresión y
la entrega de un documento YA aprobado por SIFEN, y un vencimiento de licencia no
debe impedirle al cliente reimprimir o reenviar lo que ya emitió.

`FE_PY_LICENCIA_OBLIGATORIA` es el interruptor para los builds que se entregan a un
partner con reventa ilimitada (contrato con código fuente): se deja en `False` al
armar su ZIP porque, para ese canal, el control pasa a ser enteramente contractual
(ver LICENSE y el contrato de partner). En el build que FC_Py distribuye directamente
a sus propios clientes queda en `True`.
"""
import base64
import json
from datetime import date

from odoo import release
from odoo.exceptions import UserError
from odoo.modules import module as _fe_py_odoo_module

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    _FE_PY_CRYPTO_DISPONIBLE = True
except Exception:  # pragma: no cover - entorno sin la librería `cryptography`
    _FE_PY_CRYPTO_DISPONIBLE = False

# Prefijo fijo del formato de licencia de FC_Py: es el MISMO para todos sus
# productos (Taller, local_py, l10n_py, FE_Py); no se elige uno distinto por
# producto. Lo que identifica al producto es el campo `p` del payload (ver abajo).
# No confundirlo con el prefijo de nombres de este módulo, que es `fe_py`.
FE_PY_LICENCIA_PREFIJO = "FC_PY1"

# Código de producto que viaja en el payload (`p`). Es lo que impide que un código
# emitido para local_py, l10n_py o Taller active este módulo.
FE_PY_LICENCIA_PRODUCTO = "fe_py"

# Nombre TÉCNICO del módulo, para leer su manifest. No coincide con el código de
# producto porque la carpeta del módulo lleva mayúsculas: `get_manifest` necesita
# el nombre exacto del directorio.
FE_PY_LICENCIA_MODULO = "FE_Py"

# Interruptor de build. `True`: build normal, con control de licencia (el que FC_Py
# entrega a sus clientes directos). `False`: build de partner con reventa ilimitada,
# sin control técnico (la protección queda en el contrato). Se cambia a mano al
# armar el ZIP de entrega a un partner.
FE_PY_LICENCIA_OBLIGATORIA = True

# Clave pública de verificación (FC_Py), la misma para todos los productos. Reemplazar
# junto con la clave privada si se regenera el par de claves.
FE_PY_CLAVE_PUBLICA_PEM = b"""-----BEGIN PUBLIC KEY-----
MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEA3zxYZQG18CTzhY3AnsqQ
5ejx2T7TnK6LKqFe+1cPkIjIzLAotQSYZQE8y4T3d+yISVCQdPZ0Gctj0NB7LiiP
0L6L537e+6ktpPE3hC386Yeawb29vWC/l3cTdwKrWPYVWlnPbAHaKoDpxd/jc2HR
34mCiSbdR9DrYL6FaY8lxUgoqfS6Yq8cMYT5OTUUTcNkhb7A8SgKw5We8gtOg4uT
dnB3D7CjHS17nxc9m76qJMbMTW8VmZDRj8kcJsbi6Sp7nTqEngNYxqzlR1cKnbVF
eRFbbGafT0QWcuae8vrN7EhQ8ULhHksxqqUl4LRbrOAFmco4K0jiv1DQuzKG0hgz
F33/tvBo3ajVG9jyLndLBSZ/Kr3pISHmAaFqVNkVPY/r5L+Yi3M2ElTA9ktIlaAk
cc3rzVMlxA2xuiXRAp36OqkIPzM36kV9giZNLyofNCv/soTh2e3XRpp/RVkPQyfO
ZXLKsN8BWw4GeBITBaUb0/ARyRTzt6F/qJwFlcSkmy2tAgMBAAE=
-----END PUBLIC KEY-----
"""

FE_PY_LICENCIA_MENSAJE = (
    "El módulo FE_Py (Facturación Electrónica Paraguay) no tiene una licencia "
    "válida para esta base de datos.\n\n"
    "Vaya a Localización Paraguay › Facturación Electrónica Py › Licencia FE_Py "
    "(o a Ajustes › Configuración FE_Py, sección «Licencia») para cargar o renovar "
    "el código. El «Código de la base» que FC_Py necesita para emitirlo está en esa "
    "misma pantalla.\n\n"
    "La facturación por Diarios no electrónicos (timbrado físico) no está afectada."
)

_fe_py_clave_publica_cache = None


def _fe_py_obtener_clave_publica():
    global _fe_py_clave_publica_cache
    if _fe_py_clave_publica_cache is None:
        _fe_py_clave_publica_cache = serialization.load_pem_public_key(
            FE_PY_CLAVE_PUBLICA_PEM)
    return _fe_py_clave_publica_cache


def _fe_py_b64_decode(texto):
    relleno = '=' * (-len(texto) % 4)
    return base64.urlsafe_b64decode(texto + relleno)


def fe_py_decodificar_licencia(codigo):
    """Valida la firma de un código de licencia y devuelve sus datos.

    Devuelve `{'uuid': ..., 'cliente': ..., 'vence': 'AAAA-MM-DD', 'version_odoo': int}`
    si el código es auténtico y corresponde a FE_Py. Lanza `ValueError` (mensaje
    corto, para uso interno) si el formato, la codificación, la firma, el contenido
    o el producto no son válidos (por ejemplo, un código emitido para local_py u otro
    producto de FC_Py). No compara la versión de Odoo contra la instalada: eso lo hace
    quien llama (ver `res.company._compute_fe_py_licencia`), que es quien sabe cuál es
    la versión realmente instalada.
    """
    if not codigo or not codigo.strip():
        raise ValueError("vacío")
    if not _FE_PY_CRYPTO_DISPONIBLE:
        raise ValueError("sin_libreria")
    partes = codigo.strip().split('.')
    if len(partes) != 3 or partes[0] != FE_PY_LICENCIA_PREFIJO:
        raise ValueError("formato")
    try:
        datos = _fe_py_b64_decode(partes[1])
        firma = _fe_py_b64_decode(partes[2])
    except Exception:
        raise ValueError("codificación")
    try:
        _fe_py_obtener_clave_publica().verify(
            firma, datos,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256())
    except InvalidSignature:
        raise ValueError("firma")
    except Exception:
        raise ValueError("firma")
    try:
        payload = json.loads(datos.decode('utf-8'))
    except Exception:
        raise ValueError("contenido")
    if not isinstance(payload, dict) or not all(
            clave in payload for clave in ('p', 'u', 'c', 'v', 'm')):
        raise ValueError("contenido")
    if payload['p'] != FE_PY_LICENCIA_PRODUCTO:
        raise ValueError("otro_producto")
    version_odoo = payload['m']
    if isinstance(version_odoo, bool) or not isinstance(version_odoo, int):
        raise ValueError("contenido")
    try:
        date.fromisoformat(str(payload['v']))
    except ValueError:
        raise ValueError("contenido")
    return {
        'uuid': str(payload['u']),
        'cliente': str(payload['c']),
        'vence': str(payload['v']),
        'version_odoo': version_odoo,
    }


def fe_py_version_odoo_instalada():
    """Número central de la versión del módulo instalado, leído en vivo del manifest
    (el «19» de la versión «2026.19.013»). Devuelve None si no se puede determinar.

    Odoo normaliza la versión del manifest (`adapt_version`): una versión de tres
    partes como la de este módulo ("AAAA.19.NNN") recibe antepuesta la serie de Odoo
    y queda expuesta como "19.0.AAAA.19.NNN"; en ese caso el número central es el
    anteúltimo segmento. Una versión que ya empieza con la serie de Odoo
    ("19.0.AAAA.NNNN") queda tal cual y el número central es el primer segmento.
    Nunca se toma una posición fija desde el principio.
    """
    try:
        manifest = _fe_py_odoo_module.get_manifest(FE_PY_LICENCIA_MODULO)
        version = str((manifest or {}).get('version') or '')
        partes = version.split('.')
        if len(partes) == 4 and '.'.join(partes[:2]) == release.major_version:
            return int(partes[0])
        if len(partes) >= 3:
            return int(partes[-2])
        return None
    except Exception:
        return None


def fe_py_control_activo(env):
    """True si el control de licencia está en vigor en este contexto.

    Inactivo en un build de partner (`FE_PY_LICENCIA_OBLIGATORIA = False`) y
    durante las pruebas automáticas (`current_test`, que Odoo deja asignado mientras
    corre cada caso de prueba), salvo que la propia prueba pida forzar el control con
    el contexto `fe_py_licencia_forzar_test` (así se prueba el bloqueo sin tener
    que simular una licencia en el resto de las pruebas del módulo).
    """
    if not FE_PY_LICENCIA_OBLIGATORIA:
        return False
    if _fe_py_odoo_module.current_test and not env.context.get(
            'fe_py_licencia_forzar_test'):
        return False
    return True


def fe_py_licencia_exenta(env):
    """True si esta operación no debe verificar la licencia.

    Además de lo anterior, exento mientras se instala o actualiza el módulo (carga de
    datos iniciales, antes de que el registro quede listo): sin esto, la propia carga
    de los catálogos DNIT y el `post_init_hook` fallarían.
    """
    if not fe_py_control_activo(env):
        return True
    return not env.registry.ready


def fe_py_licencia_verificar(env, company=None):
    """Lanza `UserError` si la compañía no tiene una licencia válida (salvo exención)."""
    if fe_py_licencia_exenta(env):
        return
    company = company or env.company
    if not company._fe_py_licencia_valida():
        raise UserError(FE_PY_LICENCIA_MENSAJE)


def fe_py_licencia_vigente(env, company=None):
    """True/False sin lanzar excepción, para quien tenga que decidir en silencio
    (el cron de reintento automático, por ejemplo). Devuelve True cuando el control
    está exento, para no alterar la instalación ni las pruebas."""
    if fe_py_licencia_exenta(env):
        return True
    company = company or env.company
    return company._fe_py_licencia_valida()
