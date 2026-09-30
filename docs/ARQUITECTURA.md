# Documentación técnica

## Resumen

Almacén es una aplicación web local sin framework de frontend. El navegador
carga HTML, CSS y módulos JavaScript estáticos. `server.py` sirve esos archivos,
expone la API HTTP y guarda los datos del negocio en SQLite. La aplicación no
requiere servicios externos ni paquetes Python adicionales.

```text
Navegador
  ├── HTML de index.html, componentes y vistas
  ├── CSS de styles.css y src/css/
  └── Módulos de src/js/
          │ solicitudes HTTP y cookie de sesión
          ▼
      server.py ─── SQLite (data/inventory.db)
          └──────── backup_validation.py
```

El servidor se enlaza a `127.0.0.1` y por eso solo acepta conexiones del mismo
equipo. El puerto predeterminado es `8000`.

## Estructura del código

| Ruta | Responsabilidad |
| --- | --- |
| `index.html` | Documento base y carga de la aplicación. |
| `styles.css`, `src/css/` | Importación de estilos, diseño, componentes, temas, accesibilidad, iconos y adaptación a pantallas. |
| `src/components/` | Estructura común, formularios, diálogos, acceso y avisos. |
| `src/views/` | Contenido HTML de cada pantalla. |
| `src/js/app.js` | Inicio, navegación, eventos, permisos visuales, formularios y exportaciones. |
| `src/js/auth.js` | Sesión de la interfaz, inicio y cierre de sesión, cambio de contraseña. |
| `src/js/data/store.js` | Solicitudes de datos y actualización del estado local de la interfaz. |
| `src/js/ui/` | Renderizado, carga de vistas, iconos, accesibilidad y notificaciones. |
| `src/js/utils/` | Cliente HTTP, formato, CSV, lectura de respaldos y cálculo de reportes. |
| `src/js/vendor/` | Selección local de iconos Lucide y su licencia. |
| `server.py` | Servidor HTTP, esquema SQLite, autenticación, permisos y operaciones del negocio. |
| `backup_validation.py` | Validación del formato y consistencia de respaldos JSON. |
| `tests/` | Pruebas de API, autenticación, exportaciones, reportes e iconos. |

`src/js/ui/views.js` carga los componentes y las vistas HTML. `src/js/app.js`
coordina el inicio, inicializa preferencias y autenticación, y enlaza las
acciones con `src/js/data/store.js`. El módulo de datos envía las operaciones a
la API; el estado en memoria se vuelve a cargar desde SQLite después de cada
escritura.

## Persistencia y entidades

La ruta por defecto de la base es `data/inventory.db`. Puede cambiarse con la
variable de entorno `INVENTORY_DB`. Al iniciar, el servidor crea el esquema si
no existe. Los productos de ejemplo se insertan solo en la creación inicial de
la tabla de productos.

Las principales tablas son:

| Tabla | Contenido |
| --- | --- |
| `products` | Catálogo y existencias actuales. |
| `sales`, `sale_items` | Ventas, folios, totales y detalle vendido. |
| `purchases`, `purchase_items` | Compras a proveedores y costo unitario recibido. |
| `suppliers` | Datos de contacto de proveedores. |
| `inventory_movements` | Historial de cambios de stock con motivo y responsable. |
| `users`, `sessions` | Cuentas, hashes de contraseñas y sesiones. |

Las escrituras de ventas, compras, movimientos y restauraciones usan transacciones
para mantener coordinados el historial y las existencias. El servidor vuelve a
validar cantidades, permisos y disponibilidad; las comprobaciones del navegador
no son la autoridad para aceptar una operación.

## API y permisos

La API usa JSON. La sesión se identifica mediante una cookie HTTP y el servidor
comprueba el rol antes de permitir acciones. Rutas principales:

| Método y ruta | Acción | Acceso |
| --- | --- | --- |
| `GET /api/auth/status` | Estado de autenticación y usuario actual. | Público / sesión actual |
| `POST /api/auth/setup` | Configurar el primer administrador. | Solo cuando aún no hay cuentas |
| `POST /api/auth/login`, `POST /api/auth/logout` | Iniciar o cerrar sesión. | Público / sesión actual |
| `POST /api/auth/password` | Cambiar contraseña. | Usuario autenticado |
| `GET /api/state` | Obtener los datos del negocio. | Usuario autenticado; datos reducidos para vendedor |
| `POST /api/products`, `DELETE /api/products/{id}` | Crear, editar o eliminar producto. | Administrador e inventario |
| `POST /api/sales` | Registrar venta. | Administrador y vendedor |
| `POST /api/movements` | Registrar movimiento de stock. | Administrador e inventario |
| `POST /api/suppliers`, `DELETE /api/suppliers/{id}` | Gestionar proveedores. | Administrador e inventario |
| `POST /api/purchases` | Registrar recepción de compra. | Administrador e inventario |
| `GET /api/users`, `POST /api/users` | Consultar y gestionar cuentas. | Administrador |
| `GET /api/backup` | Exportar respaldo JSON. | Administrador |
| `POST /api/backup/restore` | Validar e importar respaldo JSON. | Administrador |

El vendedor no recibe compras, proveedores ni movimientos, y los reportes y CSV
ocultan los costos y la ganancia estimada para ese rol.

## Estimación de costo y ganancia

`src/js/utils/reports.js` reconstruye costos recorriendo cronológicamente las
compras, ventas y movimientos de inventario. Las compras agregan unidades al
inventario conocido y actualizan su costo promedio móvil. Las ventas descuentan
existencias al promedio disponible en ese momento.

El stock inicial y las entradas o devoluciones sin costo quedan como unidades
desconocidas. Al descontar stock, estas unidades se consumen antes que las
conocidas; cualquier venta que incluya unidades desconocidas se separa de la
ganancia calculable. Cuando se agotan, el costo promedio vuelve a calcularse con
las existencias cuyo costo sí está documentado.

Es una estimación de costo de mercadería vendida. No considera gastos generales,
impuestos, devoluciones con valoración propia ni diferencias entre el orden
físico de salida y el supuesto del cálculo. Conviene registrar las recepciones y
los costos con precisión para obtener resultados más completos.

## Respaldo y recuperación

El respaldo JSON contiene las colecciones del negocio, pero excluye las cuentas,
contraseñas, sesiones y preferencias del navegador. `backup_validation.py`
comprueba el formato, cantidades, fechas, folios, totales, referencias y balance
entre movimientos y stock antes de iniciar la restauración.

Antes de reemplazar los datos, `snapshot_database()` genera una copia consistente
de SQLite en una carpeta `backups` junto a la base configurada. Mantiene hasta
10 copias y elimina las que tengan más de 90 días. Si la restauración JSON falla,
la transacción mantiene los datos de negocio anteriores. Para una recuperación
manual desde un snapshot SQLite, detén el servidor antes de reemplazar la base.

## Configuración

| Variable | Predeterminado | Uso |
| --- | --- | --- |
| `INVENTORY_DB` | `data/inventory.db` | Ruta del archivo SQLite. |
| `INVENTORY_PORT` | `8000` | Puerto local HTTP. |

Ejemplo PowerShell:

```powershell
$env:INVENTORY_DB = "C:\Datos\almacen.db"
$env:INVENTORY_PORT = "8080"
python server.py
```

La base y la carpeta `backups` pueden contener información comercial y de
cuentas; deben incluirse en las políticas de protección del equipo donde corre
la aplicación. El servidor local actual no implementa despliegue multiusuario
por red, HTTPS ni alojamiento público.
