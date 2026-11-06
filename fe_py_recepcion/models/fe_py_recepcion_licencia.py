# -*- coding: utf-8 -*-
"""Control de licencia del módulo FE_Py Recepción de Facturas (2026.19.006).

La licencia se emite fuera de este módulo, con una herramienta propia de FC_Py que
conserva la clave privada de firma (nunca viaja con el módulo). Este archivo solo
contiene la clave PÚBLICA, que permite VERIFICAR un código de licencia, nunca generar
uno nuevo: tenerla no alcanza para falsificar una licencia válida. La misma clave
firma las licencias de todos los productos de FC_Py (Taller, local_py, l10n_py y este
módulo); el código de licencia identifica a qué producto corresponde (campo `p`), así
que el código de un producto no sirve para activar otro. Este módulo es autosuficiente:
no importa nada de otros módulos de FC_Py ni requiere que estén instalados.

El código de licencia tiene el formato "FC_PY1.<datos>.<firma>" (base64 URL-safe), con
los datos: producto (`p`, debe ser "fe_py_recepcion"), identificador de la base de datos
(`database.uuid`), nombre del cliente, fecha de vencimiento y versión de Odoo
autorizada (`m`). `fe_py_recepcion_decodificar_licencia` lo valida.

Versión de Odoo autorizada: el código queda atado al número central de la versión del
módulo (el "19" de "2026.19.002"), no a la versión completa. Mientras ese número no
cambie, cualquier cantidad de correcciones o ajustes menores no afectan la licencia
vigente. Si el módulo pasa a otra versión de Odoo, el código emitido para la anterior
queda en estado "otra_version" y hay que pedir uno nuevo, sin ningún paso manual
adicional: la comparación es automática, cada vez que se calcula el estado.

Una sola licencia cubre a fe_py_recepcion y a su puente fe_py_recepcion_purchase.

Qué bloquea la licencia (ver también models/fe_py_recepcion_licencia_mixin.py):
  * Creación de las Equivalencias de productos del proveedor.
  * Creación y edición de las Facturas Electrónicas Recibidas: cargar XML, verificar,
    confirmar, cancelar y reabrir.
Nunca bloquea: lectura, líneas y cuotas, la pantalla de Ajustes, ni el regreso
automático de la recepción a Cargado cuando se elimina o cancela su factura.

`FE_PY_RECEPCION_LICENCIA_OBLIGATORIA` es el interruptor para los builds que se
entregan a un partner con reventa ilimitada (contrato con código fuente): se deja en
`False` al armar su ZIP porque, para ese canal, el control pasa a ser enteramente
contractual (ver LICENSE y el contrato de partner). En el build que FC_Py distribuye
directamente a sus propios clientes queda en `True`.
"""
import base64
import json
from datetime import date

from odoo import release
from odoo.exceptions import UserError
from odoo.modules import module as _fe_py_recepcion_odoo_module

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    _FE_PY_RECEPCION_CRYPTO_DISPONIBLE = True
except ImportError:  # pragma: no cover - entorno sin la librería `cryptography`
    _FE_PY_RECEPCION_CRYPTO_DISPONIBLE = False

# Prefijo fijo del formato de licencia de FC_Py: es el MISMO para todos sus
# productos; no se elige uno distinto por producto. Lo que identifica al producto
# es el campo `p` del payload.
FE_PY_RECEPCION_LICENCIA_PREFIJO = "FC_PY1"
FE_PY_RECEPCION_LICENCIA_PRODUCTO = "fe_py_recepcion"

# Interruptor de build. `True`: build normal, con control de licencia (el que FC_Py
# entrega a sus clientes directos). `False`: build de partner con reventa ilimitada,
# sin control técnico (la protección queda en el contrato). Se cambia a mano al
# armar el ZIP de entrega a un partner.
FE_PY_RECEPCION_LICENCIA_OBLIGATORIA = True

