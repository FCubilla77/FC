# -*- coding: utf-8 -*-
"""Control de licencia del módulo Paraguay - Contabilidad (l10n_py), versión 2026.19.019.

La licencia se emite fuera de este módulo, con una herramienta propia de FC_Py que
conserva la clave privada de firma (nunca viaja con el módulo). Este archivo solo
contiene la clave PÚBLICA, que permite VERIFICAR un código de licencia, nunca generar
uno nuevo: tenerla no alcanza para falsificar una licencia válida. La misma clave
firma las licencias de todos los productos de FC_Py (Taller, local_py, l10n_py); el
código de licencia identifica a qué producto corresponde (campo `p`), así que el
código de un producto no sirve para activar otro. Este módulo es autosuficiente: no
importa nada de otros módulos de FC_Py ni requiere que estén instalados.

El código de licencia tiene el formato "FC_PY1.<datos>.<firma>" (base64 URL-safe),
con los datos: producto (`p`, debe ser "l10n_py"), identificador de la base de datos
(`database.uuid`), nombre del cliente, fecha de vencimiento y versión de Odoo
autorizada (`m`). `l10n_py_decodificar_licencia` lo valida.

Versión de Odoo autorizada: el código queda atado al número central de la versión
del módulo (el "19" de "2026.19.019"), no a la versión completa. Mientras ese
número no cambie, cualquier cantidad de correcciones o ajustes menores no afectan la
licencia vigente. Si el módulo pasa a otra versión de Odoo, el código emitido para la
anterior queda en estado "otra_version" y hay que pedir uno nuevo, sin ningún paso
manual adicional.

Qué bloquea la licencia (ver también models/chart_template_licencia.py y
models/licencia_mixin.py):
  * La asignación del paquete fiscal "py" (account.chart.template.try_loading).
  * La creación y edición de Cierres de Ejercicio (l10n_py.cierre_ejercicio).
Nunca bloquea: lectura, informes (Balance General), la pantalla de Ajustes, ni los
modelos nativos de Odoo (cuentas, grupos, impuestos, asientos).

`L10N_PY_LICENCIA_OBLIGATORIA` es el interruptor para los builds que se entregan a un
partner con reventa ilimitada (contrato con código fuente): se deja en `False` al
armar su ZIP porque, para ese canal, el control pasa a ser enteramente contractual
(ver LICENSE y el contrato de partner). En el build que FC_Py distribuye directamente
a sus propios clientes queda en `True`.
"""
import base64
import json
from datetime import date

from odoo.exceptions import UserError
from odoo.modules import module as _l10n_py_odoo_module

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    _L10N_PY_CRYPTO_DISPONIBLE = True
except ImportError:  # pragma: no cover - entorno sin la librería `cryptography`
    _L10N_PY_CRYPTO_DISPONIBLE = False

L10N_PY_LICENCIA_PREFIJO = "FC_PY1"
L10N_PY_LICENCIA_PRODUCTO = "l10n_py"
L10N_PY_CODIGO_PAQUETE_FISCAL = "py"

# Interruptor de build. `True`: build normal, con control de licencia (el que FC_Py
# entrega a sus clientes directos). `False`: build de partner con reventa ilimitada,
# sin control técnico (la protección queda en el contrato). Se cambia a mano al
# armar el ZIP de entrega a un partner.
L10N_PY_LICENCIA_OBLIGATORIA = True

