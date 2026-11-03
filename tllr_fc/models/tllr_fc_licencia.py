# -*- coding: utf-8 -*-
"""Control de licencia del módulo Taller (2026.19.032 / 2026.19.033 / 2026.19.034).

La licencia se emite fuera de este módulo, con una herramienta propia de FC_Py que
conserva la clave privada de firma (nunca viaja con el módulo). Este archivo solo
contiene la clave PÚBLICA, que permite VERIFICAR un código de licencia, nunca generar
uno nuevo: tenerla no alcanza para falsificar una licencia válida. La misma clave
firma las licencias de todos los productos de FC_Py (Taller, local_py, l10n_py); el
código de licencia identifica a qué producto corresponde (campo `p`), así que el
código de un producto no sirve para activar otro.

El código de licencia tiene el formato "TLLRFC1.<datos>.<firma>" (base64 URL-safe),
con los datos: producto (`p`, debe ser "tllr_fc"), identificador de la base de datos
(`database.uuid`), nombre del cliente, fecha de vencimiento y versión de Odoo
autorizada (`m`, desde 2026.19.034 — ver más abajo). `tllr_fc_decodificar_licencia`
lo valida.

Versión de Odoo autorizada (desde 2026.19.034): el código de licencia queda atado al
número central de la versión del módulo (el "19" de "2026.19.034"), no a la versión
completa. Mientras ese número no cambie, cualquier cantidad de correcciones o
ajustes menores (el último número) no afectan la licencia vigente. El día que el
módulo pase a estar preparado para otra versión de Odoo (ese número central cambia,
por ejemplo a "20"), cualquier código emitido para el número anterior deja de ser
válido (estado "otra_version") y hay que emitir uno nuevo — sin necesidad de ningún
paso manual adicional: la comparación es automática, cada vez que se calcula el
estado de la licencia, contra la versión realmente instalada.

`TLLR_FC_LICENCIA_OBLIGATORIA` es el interruptor para los builds que se entregan a un
partner con reventa ilimitada (contrato con código fuente): se deja en `False` al
armar su ZIP porque, para ese canal, el control pasa a ser enteramente contractual
(ver LICENSE y el contrato de partner) y no tiene sentido que sus clientes finales
dependan de que FC_Py les firme un código. En el build que FC_Py distribuye
directamente a sus propios clientes queda en `True`.
"""
import base64
import json

from odoo.exceptions import UserError
from odoo.modules import module as _tllr_fc_odoo_module

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    _TLLR_FC_CRYPTO_DISPONIBLE = True
except ImportError:  # pragma: no cover - entorno sin la librería `cryptography`
    _TLLR_FC_CRYPTO_DISPONIBLE = False

TLLR_FC_LICENCIA_PREFIJO = "TLLRFC1"
TLLR_FC_LICENCIA_PRODUCTO = "tllr_fc"

# Interruptor de build. `True`: build normal, con control de licencia (el que FC_Py
# entrega a sus clientes directos). `False`: build de partner con reventa ilimitada,
# sin control técnico (la protección queda en el contrato). Se cambia a mano al
# armar el ZIP de entrega a un partner; ver Guía de Desarrollo, sección 12.
TLLR_FC_LICENCIA_OBLIGATORIA = True

