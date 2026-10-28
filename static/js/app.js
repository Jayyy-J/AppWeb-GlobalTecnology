/* GlobalTecnology — comportamiento del frontend (HTMX + Alpine.js, sin build) */
(function () {
  "use strict";

  // ---------- CSRF para peticiones HTMX (se lee de la cookie: sobrevive a la rotación al iniciar sesión) ----------
  function cookie(nombre) {
    var m = document.cookie.match("(^|;)\\s*" + nombre + "\\s*=\\s*([^;]+)");
    return m ? decodeURIComponent(m.pop()) : "";
  }
  document.addEventListener("htmx:configRequest", function (e) {
    var token = cookie("csrftoken");
    if (!token) { var meta = document.querySelector("meta[name=csrf-token]"); token = meta ? meta.content : ""; }
    if (token) e.detail.headers["X-CSRFToken"] = token;
    // URLs limpias y compartibles: sin parámetros vacíos en las peticiones GET
    if (e.detail.verb === "get" && e.detail.parameters && e.detail.parameters.forEach) {
      var vacios = [];
      e.detail.parameters.forEach(function (v, k) { if (v === "") vacios.push(k); });
      vacios.forEach(function (k) { e.detail.parameters.delete(k); });
    }
  });

  // ---------- Contador del carrito (evento HX-Trigger "carrito-actualizado") ----------
  document.addEventListener("carrito-actualizado", function (e) {
    var n = (e.detail && e.detail.count) || 0;
    document.querySelectorAll("[data-contador-carrito]").forEach(function (el) {
      el.textContent = n;
      el.classList.toggle("hidden", !n);
    });
  });

  // ---------- Redirección pedida por HTMX a login, conservando la página ----------
  document.addEventListener("htmx:beforeSwap", function (e) {
    // Permite mostrar mensajes de error 4xx de formularios parciales
    if (e.detail.xhr.status === 422 || e.detail.xhr.status === 409) {
      e.detail.shouldSwap = true;
      e.detail.isError = false;
    }
  });

  document.addEventListener("htmx:responseError", function (e) {
    toast("No pudimos completar la acción. Intenta de nuevo.", "error");
  });
  document.addEventListener("htmx:sendError", function () {
    toast("Sin conexión. Revisa tu internet e intenta de nuevo.", "error");
  });

  // ---------- Toast desde JS ----------
  function toast(texto, tipo) {
    var cont = document.getElementById("mensajes");
    if (!cont) return;
    var div = document.createElement("div");
    div.className = "toast " + (tipo || "info");
    div.setAttribute("role", "status");
    var span = document.createElement("span");
    span.textContent = texto;
    var btn = document.createElement("button");
    btn.type = "button"; btn.setAttribute("aria-label", "Cerrar"); btn.textContent = "×";
    btn.onclick = function () { div.remove(); };
    div.appendChild(span); div.appendChild(btn);
    cont.appendChild(div);
    setTimeout(function () { div.remove(); }, 6000);
  }
  window.gtToast = toast;
  document.addEventListener("toast", function (e) { toast(e.detail.value || e.detail.texto, e.detail.tipo); });

  // ---------- Copiar al portapapeles ----------
  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-copiar]");
    if (!btn) return;
    var target = document.querySelector(btn.getAttribute("data-copiar"));
    var texto = target ? target.innerText : btn.getAttribute("data-texto");
    if (navigator.clipboard) {
      navigator.clipboard.writeText(texto).then(function () { toast("Copiado al portapapeles", "success"); });
    }
  });

  // ---------- Componentes Alpine ----------
  document.addEventListener("alpine:init", function () {
    /* Búsqueda predictiva: combobox accesible con debounce (250 ms en la plantilla) */
    Alpine.data("buscador", function (url) {
      return {
        q: "", html: "", abierto: false, activo: -1, ctrl: null,
        init: function () { this.q = this.$refs.input.value || ""; },
        opciones: function () { return Array.from(this.$refs.lista.querySelectorAll("[role=option]")); },
        buscar: function () {
          var self = this;
          var q = this.q.trim();
          if (q.length < 2) { this.cerrar(); this.html = ""; return; }
          if (this.ctrl) this.ctrl.abort();
          this.ctrl = new AbortController();
          var params = new URLSearchParams({ q: q });
          fetch(url + "?" + params.toString(), { signal: this.ctrl.signal, headers: { "HX-Request": "true" } })
            .then(function (r) { return r.text(); })
            .then(function (html) {
              self.html = html; self.activo = -1; self.abierto = true;
              self.$nextTick(function () {
                self.opciones().forEach(function (el, i) { el.id = "sug-" + i; el.setAttribute("aria-selected", "false"); });
                if (window.htmx) htmx.process(self.$refs.lista);
              });
            })
            .catch(function () {});
        },
        mover: function (d) {
          var ops = this.opciones();
          if (!this.abierto || !ops.length) { if (this.html) this.abierto = true; return; }
          this.activo = (this.activo + d + ops.length) % ops.length;
          ops.forEach(function (el, i) { el.setAttribute("aria-selected", i === this.activo ? "true" : "false"); }, this);
          ops[this.activo].scrollIntoView({ block: "nearest" });
        },
        elegir: function (e) {
          var ops = this.opciones();
          if (this.abierto && this.activo >= 0 && ops[this.activo]) {
            e.preventDefault();
            var el = ops[this.activo];
            this.cerrar();
            el.click();
          }
        },
        enviar: function () { this.cerrar(); },
        cerrar: function () { this.abierto = false; this.activo = -1; },
      };
    });

    /* Carrusel de banners */
    Alpine.data("carrusel", function (total) {
      return {
        i: 0, total: total, timer: null,
        init: function () { this.play(); },
        play: function () {
          var self = this;
          if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || this.total < 2) return;
          this.timer = setInterval(function () { self.next(); }, 6000);
        },
        stop: function () { clearInterval(this.timer); },
        next: function () { this.i = (this.i + 1) % this.total; },
        prev: function () { this.i = (this.i - 1 + this.total) % this.total; },
        ir: function (n) { this.i = n; },
      };
    });

    /* Galería de la ficha: miniaturas + zoom al pasar el cursor */
    Alpine.data("galeria", function () {
      return {
        actual: 0, zoom: false, origen: "50% 50%",
        mover: function (e) {
          var r = e.currentTarget.getBoundingClientRect();
          this.origen = ((e.clientX - r.left) / r.width * 100) + "% " + ((e.clientY - r.top) / r.height * 100) + "%";
        },
      };
    });

    /* Selector de cantidad limitado al stock */
    Alpine.data("cantidad", function (max, inicial) {
      return {
        n: inicial || 1, max: max,
        menos: function () { if (this.n > 1) this.n--; },
        mas: function () { if (this.n < this.max) this.n++; },
        validar: function () { var v = parseInt(this.n, 10) || 1; this.n = Math.min(Math.max(1, v), this.max); },
      };
    });

    /* Estado global de la interfaz (cajón móvil) */
    Alpine.store("ui", { menu: false });
    document.addEventListener("htmx:beforeSwap", function () { Alpine.store("ui").menu = false; });

    /* Lightbox simple */
    Alpine.store("lightbox", { src: "", alt: "", abierto: false,
      abrir: function (src, alt) { this.src = src; this.alt = alt || ""; this.abierto = true; },
      cerrar: function () { this.abierto = false; } });
  });

  // Al navegar con hx-boost, volver arriba y mover el foco al contenido principal (accesibilidad)
  document.addEventListener("htmx:afterSettle", function (e) {
    if (e.detail.boosted) {
      var main = document.getElementById("contenido");
      if (main) main.focus({ preventScroll: true });
    }
  });
})();
