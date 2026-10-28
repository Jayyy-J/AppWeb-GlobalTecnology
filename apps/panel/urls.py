from django.urls import path

from .views import categorias, clientes, contenido, dashboard, envios, pedidos, productos, reportes

app_name = "panel"
urlpatterns = [
    path("", dashboard.dashboard, name="dashboard"),
    # Productos
    path("productos/", productos.lista, name="productos"),
    path("productos/acciones/", productos.acciones, name="productos_acciones"),
    path("productos/nuevo/", productos.formulario, name="producto_nuevo"),
    path("productos/<int:pk>/editar/", productos.formulario, name="producto_editar"),
    path("productos/<int:pk>/duplicar/", productos.duplicar, name="producto_duplicar"),
    path("productos/<int:pk>/eliminar/", productos.eliminar, name="producto_eliminar"),
    path("productos/<int:pk>/imagenes/", productos.imagenes_subir, name="imagenes_subir"),
    path("productos/<int:pk>/imagenes/orden/", productos.imagenes_orden, name="imagenes_orden"),
    path("imagenes/<int:img_id>/principal/", productos.imagen_principal, name="imagen_principal"),
    path("imagenes/<int:img_id>/eliminar/", productos.imagen_eliminar, name="imagen_eliminar"),
    path("imagenes/<int:img_id>/alt/", productos.imagen_alt, name="imagen_alt"),
    # Categorías y marcas
    path("categorias/", categorias.lista, name="categorias"),
    path("categorias/orden/", categorias.ordenar, name="categorias_orden"),
    path("categorias/nueva/", categorias.formulario, name="categoria_nueva"),
    path("categorias/<int:pk>/editar/", categorias.formulario, name="categoria_editar"),
    path("categorias/<int:pk>/eliminar/", categorias.eliminar, name="categoria_eliminar"),
    path("categorias/<int:pk>/productos/", categorias.productos, name="categoria_productos"),
    path("marcas/", categorias.marcas, name="marcas"),
    path("marcas/nueva/", categorias.marca_form, name="marca_nueva"),
    path("marcas/<int:pk>/editar/", categorias.marca_form, name="marca_editar"),
    path("marcas/<int:pk>/eliminar/", categorias.marca_eliminar, name="marca_eliminar"),
    # Pedidos
    path("pedidos/", pedidos.lista, name="pedidos"),
    path("pedidos/<str:numero>/", pedidos.detalle, name="pedido"),
    path("pedidos/<str:numero>/estado/", pedidos.cambiar_estado, name="pedido_estado"),
    path("pedidos/<str:numero>/cotizar/", pedidos.cotizar, name="pedido_cotizar"),
    path("pedidos/<str:numero>/notas/", pedidos.notas, name="pedido_notas"),
    path("pedidos/<str:numero>/rotulo/", pedidos.rotulo, name="pedido_rotulo"),
    # Envíos
    path("envios/", envios.envios, name="envios"),
    path("envios/tarifas/nueva/", envios.tarifa_form, name="tarifa_nueva"),
    path("envios/tarifas/<int:pk>/editar/", envios.tarifa_form, name="tarifa_editar"),
    path("envios/tarifas/<int:pk>/eliminar/", envios.tarifa_eliminar, name="tarifa_eliminar"),
    path("envios/tarifas/importar/", envios.tarifas_importar, name="tarifas_importar"),
    # Clientes
    path("clientes/", clientes.lista, name="clientes"),
    path("clientes/<int:pk>/", clientes.detalle, name="cliente"),
    path("clientes/<int:pk>/activar/", clientes.activar, name="cliente_activar"),
    path("clientes/<int:pk>/staff/", clientes.staff, name="cliente_staff"),
    # Contenido
    path("contenido/tienda/", contenido.tienda, name="tienda"),
    path("contenido/banners/", contenido.banners, name="banners"),
    path("contenido/banners/nuevo/", contenido.banner_form, name="banner_nuevo"),
    path("contenido/banners/<int:pk>/editar/", contenido.banner_form, name="banner_editar"),
    path("contenido/banners/<int:pk>/eliminar/", contenido.banner_eliminar, name="banner_eliminar"),
    path("contenido/legales/", contenido.legales, name="legales"),
    path("contenido/legales/<int:pk>/editar/", contenido.legal_form, name="legal_editar"),
    # Reportes y auditoría
    path("reportes/", reportes.reportes, name="reportes"),
    path("auditoria/", reportes.auditoria, name="auditoria"),
]
