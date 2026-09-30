# Almacén — sistema de inventario y ventas

MVP local para administrar productos, controlar stock y registrar ventas. La información del negocio se guarda en una base de datos SQLite.

## Ejecutar

Desde esta carpeta:

```powershell
python server.py
```

Luego abre `http://127.0.0.1:8000`.

Para instalación, uso de cada módulo, roles y recuperación de respaldos, consulta
la [guía de usuario](docs/USO.md). La estructura del código, el modelo de datos,
los permisos de API y las decisiones del cálculo de costos están descritos en la
[documentación técnica](docs/ARQUITECTURA.md).

En el primer acceso se configura el administrador. Los roles de vendedor e inventario
tienen permisos distintos; el administrador puede gestionarlos desde Usuarios.
El menú de la cuenta permite cerrar sesión y cambiar la contraseña, invalidando las
otras sesiones de esa cuenta.

## Verificación

Las pruebas de la API crean bases SQLite temporales y usan puertos disponibles
automáticamente, sin modificar `data/inventory.db`.

```powershell
python -m unittest discover -s tests -v
node --test tests/frontend.test.mjs tests/icons.test.mjs tests/reports.test.mjs tests/navigation.test.mjs
```

Cubren permisos, sesiones, validaciones, transacciones de inventario, archivos privados,
avisos en diálogos y escape de contenido. Las pruebas de interfaz usan un DOM simulado;
no sustituyen una comprobación visual en navegador.

## Funciones incluidas

- Panel con ventas del día, valor de inventario y alertas.
- Reportes por periodo con ventas, ingresos, ticket promedio y productos más vendidos.
- Estimación de ganancias según compras anteriores a cada venta, indicando los costos desconocidos.
- Exportación de ventas e inventario a CSV y respaldo de los datos del negocio en JSON.
- Restauración de respaldos JSON disponible para administradores.
- Alertas automáticas y visibles para productos bajo el stock mínimo.
- Alta, edición, búsqueda, filtrado y eliminación de productos.
- Punto de venta con carrito y control de existencias.
- Descuento automático de stock al completar una venta.
- Historial de ventas y resumen de los últimos siete días.
- Historial de entradas, ventas, devoluciones, pérdidas y ajustes de stock.
- Proveedores y recepción de compras con actualización automática de existencias.
- Inicio de sesión, sesiones seguras y roles de administrador, vendedor e inventario.
- Diseño adaptable a escritorio y teléfono.
- Modo oscuro, contraste alto, texto ampliado y lector de pantalla integrado.

## Datos

Los administradores pueden descargar y restaurar respaldos desde Reportes.
El servidor comprueba colecciones, fechas, cantidades, totales, referencias y
existencias antes de reemplazar los datos en una transacción. Las cuentas,
contraseñas y preferencias no se incluyen ni se reemplazan. Los respaldos
anteriores completos siguen siendo compatibles, incluso si contienen BOM.
Antes de cada restauración válida, el servidor guarda una copia SQLite de la
base actual en `data/backups/` (o junto a la ruta configurada en `INVENTORY_DB`).
Se conservan como máximo las 10 copias más recientes y se eliminan las que
tengan más de 90 días.

La ganancia es una estimación con promedio móvil: cada compra actualiza el costo
de las existencias conocidas y cada venta lo descuenta. El inventario inicial,
las entradas y devoluciones sin costo quedan marcados como desconocidos; una
venta no recibe costo conocido hasta que esas unidades se hayan agotado.
Los productos sin costo conocido se muestran por separado. No incluye gastos
ni ajustes por devoluciones; los vendedores no ven costos ni ganancias.

Los productos y las ventas se guardan en SQLite dentro de `data/inventory.db`. La base se crea automáticamente al iniciar el servidor e incluye productos de ejemplo solamente en su primera creación. Las preferencias visuales continúan guardándose en el navegador.

## Estructura

La interfaz utiliza una selección local de iconos [Lucide](https://lucide.dev/)
(versión 0.468.0, licencia ISC). Los SVG se incluyen en
`src/js/vendor/lucide.js` y la licencia en `src/js/vendor/lucide-LICENSE.txt`.
No se requiere conexión a un CDN. Para usar un icono en HTML, escribe
`<span data-icon="package"></span>`; para contenido dinámico, utiliza
`icon("package")` desde `src/js/ui/icons.js`.

```text
server.py                 Servidor HTTP, API y SQLite
backup_validation.py      Validación de respaldos JSON
docs/
├── USO.md                Instalación, operación y ayuda para usuarios
└── ARQUITECTURA.md       Módulos, datos, API y decisiones técnicas
src/
├── components/         Layout, diálogos, autenticación y avisos
├── views/              Vistas HTML independientes
├── css/
│   ├── base.css, layout.css, components.css
│   ├── theme.css, accessibility.css, responsive.css
│   ├── icons.css
│   └── brand.css          Acabado visual del sistema
└── js/
    ├── app.js, auth.js, config.js
    ├── data/             Acceso a la API y estado de interfaz
    ├── ui/               Vistas, renderizado, iconos y accesibilidad
    ├── utils/            API, formato, exportaciones y reportes
    └── vendor/           Iconos Lucide locales
tests/                    Pruebas de API y JavaScript
```
