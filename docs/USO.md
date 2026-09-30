# Guía de uso

## Requisitos e inicio

Se necesita Python instalado. El servidor utiliza únicamente módulos incluidos
con Python; no hace falta instalar paquetes externos.

En Windows, abre PowerShell en la carpeta del proyecto y ejecuta:

```powershell
python server.py
```

Abre `http://127.0.0.1:8000` en el navegador. La primera vez, crea la cuenta de
administrador. Para apagar el servidor, vuelve a PowerShell y presiona `Ctrl+C`.

La aplicación escucha solo en el equipo local. Para acceder desde otros equipos
se necesita preparar y proteger una instalación de servidor; no basta con
cambiar la dirección que se abre en el navegador.

## Cuentas y permisos

El administrador crea y activa cuentas desde **Usuarios**. Cada cuenta tiene uno
de estos roles:

| Rol | Permisos principales |
| --- | --- |
| Administrador | Acceso completo, usuarios, reportes, exportaciones y respaldos. |
| Inventario | Productos, movimientos, proveedores y compras. |
| Vendedor | Punto de venta e historial de ventas; no puede consultar costos ni ganancias. |

El menú de cuenta permite cambiar la contraseña y cerrar sesión. Al cambiar la
contraseña, las otras sesiones de esa cuenta se invalidan. La cuenta propia y el
último administrador activo están protegidos contra desactivación.

En escritorio, usa el control junto al menú para contraer o expandir la barra
lateral. La selección se recuerda en ese navegador. En móvil la navegación se
muestra en la franja inferior.

## Operación diaria

1. En **Productos**, crea cada artículo con nombre, SKU, categoría, precio de
   venta y stock mínimo. El stock se gestiona con movimientos y compras, no al
   editar los datos del producto.
2. En **Abastecer**, registra proveedores y recepciones. Agrega productos,
   cantidades y costo unitario. La recepción aumenta el inventario.
3. En **Vender**, agrega productos al carrito, ajusta cantidades y registra la
   venta. El servidor valida las existencias y descuenta el stock al confirmar.
4. En **Movimientos**, registra entradas, devoluciones, pérdidas o ajustes que
   no correspondan a una compra o venta. Escribe un motivo para mantener el
   historial entendible.
5. Usa **Inicio**, **Historial** y **Reportes** para revisar alertas, actividad y
   resultados. Los reportes se pueden filtrar por periodo.

Las alertas de reposición se activan cuando el stock es igual o inferior al
mínimo configurado para el producto.

## Exportaciones y respaldos

En **Reportes**, los botones de exportación descargan ventas e inventario como
CSV. El respaldo general se descarga como JSON e incluye productos, ventas,
compras, proveedores y movimientos. No incluye cuentas de usuario, contraseñas
ni preferencias visuales.

Solo el administrador puede importar un respaldo. La importación reemplaza los
datos actuales del negocio, conserva las cuentas de usuario y preferencias y
valida el archivo antes de modificar la base. Antes de completar una restauración
válida, el servidor guarda una copia SQLite de la base actual.

Las copias automáticas se guardan en `data/backups/` junto a la base (si se usa
`INVENTORY_DB`, se guardan en la carpeta `backups` junto a esa base). La política
conserva como máximo las 10 más recientes y elimina las que superen 90 días.
Para recuperar manualmente una de estas copias, detén el servidor y reemplaza la
base configurada con el archivo `.db` elegido; luego inicia el servidor de nuevo.
Haz una copia del archivo actual antes de reemplazarlo.

## Accesibilidad y apariencia

El selector **Modo oscuro** está en la barra lateral. El panel **Accesibilidad**
permite activar alto contraste, texto ampliado y movimiento reducido. También
incluye lectura de pantalla mediante las voces disponibles en el navegador y
controles para elegir voz y velocidad. La disponibilidad de voces depende del
sistema operativo y del navegador. Las preferencias visuales se guardan en ese
navegador.

## Pruebas

Para ejecutar las pruebas automatizadas, abre una segunda terminal en la carpeta
del proyecto:

```powershell
python -m unittest discover -s tests -v
node --test tests/frontend.test.mjs tests/icons.test.mjs tests/reports.test.mjs tests/navigation.test.mjs
```

Las pruebas de Python usan una base temporal. Las de JavaScript prueban utilidades
y componentes con un DOM simulado; ninguna sustituye una revisión visual de la
interfaz en navegadores y tamaños de pantalla reales.