# Clave pública de verificación (FC_Py), la misma para todos los productos. Reemplazar
# junto con la clave privada si se regenera el par de claves.
FE_PY_RECEPCION_CLAVE_PUBLICA_PEM = b"""-----BEGIN PUBLIC KEY-----
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

FE_PY_RECEPCION_LICENCIA_MENSAJE = (
    "El módulo FE_Py Recepción de Facturas no tiene una licencia válida para "
    "esta base de datos.\n\n"
    "Vaya a Ajustes › Configuración FE_Py Recepción, sección «Licencia», para cargar o "
    "renovar el código. El «Código de la base» que FC_Py necesita para emitirlo "
    "está en esa misma pantalla."
)

_fe_py_recepcion_clave_publica_cache = None


def _fe_py_recepcion_obtener_clave_publica():
    global _fe_py_recepcion_clave_publica_cache
    if _fe_py_recepcion_clave_publica_cache is None:
        _fe_py_recepcion_clave_publica_cache = serialization.load_pem_public_key(
            FE_PY_RECEPCION_CLAVE_PUBLICA_PEM)
    return _fe_py_recepcion_clave_publica_cache


def _fe_py_recepcion_b64_decode(texto):
    relleno = '=' * (-len(texto) % 4)
    return base64.urlsafe_b64decode(texto + relleno)


def fe_py_recepcion_decodificar_licencia(codigo):
    """Valida la firma de un código de licencia y devuelve sus datos.

    Devuelve `{'uuid': ..., 'cliente': ..., 'vence': 'AAAA-MM-DD', 'version_odoo': int}`
    si el código es auténtico y corresponde a este módulo. Lanza `ValueError` (mensaje
    corto, para uso interno) si el formato, la codificación, la firma, el contenido
    o el producto no son válidos (por ejemplo, un código emitido para otro producto
    de FC_Py). No compara la versión de Odoo contra la instalada: eso lo hace quien
    llama (ver `res.company._compute_fe_py_recepcion_licencia`), que es quien sabe
    cuál es la versión realmente instalada.
    """
    if not codigo or not codigo.strip():
        raise ValueError("vacío")
    if not _FE_PY_RECEPCION_CRYPTO_DISPONIBLE:
        raise ValueError("sin_libreria")
    partes = codigo.strip().split('.')
    if len(partes) != 3 or partes[0] != FE_PY_RECEPCION_LICENCIA_PREFIJO:
        raise ValueError("formato")
    try:
        datos = _fe_py_recepcion_b64_decode(partes[1])
        firma = _fe_py_recepcion_b64_decode(partes[2])
    except Exception:
        raise ValueError("codificación")
    try:
        _fe_py_recepcion_obtener_clave_publica().verify(
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
    if payload['p'] != FE_PY_RECEPCION_LICENCIA_PRODUCTO:
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


def fe_py_recepcion_version_odoo_instalada():
    """Número central de la versión del módulo instalado, leído en vivo del manifest
    (el «19» de la versión «2026.19.006»). Devuelve None si no se puede determinar.

    Odoo normaliza la versión del manifest (`adapt_version`): una versión de tres
    partes como la de este módulo («AAAA.19.NNN») recibe antepuesta la serie de Odoo
    y queda expuesta como «19.0.AAAA.19.NNN»; en ese caso el número central es el
    anteúltimo segmento. Una versión que ya empieza con la serie de Odoo
    («19.0.AAAA.NNNN») queda tal cual y el número central es el primer segmento.
    Nunca se toma una posición fija desde el principio.
    """
    try:
        manifest = _fe_py_recepcion_odoo_module.get_manifest(FE_PY_RECEPCION_LICENCIA_PRODUCTO)
        version = str((manifest or {}).get('version') or '')
        partes = version.split('.')
        if len(partes) == 4 and '.'.join(partes[:2]) == release.major_version:
            return int(partes[0])
        if len(partes) >= 3:
            return int(partes[-2])
        return None
    except Exception:
        return None


def fe_py_recepcion_control_activo(env):
    """True si el control de licencia está en vigor en este contexto.

    Inactivo en un build de partner (`FE_PY_RECEPCION_LICENCIA_OBLIGATORIA = False`) y
    durante las pruebas automáticas (`current_test`, que Odoo deja asignado mientras
    corre cada caso de prueba), salvo que la propia prueba pida forzar el control con
    el contexto `fe_py_recepcion_licencia_forzar_test` (así se prueba el bloqueo sin
    tener que simular una licencia en el resto de las pruebas del módulo).
    """
    if not FE_PY_RECEPCION_LICENCIA_OBLIGATORIA:
        return False
    if _fe_py_recepcion_odoo_module.current_test and not env.context.get(
            'fe_py_recepcion_licencia_forzar_test'):
        return False
    return True


def fe_py_recepcion_licencia_exenta(env):
    """True si este `create`/`write` no debe verificar la licencia.

    Además de lo anterior, exento mientras se instala o actualiza el módulo (carga de
    datos iniciales, antes de que el registro quede listo), y en los pasos internos
    del sistema que marcan el contexto `fe_py_recepcion_licencia_omitir` (por ejemplo,
    el regreso de la recepción a Cargado al eliminar o cancelar su factura: no debe
    impedir trabajar con la contabilidad si la licencia venció).
    """
    if not fe_py_recepcion_control_activo(env):
        return True
    if env.context.get('fe_py_recepcion_licencia_omitir'):
        return True
    return not env.registry.ready


def fe_py_recepcion_licencia_verificar(env, company=None):
    """Lanza `UserError` si la compañía no tiene una licencia válida (salvo exención)."""
    if fe_py_recepcion_licencia_exenta(env):
        return
    company = company or env.company
    if not company._fe_py_recepcion_licencia_valida():
        raise UserError(FE_PY_RECEPCION_LICENCIA_MENSAJE)
