# Almacén — sistema de inventario y ventas

MVP local para administrar productos, controlar stock y registrar ventas. La información del negocio se guarda en una base de datos SQLite.

## Ejecutar

Desde esta carpeta:

```powershell
python server.py
```

Luego abre `http://127.0.0.1:8000`.

En el primer acceso se configura el administrador. Los roles de vendedor e inventario
tienen permisos distintos; el administrador puede gestionarlos desde Usuarios.
El menú de la cuenta permite cerrar sesión y cambiar la contraseña, invalidando las
otras sesiones de esa cuenta.

## Verificación

Las pruebas de la API crean bases SQLite temporales y usan puertos disponibles
automáticamente, sin modificar `data/inventory.db`.

```powershell
python -m unittest discover -s tests -v
node --test tests/frontend.test.mjs
```

Cubren permisos, sesiones, validaciones, transacciones de inventario, archivos privados,
avisos en diálogos y escape de contenido. Las pruebas de interfaz usan un DOM simulado;
no sustituyen una comprobación visual en navegador.

## Funciones incluidas

- Panel con ventas del día, valor de inventario y alertas.
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

Los productos y las ventas se guardan en SQLite dentro de `data/inventory.db`. La base se crea automáticamente al iniciar el servidor e incluye productos de ejemplo solamente en su primera creación. Las preferencias visuales continúan guardándose en el navegador.

## Estructura

```text
src/
├── css/
│   ├── base.css          Variables y estilos globales
│   ├── layout.css        Estructura y grillas
│   ├── components.css    Componentes de la interfaz
│   ├── theme.css         Identidad visual y ajustes de estilo
│   ├── accessibility.css Modos visuales y panel de accesibilidad
│   └── responsive.css    Adaptación a tablet y teléfono
└── js/
    ├── app.js            Eventos y coordinación de la interfaz
    ├── config.js         Configuración compartida
    ├── data/             Datos iniciales y persistencia
    ├── ui/               Renderizado y notificaciones
    └── utils/            Funciones de formato reutilizables
```
