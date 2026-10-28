import pytest
from django.core import mail
from django.urls import reverse

from apps.accounts.models import User
from apps.core.templatetags.cop import format_cop, resaltar

pytestmark = pytest.mark.django_db


def test_formato_cop():
    assert format_cop(1299900) == "$1.299.900"
    assert format_cop(0) == "$0"
    assert format_cop(999) == "$999"
    assert format_cop(-15000) == "-$15.000"
    assert format_cop("abc") == ""


def test_resaltar_sin_tildes():
    html = resaltar("Portátil Lenovo", "portatil")
    assert "<mark>Portátil</mark>" in html


def test_registro_requiere_tratamiento_de_datos(client):
    datos = {
        "first_name": "Ana", "last_name": "Pérez", "email": "ana@test.co", "telefono": "3001112233",
        "password1": "Clave-segura-123", "password2": "Clave-segura-123",
    }
    r = client.post(reverse("accounts:registro"), datos)
    assert r.status_code == 200
    assert not User.objects.filter(email="ana@test.co").exists()

    datos["acepta_tratamiento_datos"] = "on"
    r = client.post(reverse("accounts:registro") + "?next=/carrito/", {**datos, "next": "/carrito/"})
    assert r.status_code == 302 and r.url == "/carrito/"
    u = User.objects.get(email="ana@test.co")
    assert u.acepta_tratamiento_datos and u.fecha_aceptacion_datos
    assert any("Bienvenido" in m.subject for m in mail.outbox)


def test_registro_no_redirige_a_dominio_externo(client):
    datos = {
        "first_name": "Ana", "last_name": "Pérez", "email": "ana2@test.co", "telefono": "3001112233",
        "password1": "Clave-segura-123", "password2": "Clave-segura-123", "acepta_tratamiento_datos": "on",
        "next": "https://malo.com/",
    }
    r = client.post(reverse("accounts:registro"), datos)
    assert r.status_code == 302 and r.url == "/"


def test_login_con_email_sin_mayusculas(client, cliente):
    r = client.post(reverse("accounts:login"), {"username": "CLIENTE@test.co", "password": "Clave-segura-123"})
    assert r.status_code == 302
    assert client.session.get("_auth_user_id") == str(cliente.pk)


def test_login_invalido_muestra_error(client, cliente):
    r = client.post(reverse("accounts:login"), {"username": "cliente@test.co", "password": "mala"})
    assert r.status_code == 200
    assert "incorrectos" in r.content.decode()


def test_recuperar_clave_envia_email(client, cliente):
    r = client.post(reverse("accounts:recuperar"), {"email": "cliente@test.co"})
    assert r.status_code == 302
    assert len(mail.outbox) == 1 and "/cuenta/recuperar/" in mail.outbox[0].alternatives[0][0]


def test_paginas_publicas(client):
    for url in ["/", "/cuenta/ingresar/", "/cuenta/registro/", "/robots.txt", "/salud/"]:
        assert client.get(url).status_code == 200, url
    assert client.get("/no-existe-xyz/").status_code == 404


def test_paginas_legales_creadas(client):
    from apps.storefront.models import LegalPage

    assert LegalPage.objects.count() == 4
    r = client.get(reverse("storefront:legal", args=["cambios-devoluciones-y-retracto"]))
    assert r.status_code == 200
    assert "Ley 1480" in r.content.decode() and "Borrador" in r.content.decode()


def test_media_publica_no_sirve_evidencias(client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    (tmp_path / "privado" / "evidencias").mkdir(parents=True)
    (tmp_path / "privado" / "evidencias" / "x.webp").write_bytes(b"x")
    (tmp_path / "productos").mkdir()
    (tmp_path / "productos" / "a.webp").write_bytes(b"x")
    assert client.get("/media/privado/evidencias/x.webp").status_code == 404
    assert client.get("/media/productos/../privado/evidencias/x.webp").status_code == 404
    r = client.get("/media/productos/a.webp")
    assert r.status_code == 200 and "max-age=31536000" in r["Cache-Control"]


def test_validacion_imagen_rechaza_archivo_falso():
    from django.core.exceptions import ValidationError
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core.images import validate_image_file

    falso = SimpleUploadedFile("virus.png", b"MZ\x90\x00 esto no es una imagen", content_type="image/png")
    with pytest.raises(ValidationError):
        validate_image_file(falso)


def test_validacion_imagen_peso_maximo(settings, imagen):
    from django.core.exceptions import ValidationError

    from apps.core.images import validate_image_file

    settings.MAX_UPLOAD_MB = 0
    with pytest.raises(ValidationError):
        validate_image_file(imagen())


def test_check_tunnel(settings, monkeypatch, capsys):
    from django.core.management import call_command

    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.tunnel")
    settings.SITE_URL = "https://abc123-8000.use2.devtunnels.ms"
    settings.ALLOWED_HOSTS = [".devtunnels.ms"]
    settings.CSRF_TRUSTED_ORIGINS = ["https://*.devtunnels.ms"]
    settings.SECURE_SSL_REDIRECT = False
    settings.SESSION_COOKIE_SECURE = settings.CSRF_COOKIE_SECURE = True
    call_command("check_tunnel")
    salida = capsys.readouterr().out
    assert "Todo listo" in salida
    settings.WOMPI_PUBLIC_KEY = "pub_prod_xxx"
    call_command("check_tunnel")
    assert "FALLA" in capsys.readouterr().out