# Clave pública de verificación (FC_Py). Reemplazar junto con la clave privada
# si se regenera el par de claves (ver la Guía de Desarrollo, sección de licencias).
TLLR_FC_CLAVE_PUBLICA_PEM = b"""-----BEGIN PUBLIC KEY-----
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

TLLR_FC_LICENCIA_MENSAJE = (
    "El Taller no tiene una licencia válida para esta base de datos.\n\n"
    "Vayan a Taller › Configuración › Ajustes, sección «Licencia», para cargar o "
    "renovar el código. El «Código de la base» que FC_Py necesita para emitirlo "
    "está en esa misma pantalla."
)

_tllr_fc_clave_publica_cache = None


def _tllr_fc_obtener_clave_publica():
    global _tllr_fc_clave_publica_cache
    if _tllr_fc_clave_publica_cache is None:
        _tllr_fc_clave_publica_cache = serialization.load_pem_public_key(
            TLLR_FC_CLAVE_PUBLICA_PEM)
    return _tllr_fc_clave_publica_cache


def _tllr_fc_b64_decode(texto):
    relleno = '=' * (-len(texto) % 4)
    return base64.urlsafe_b64decode(texto + relleno)


def tllr_fc_decodificar_licencia(codigo):
    """Valida la firma de un código de licencia y devuelve sus datos.

    Devuelve `{'uuid': ..., 'cliente': ..., 'vence': 'AAAA-MM-DD', 'version_odoo': int}`
    si el código es auténtico y corresponde al Taller. Lanza `ValueError` (mensaje
    corto, para uso interno) si el formato, la codificación, la firma, el contenido
    o el producto no son válidos (por ejemplo, un código emitido para otro producto
    de FC_Py). No compara la versión de Odoo contra la instalada: eso lo hace quien
    llama (ver `res.company._compute_tllr_fc_licencia`), que es quien sabe cuál es
    la versión realmente instalada.
    """
    if not codigo or not codigo.strip():
        raise ValueError("vacío")
    if not _TLLR_FC_CRYPTO_DISPONIBLE:
        raise ValueError("sin_libreria")
    partes = codigo.strip().split('.')
    if len(partes) != 3 or partes[0] != TLLR_FC_LICENCIA_PREFIJO:
        raise ValueError("formato")
    try:
        datos_bytes = _tllr_fc_b64_decode(partes[1])
        firma_bytes = _tllr_fc_b64_decode(partes[2])
    except Exception:
        raise ValueError("codificación")
    try:
        _tllr_fc_obtener_clave_publica().verify(
            firma_bytes, datos_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256())
    except InvalidSignature:
        raise ValueError("firma")
    try:
        datos = json.loads(datos_bytes.decode('utf-8'))
    except Exception:
        raise ValueError("contenido")
    if not isinstance(datos, dict) or not all(k in datos for k in ('p', 'u', 'c', 'v', 'm')):
        raise ValueError("contenido")
    if datos['p'] != TLLR_FC_LICENCIA_PRODUCTO:
        raise ValueError("otro_producto")
    return {
        'uuid': datos['u'], 'cliente': datos['c'], 'vence': datos['v'],
        'version_odoo': datos['m'],
    }


def tllr_fc_version_odoo_instalada():
    """Número central de la versión del módulo instalado (ej. 19 en "2026.19.034").

    Se lee del manifest del módulo instalado, no de una constante aparte: así no
    hay que acordarse de actualizar dos lugares distintos el día que el módulo pase
    a estar preparado para otra versión de Odoo. Devuelve `None` si no se puede
    determinar (no debería pasar en un módulo instalado correctamente).
    """
    try:
        manifest = _tllr_fc_odoo_module.get_manifest('tllr_fc')
        version = str((manifest or {}).get('version') or '')
        return int(version.split('.')[1])
    except Exception:
        return None


def tllr_fc_licencia_exenta(env):
    """True si este `create`/`write` no debe verificar la licencia.

    Exento en un build de partner (`TLLR_FC_LICENCIA_OBLIGATORIA = False`), mientras
    se instala o actualiza el módulo (carga de datos iniciales, antes de que el
    registro quede listo) y durante las pruebas automáticas (`current_test`, que
    Odoo deja asignado mientras corre cada caso de prueba, desde su `setUpClass`),
    salvo que la propia prueba pida forzar el control con el contexto
    `tllr_fc_licencia_forzar_test` (así se prueba el bloqueo sin tener que simular una
    licencia en el resto de las pruebas del módulo).
    """
    if not TLLR_FC_LICENCIA_OBLIGATORIA:
        return True
    registry = env.registry
    if not registry.ready:
        return True
    if _tllr_fc_odoo_module.current_test and not env.context.get('tllr_fc_licencia_forzar_test'):
        return True
    return False


def tllr_fc_licencia_verificar(env, company):
    """Lanza `UserError` si la compañía no tiene una licencia válida (salvo exención)."""
    if tllr_fc_licencia_exenta(env):
        return
    company = company or env.company
    if not company._tllr_fc_licencia_valida():
        raise UserError(TLLR_FC_LICENCIA_MENSAJE)
