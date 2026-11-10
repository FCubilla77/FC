# Licencia de FE_Py Recepción de Facturas (2026.19.012)

Licencia **OPL-1** (Odoo Proprietary License v1.0). Ver `LICENSE`. Una sola licencia
cubre `fe_py_recepcion` y su puente `fe_py_recepcion_purchase`.

## Código de licencia
- Formato: `FC_PY1.<datos en base64url>.<firma en base64url>`. El prefijo `FC_PY1` es el
  mismo en todos los productos de FC_Py; el producto se identifica con el campo `p`.
- Datos (JSON): `p` = `fe_py_recepcion`, `u` = `database.uuid` de la base, `c` = cliente,
  `v` = vencimiento (ISO) y `m` = número central de la versión (el «19» de `2026.19.012`).
- Firma RSA-PSS / SHA-256 con clave de 3072 bits. El módulo solo contiene la clave pública
  (`models/fe_py_recepcion_licencia.py`), la misma de todos los productos de FC_Py.

## Estados (Ajustes › Configuración FE_Py Recepción › Licencia)
| Estado | Significado |
|---|---|
| Sin licencia | No se cargó ningún código. |
| Válida | Firma correcta, producto y base de datos correctos, versión vigente y sin vencer. |
| Vencida | La fecha de vencimiento ya pasó. |
| Inválida | Firma, formato o contenido incorrectos, o emitido para otra base o producto. |
| Otra versión | El código es para otro número central de versión; hay que pedir uno nuevo. |

El «Código de la base» tiene el formato `versión|uuid` (por ejemplo `19|3f9e…`) y es lo que
el cliente envía a FC_Py.

## Qué bloquea sin licencia válida
- **Crear**: equivalencias de productos del proveedor.
- **Crear y editar**: facturas electrónicas recibidas (cargar XML, verificar, confirmar,
  cancelar, reabrir), incluida la confirmación automática al cargar el XML y la lectura de la casilla de correo: sin licencia
  válida no se lee la casilla (los correos quedan sin leer, no se pierden).
- **Nunca**: lectura, líneas y cuotas, Ajustes, la factura de proveedor ya generada, la
  edición de una equivalencia ya creada, ni el regreso automático de la recepción a Cargado
  al eliminar o cancelar su factura.

## Exenciones
- Durante la instalación o actualización del módulo (`registry.ready` es falso).
- En las pruebas automáticas, salvo que la prueba fuerce el control con el contexto
  `fe_py_recepcion_licencia_forzar_test`.
- En los pasos internos que marcan el contexto `fe_py_recepcion_licencia_omitir`.
- Build de partner: con `FE_PY_RECEPCION_LICENCIA_OBLIGATORIA = False` el control técnico
  se desactiva. Solo para partners con contrato de reventa ilimitada de código fuente;
  nunca en el build que FC_Py entrega a sus clientes.

## Cómo emitir un código (uso interno de FC_Py)
```
python3 generar_licencia.py --producto fe_py_recepcion \
    --codigo-base "19|<uuid>" --cliente "<nombre>" [--vence AAAA-MM-DD | --dias N]
```
El script separa la versión del uuid y firma ambos. Sin `--dias` ni `--vence` el
vencimiento queda en 1.000.000 de días: el límite real es la versión. El valor
`fe_py_recepcion` debe estar en la lista de productos válidos del script.

## Reglas
- La clave privada nunca viaja con el módulo ni se guarda en un repositorio.
- Modelo comercial por versión de Odoo, no por fecha: las correcciones (último número) no
  afectan la licencia; el cambio del número central (por ejemplo, 19 a 20) exige un
  código nuevo.

## Pruebas
- Sin Odoo: `python3 -I tests/test_licencia_sin_odoo.py -v`.
- Con Odoo: `tests/test_licencia.py` (estados de la compañía, bloqueos, maestro editable,
  interruptor de partner).