# Clave pública de verificación (FC_Py), la misma para todos los productos. Reemplazar
# junto con la clave privada si se regenera el par de claves.
L10N_PY_CLAVE_PUBLICA_PEM = b"""-----BEGIN PUBLIC KEY-----
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

L10N_PY_LICENCIA_MENSAJE = (
    "Paraguay - Contabilidad (l10n_py) no tiene una licencia válida para esta base "
    "de datos.\n\n"
    "Vaya a Ajustes › Configuración l10n_py, sección «Licencia», para cargar o "
    "renovar el código. El «Código de la base» que FC_Py necesita para emitirlo "
    "está en esa misma pantalla. Una vez cargada una licencia válida podrá asignar "
    "el paquete fiscal Paraguay."
)

_l10n_py_clave_publica_cache = None


def _l10n_py_obtener_clave_publica():
    global _l10n_py_clave_publica_cache
    if _l10n_py_clave_publica_cache is None:
        _l10n_py_clave_publica_cache = serialization.load_pem_public_key(
            L10N_PY_CLAVE_PUBLICA_PEM)
    return _l10n_py_clave_publica_cache


def _l10n_py_b64_decode(texto):
    relleno = '=' * (-len(texto) % 4)
    return base64.urlsafe_b64decode(texto + relleno)


def l10n_py_decodificar_licencia(codigo):
    """Valida la firma de un código de licencia y devuelve sus datos.

    Devuelve `{'uuid': ..., 'cliente': ..., 'vence': 'AAAA-MM-DD', 'version_odoo': int}`
    si el código es auténtico y corresponde a l10n_py. Lanza `ValueError` (mensaje
    corto, para uso interno) si el formato, la codificación, la firma, el contenido
    o el producto no son válidos (por ejemplo, un código emitido para otro producto
    de FC_Py). No compara la versión de Odoo contra la instalada: eso lo hace quien
    llama (ver `res.company._compute_l10n_py_licencia`), que es quien sabe cuál es
    la versión realmente instalada.
    """
    if not codigo or not codigo.strip():
        raise ValueError("vacío")
    if not _L10N_PY_CRYPTO_DISPONIBLE:
        raise ValueError("sin_libreria")
    partes = codigo.strip().split('.')
    if len(partes) != 3 or partes[0] != L10N_PY_LICENCIA_PREFIJO:
        raise ValueError("formato")
    try:
        datos = _l10n_py_b64_decode(partes[1])
        firma = _l10n_py_b64_decode(partes[2])
    except Exception:
        raise ValueError("codificación")
    try:
        _l10n_py_obtener_clave_publica().verify(
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
    if payload['p'] != L10N_PY_LICENCIA_PRODUCTO:
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


def l10n_py_version_odoo_instalada():
    """Número central de la versión del módulo instalado (el «19» de «2026.19.019»),
    leído en vivo del manifest. Devuelve None si no se puede determinar.

    OJO: `get_manifest` no devuelve el string tal cual se escribió. Odoo le antepone
    su propia serie (`adapt_version`, en odoo/modules/module.py): «2026.19.019» se
    expone como «19.0.2026.19.019». Por eso se toma el anteúltimo segmento (año,
    número central y correlativo son siempre los últimos tres), nunca una posición
    fija desde el principio del string.
    """
    try:
        manifest = _l10n_py_odoo_module.get_manifest(L10N_PY_LICENCIA_PRODUCTO)
        version = str((manifest or {}).get('version') or '')
        partes = version.split('.')
        if len(partes) < 3:
            return None
        return int(partes[-2])
    except Exception:
        return None


def l10n_py_control_activo(env):
    """True si el control de licencia está en vigor en este contexto.

    Inactivo en un build de partner (`L10N_PY_LICENCIA_OBLIGATORIA = False`) y durante
    las pruebas automáticas (`current_test`, que Odoo deja asignado mientras corre
    cada caso de prueba), salvo que la propia prueba pida forzar el control con el
    contexto `l10n_py_licencia_forzar_test` (así se prueba el bloqueo sin tener que
    simular una licencia en el resto de las pruebas del módulo).
    """
    if not L10N_PY_LICENCIA_OBLIGATORIA:
        return False
    if _l10n_py_odoo_module.current_test and not env.context.get('l10n_py_licencia_forzar_test'):
        return False
    return True


def l10n_py_licencia_exenta(env):
    """True si este `create`/`write` no debe verificar la licencia.

    Además de lo anterior, exento mientras se instala o actualiza el módulo (carga de
    datos iniciales, antes de que el registro quede listo): sin esto, la propia carga
    de datos del módulo fallaría.
    """
    if not l10n_py_control_activo(env):
        return True
    return not env.registry.ready


def l10n_py_licencia_verificar(env, company=None):
    """Lanza `UserError` si la compañía no tiene una licencia válida (salvo exención)."""
    if l10n_py_licencia_exenta(env):
        return
    company = company or env.company
    if not company._l10n_py_licencia_valida():
        raise UserError(L10N_PY_LICENCIA_MENSAJE)
