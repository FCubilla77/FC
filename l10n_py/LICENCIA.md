# Licencia de l10n_py (OPL-1) — guía de activación y emisión

Módulo: `l10n_py` · Versión 2026.19.017 · © 2026 FC_Py

## 1. Qué se licencia
`l10n_py` se distribuye bajo **OPL-1** (ver `LICENSE`). Además del contrato, el módulo
incorpora un control técnico: sin una licencia vigente, emitida por FC_Py y atada a la
base de datos del cliente, **no se puede asignar el paquete fiscal Paraguay** ni crear o
editar Cierres de Ejercicio.

## 2. Activación (cliente)
1. Ir a **Ajustes › Configuración l10n_py › Licencia**.
2. Copiar el **Código de la base** (formato `versión|uuid`, ej. `19|3f9e…`) y enviarlo a FC_Py tal cual, sin separarlo.
3. Pegar el **Código de licencia** recibido y guardar. El estado debe pasar a *Válida*.
4. Recién entonces, en Contabilidad › Ajustes, seleccionar el paquete fiscal **Paraguay**: se cargan plan de cuentas, grupos, impuestos y cuentas predeterminadas.

## 3. Campos (res.company, prefijo `l10n_py_licencia_`)
| Campo | Tipo | Descripción |
|---|---|---|
| `uuid` | Char, calculado | `versión|uuid` de la base, con botón de copiar |
| `codigo` | Text | Único editable: el código pegado por el cliente |
| `cliente` / `vencimiento` | calculados | Extraídos del código |
| `estado` | Selection | `sin_licencia`, `valida`, `vencida`, `invalida`, `otra_version` |

## 4. Formato del código
`FC_PY1.<datos base64url>.<firma base64url>` — prefijo fijo y compartido por todos los
productos de FC_Py. Datos (JSON): `p` = `l10n_py`, `u` = `database.uuid`, `c` = cliente,
`v` = vencimiento ISO, `m` = número central de versión de Odoo (el «19» de `2026.19.017`; Odoo expone la
versión como `19.0.2026.19.017`, y se toma el anteúltimo segmento). Firma RSA-PSS/SHA-256 (3072 bits).
El módulo contiene solo la **clave pública**; la misma clave verifica todos los productos.

## 5. Qué se bloquea
- **Asignar el paquete fiscal `py`** (carga del plan de cuentas): mensaje de error si no hay licencia válida. Las cargas automáticas (instalación del módulo, alta de compañía) se omiten en silencio. Bases con el plan ya cargado no se vuelven a bloquear.
- **Crear y editar** `l10n_py.cierre_ejercicio` (documento de trabajo en curso).
- **Nunca se bloquea**: lectura, informes (Balance General), Ajustes, ni los modelos nativos de Odoo.

## 6. Exenciones
- Instalación/actualización del módulo (`registry.ready` falso).
- Pruebas automáticas, salvo contexto `l10n_py_licencia_forzar_test`.
- **Build de partner**: constante `L10N_PY_LICENCIA_OBLIGATORIA = False` en `models/l10n_py_licencia.py` desactiva el control. Solo para partners con contrato de reventa ilimitada con código fuente; nunca en el build que FC_Py entrega a sus clientes.

## 7. Emisión (uso interno FC_Py)
```
python generar_licencia.py --producto l10n_py --codigo-base "19|<uuid>" \
       --cliente "<nombre>" [--vence AAAA-MM-DD | --dias N]
```
- Producto válido: **`l10n_py`** (agregarlo a la lista de productos del script).
- Sin `--dias`/`--vence` el vencimiento es de 1.000.000 de días: el límite real es la versión de Odoo.
- Modelo comercial por **versión de Odoo**, no por fecha: el correlativo final (016, 017…) no afecta la licencia; si el número central cambia (ej. 20), los códigos anteriores pasan a *otra_version* y hay que emitir uno nuevo.
- La clave privada nunca se incluye en el módulo ni en repositorios.
