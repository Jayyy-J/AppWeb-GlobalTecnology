/* Panel GlobalTecnology: componentes del formulario de producto, arrastrar y soltar */
(function () {
  "use strict";

  function cop(n) {
    n = Math.round(Number(n) || 0);
    return "$" + n.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }
  window.gtCop = cop;

  // Reordenamiento con SortableJS: <ul data-sortable="/url/" data-campo="orden"> con hijos [data-id]
  function initSortables(root) {
    if (!window.Sortable) return;
    (root || document).querySelectorAll("[data-sortable]").forEach(function (el) {
      if (el._sortable) return;
      el._sortable = Sortable.create(el, {
        animation: 160, handle: el.getAttribute("data-handle") || null, ghostClass: "sortable-ghost",
        onEnd: function () {
          var ids = Array.from(el.children).map(function (c) { return c.getAttribute("data-id"); }).filter(Boolean);
          var body = new URLSearchParams();
          ids.forEach(function (id) { body.append("orden", id); });
          var meta = document.querySelector("meta[name=csrf-token]");
          var m = document.cookie.match(/(?:^|;)\s*csrftoken=([^;]+)/);
          fetch(el.getAttribute("data-sortable"), {
            method: "POST", body: body,
            headers: { "X-CSRFToken": m ? decodeURIComponent(m[1]) : (meta ? meta.content : ""), "HX-Request": "true" },
          }).then(function (r) {
            if (window.gtToast) gtToast(r.ok ? "Orden guardado" : "No se pudo guardar el orden", r.ok ? "success" : "error");
          });
        },
      });
    });
  }
  document.addEventListener("DOMContentLoaded", function () { initSortables(); });
  document.addEventListener("htmx:load", function (e) { initSortables(e.target); });

  document.addEventListener("alpine:init", function () {
    /* Vista previa en vivo del precio + editor de especificaciones */
    Alpine.data("productoForm", function (inicial) {
      return {
        precio: inicial.precio || 0, tipo: inicial.tipo || "ninguno", pct: inicial.pct || null, antes: inicial.antes || null,
        specs: inicial.specs || [],
        get final() {
          if (this.tipo === "porcentaje" && this.pct >= 1 && this.pct <= 90) return Math.round(this.precio * (100 - this.pct) / 100);
          return this.precio;
        },
        get tachado() {
          if (this.tipo === "porcentaje" && this.pct >= 1 && this.pct <= 90) return this.precio;
          if (this.tipo === "precio_antes" && this.antes > this.precio) return this.antes;
          return 0;
        },
        get ahorroPct() {
          if (!this.tachado) return 0;
          if (this.tipo === "porcentaje") return this.pct;
          return Math.round((this.tachado - this.final) * 100 / this.tachado);
        },
        get errorDescuento() {
          if (this.tipo === "porcentaje" && !(this.pct >= 1 && this.pct <= 90)) return "El porcentaje debe estar entre 1 y 90.";
          if (this.tipo === "precio_antes" && !(this.antes > this.precio)) return "El precio antes debe ser mayor que el precio de venta.";
          return "";
        },
        cop: cop,
        agregarSpec: function () { this.specs.push({ k: "", v: "" }); },
        quitarSpec: function (i) { this.specs.splice(i, 1); },
        get specsJson() { return JSON.stringify(this.specs); },
      };
    });

    /* Zona de arrastrar y soltar fotos: asigna los archivos al <input type=file multiple> */
    Alpine.data("dropzone", function () {
      return {
        encima: false, nombres: [],
        soltar: function (e) {
          this.encima = false;
          var input = this.$refs.input;
          var dt = new DataTransfer();
          Array.from(input.files || []).forEach(function (f) { dt.items.add(f); });
          Array.from(e.dataTransfer.files).forEach(function (f) { if (f.type.indexOf("image/") === 0) dt.items.add(f); });
          input.files = dt.files;
          this.actualizar();
          if (input.hasAttribute("data-autosubmit")) input.dispatchEvent(new Event("change", { bubbles: true }));
        },
        actualizar: function () { this.nombres = Array.from(this.$refs.input.files || []).map(function (f) { return f.name; }); },
      };
    });

    /* Formulario de cambio de estado: muestra campos según estado y método */
    Alpine.data("cambioEstado", function (estado, metodo, metodoActual) {
      return { estado: estado || "", metodo: metodo || "", metodoActual: metodoActual || "" };
    });
  });
})();
