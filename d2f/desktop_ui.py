#!/usr/bin/env python3
"""
Aplicación de escritorio nativa GTK4 para design2fusion.
No usa servidor web ni navegador: es una app GTK real.
"""

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib, Gdk, GdkPixbuf

import os
import sys
import threading
import subprocess
import tempfile
import shutil
from pathlib import Path

# Imports compatibles con pyinstaller
try:
    from . import __version__
    from .cli import convert
    from .settings import OUT_BASE
except ImportError:
    import d2f
    __version__ = d2f.__version__
    from d2f.cli import convert
    from d2f.settings import OUT_BASE

# -----------------------------------------------------------------------------
# Constantes y utilidades
# -----------------------------------------------------------------------------
APP_ID = "com.tulunlk.design2fusion"
SUPPORTED_EXTS = [".figcraft", ".penpot", ".fig", ".json"]
SUPPORTED_FILTERS = "*.figcraft,*.penpot,*.fig,*.json"


def human_size(path: Path) -> str:
    """Tamaño legible de archivo."""
    try:
        size = path.stat().st_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    except Exception:
        return "—"


# -----------------------------------------------------------------------------
# Widget: Drop Zone con drag & drop nativo
# -----------------------------------------------------------------------------
class DropZone(Gtk.DropTarget):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.set_gtypes([Gdk.FileList])
        self.connect("drop", self.on_drop)

    def on_drop(self, target, value, x, y):
        files = value.get_files()
        if files:
            file_path = files[0].get_path()
            if file_path and any(file_path.endswith(ext) for ext in SUPPORTED_EXTS):
                self.callback(file_path)
                return True
        return False


class DropZoneWidget(Gtk.Box):
    def __init__(self, on_file_selected):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.on_file_selected = on_file_selected
        self.set_css_classes(["drop-zone"])
        self.set_valign(Gtk.Align.CENTER)
        self.set_halign(Gtk.Align.CENTER)
        self.set_hexpand(True)

        # Drop target nativo GTK4
        drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop_target.connect("drop", self.on_drop)
        self.add_controller(drop_target)

        # Contenido visual
        icon = Gtk.Image.new_from_icon_name("document-open-symbolic")
        icon.set_pixel_size(48)
        icon.set_css_classes(["drop-icon"])

        title = Gtk.Label(label="Arrastra tu archivo aquí")
        title.add_css_class("drop-title")

        hint = Gtk.Label(label="o haz clic para seleccionar")
        hint.add_css_class("drop-hint")

        formats = Gtk.Label()
        formats.set_markup(
            'Formatos: <tt>.figcraft</tt> <tt>.penpot</tt> <tt>.fig</tt> <tt>.json</tt> (con carpeta <tt>images/</tt>)'
        )
        formats.add_css_class("drop-formats")

        self.append(icon)
        self.append(title)
        self.append(hint)
        self.append(formats)

        # Click para abrir selector
        gesture = Gtk.GestureClick.new()
        gesture.connect("pressed", self.on_click)
        self.add_controller(gesture)

    def on_drop(self, target, value, x, y):
        files = value.get_files()
        if files:
            file_path = files[0].get_path()
            if file_path and any(file_path.endswith(ext) for ext in SUPPORTED_EXTS):
                self.on_file_selected(file_path)
                self.add_css_class("drag-active")
                GLib.timeout_add(300, lambda: self.remove_css_class("drag-active") or False)
                return True
        return False

    def on_click(self, gesture, n_press, x, y):
        dialog = Gtk.FileDialog.new()
        dialog.set_title("Seleccionar archivo de diseño")
        filters = Gtk.FileFilter.new()
        filters.set_name("Archivos de diseño")
        for ext in SUPPORTED_EXTS:
            filters.add_pattern(f"*{ext}")
        dialog.set_filters(Gio.ListStore.new(filters))

        def on_open_done(dialog, result):
            try:
                file = dialog.open_finish(result)
                if file:
                    self.on_file_selected(file.get_path())
            except Exception as e:
                print(f"Error abriendo archivo: {e}")

        dialog.open(None, None, on_open_done)

    def set_drag_active(self, active: bool):
        if active:
            self.add_css_class("drag-active")
        else:
            self.remove_css_class("drag-active")


# -----------------------------------------------------------------------------
# Widget: Output Section (carpeta destino, preview, thumbnails)
# -----------------------------------------------------------------------------
class OutputSection(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.set_visible(False)
        self.add_css_class("output-section")

    def show_result(self, result: dict):
        self.remove_all()

        # Header card
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        card.add_css_class("out-card")

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        header.add_css_class("out-header")
        header.set_margin_top(16)
        header.set_margin_bottom(16)
        header.set_margin_start(20)
        header.set_margin_end(20)

        badge = Gtk.Label(label="Listo")
        badge.add_css_class("out-badge")

        outdir = result.get("outdir", "")
        path_label = Gtk.Label(label=outdir)
        path_label.add_css_class("out-path")
        path_label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
        path_label.set_hexpand(True)
        path_label.set_selectable(True)

        open_btn = Gtk.Button(label="Abrir carpeta")
        open_btn.add_css_class("btn-link")
        open_btn.connect("clicked", lambda b: self.open_folder(outdir))

        header.append(badge)
        header.append(path_label)
        header.append(open_btn)
        card.append(header)

        # Body
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        body.set_margin_top(20)
        body.set_margin_bottom(20)
        body.set_margin_start(20)
        body.set_margin_end(20)

        # Preview image
        ref = result.get("referencia")
        if ref and os.path.exists(ref):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(ref, 800, 450, True)
                img = Gtk.Picture.new_for_pixbuf(pixbuf)
                img.set_content_fit(Gtk.ContentFit.CONTAIN)
                frame = Gtk.Frame()
                frame.set_child(img)
                frame.add_css_class("preview-frame")
                body.append(frame)
            except Exception as e:
                print(f"Error cargando preview: {e}")

        # Thumbnails grid
        capas = result.get("capas", [])
        if capas:
            grid = Gtk.FlowBox()
            grid.set_valign(Gtk.Align.START)
            grid.set_max_children_per_line(4)
            grid.set_min_children_per_line(1)
            grid.set_selection_mode(Gtk.SelectionMode.NONE)
            grid.add_css_class("out-grid")

            for capa_path in capas:
                if not os.path.exists(capa_path):
                    continue
                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(capa_path, 180, 101, True)
                    img = Gtk.Picture.new_for_pixbuf(pixbuf)
                    img.set_content_fit(Gtk.ContentFit.COVER)

                    thumb = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                    thumb.add_css_class("thumb")
                    thumb.append(img)

                    name = os.path.basename(capa_path)
                    label = Gtk.Label(label=name)
                    label.add_css_class("thumb-label")
                    label.set_ellipsize(3)
                    label.set_max_width_chars(20)
                    thumb.append(label)

                    grid.append(thumb)
                except Exception as e:
                    print(f"Error cargando thumbnail {capa_path}: {e}")

            body.append(grid)

        # JSON details (collapsible)
        expander = Gtk.Expander()
        expander.set_label("Ver JSON completo")
        json_text = Gtk.TextView()
        json_text.set_editable(False)
        json_text.set_monospace(True)
        json_text.set_wrap_mode(Gtk.WrapMode.NONE)
        json_text.get_buffer().set_text(str(result))
        json_text.add_css_class("out-json")
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_max_height(300)
        scrolled.set_child(json_text)
        expander.set_child(scrolled)
        body.append(expander)

        card.append(body)
        self.append(card)
        self.set_visible(True)

    def open_folder(self, path):
        try:
            subprocess.Popen(["xdg-open", path], start_new_session=True)
        except Exception as e:
            print(f"Error abriendo carpeta: {e}")

    def show_error(self, message: str):
        self.remove_all()
        err = Gtk.Label(label=message)
        err.add_css_class("error")
        err.set_wrap(True)
        err.set_margin_top(20)
        err.set_margin_bottom(20)
        self.append(err)
        self.set_visible(True)

    def remove_all(self):
        child = self.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.remove(child)
            child = next_child


# -----------------------------------------------------------------------------
# Ventana principal
# -----------------------------------------------------------------------------
class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.set_title("design2fusion")
        self.set_default_size(1000, 950)
        self.set_icon_name("design2fusion")

        # Variables de estado
        self.current_file = None
        self.converting = False

        # Layout principal
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(main_box)

        # Header bar (Adw)
        header = Adw.HeaderBar()
        header.set_title_widget(Gtk.Label(label="design2fusion"))
        main_box.append(header)

        # Content con scroll
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        main_box.append(scrolled)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        content.set_margin_top(32)
        content.set_margin_bottom(60)
        content.set_margin_start(20)
        content.set_margin_end(20)
        scrolled.set_child(content)

        # Title area
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        title_box.set_halign(Gtk.Align.CENTER)

        title = Gtk.Label(label="design2fusion")
        title.add_css_class("main-title")

        subtitle = Gtk.Label(label="Figma · Penpot · FigCraft → nodos de Fusion (DaVinci Resolve)")
        subtitle.add_css_class("main-subtitle")

        version_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        version_box.set_halign(Gtk.Align.CENTER)
        version_box.add_css_class("version-bar")

        version_label = Gtk.Label(label=f"v{__version__}")
        version_label.add_css_class("version-label")

        update_btn = Gtk.Button(label="Actualizar")
        update_btn.add_css_class("btn-update")
        update_btn.connect("clicked", self.on_update_clicked)

        version_box.append(version_label)
        version_box.append(update_btn)

        title_box.append(title)
        title_box.append(subtitle)
        title_box.append(version_box)
        content.append(title_box)

        # Drop zone
        self.drop_zone = DropZoneWidget(self.on_file_selected)
        content.append(self.drop_zone)

        # Or divider
        divider = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        divider.add_css_class("or-divider")
        divider_label = Gtk.Label(label="O una ruta local")
        divider_label.add_css_class("or-label")
        divider.append(divider_label)
        content.append(divider)

        # Path input
        path_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.path_entry = Gtk.Entry()
        self.path_entry.set_placeholder_text("/home/alan/Descargas/mi-diseño.figcraft")
        self.path_entry.set_hexpand(True)
        self.path_entry.connect("activate", self.on_convert_clicked)
        path_box.append(self.path_entry)
        content.append(path_box)

        # Options
        # Options container
        options_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)

        opts_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)

        frame_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        frame_label = Gtk.Label(label="Frame (nombre o id, opcional)")
        frame_label.add_css_class("opt-label")
        frame_label.set_halign(Gtk.Align.START)
        self.frame_entry = Gtk.Entry()
        self.frame_entry.set_placeholder_text("Slide 16:9 - 1")
        self.frame_entry.connect("activate", self.on_convert_clicked)
        frame_box.append(frame_label)
        frame_box.append(self.frame_entry)
        opts_box.append(frame_box)

        scale_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        scale_label = Gtk.Label(label="Escala PNG")
        scale_label.add_css_class("opt-label")
        scale_label.set_halign(Gtk.Align.START)
        self.scale_spin = Gtk.SpinButton.new_with_range(0.1, 8.0, 0.5)
        self.scale_spin.set_value(1.0)
        self.scale_spin.connect("activate", self.on_convert_clicked)
        scale_box.append(scale_label)
        scale_box.append(self.scale_spin)
        opts_box.append(scale_box)

        anim_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        anim_label = Gtk.Label(label="Animación de texto")
        anim_label.add_css_class("opt-label")
        anim_label.set_halign(Gtk.Align.START)
        self.anim_ids = ["none", "scale-in", "letter-slide"]
        self.anim_dd = Gtk.DropDown.new_from_strings([
            "Sin animación",
            "Entrada (Reactor: Scale In)",
            "Letra a letra (Reactor: Letter Slide)",
        ])
        anim_box.append(anim_label)
        anim_box.append(self.anim_dd)
        opts_box.append(anim_box)
        options_container.append(opts_box)

        # Output directory selector
        out_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        out_label = Gtk.Label(label="Carpeta de salida")
        out_label.add_css_class("opt-label")
        out_label.set_halign(Gtk.Align.START)
        
        out_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.out_entry = Gtk.Entry()
        self.out_entry.set_placeholder_text("Por defecto: ~/Documentos/MotionGraphic/design2fusion/<frame>")
        self.out_entry.set_hexpand(True)
        
        self.out_btn = Gtk.Button(label="Examinar…")
        self.out_btn.connect("clicked", self.on_browse_out_clicked)
        
        out_row.append(self.out_entry)
        out_row.append(self.out_btn)
        
        out_box.append(out_label)
        out_box.append(out_row)
        options_container.append(out_box)
        content.append(options_container)

        # Convert button
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        btn_box.set_halign(Gtk.Align.CENTER)
        self.convert_btn = Gtk.Button(label="Convertir")
        self.convert_btn.add_css_class("btn-convert")
        self.convert_btn.connect("clicked", self.on_convert_clicked)
        btn_box.append(self.convert_btn)
        content.append(btn_box)

        # Output section
        self.output = OutputSection()
        content.append(self.output)

        # Spinner (hidden initially)
        self.spinner = Gtk.Spinner()
        self.spinner.set_visible(False)
        btn_box.append(self.spinner)

    def on_file_selected(self, path: str):
        self.current_file = path
        self.path_entry.set_text(path)

    def on_browse_out_clicked(self, _btn):
        dialog = Gtk.FileDialog()
        dialog.set_title("Seleccionar carpeta de salida")
        dialog.select_folder(self, None, self.on_folder_selected)

    def on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                path = folder.get_path()
                if path:
                    self.out_entry.set_text(path)
        except Exception:
            pass

    def on_convert_clicked(self, _widget=None):
        if self.converting:
            return

        # Obtener archivo: drop zone o entry
        file_path = self.current_file or self.path_entry.get_text().strip()
        if not file_path:
            self.show_error("Seleccioná un archivo o poné una ruta")
            return

        frame = self.frame_entry.get_text().strip() or None
        scale = self.scale_spin.get_value()
        anim = self.anim_ids[self.anim_dd.get_selected()]
        out = self.out_entry.get_text().strip() or None

        self.set_converting(True)
        self.output.set_visible(False)

        # Ejecutar conversión en thread aparte
        thread = threading.Thread(
            target=self.run_conversion,
            args=(file_path, frame, scale, anim, out),
            daemon=True
        )
        thread.start()

    def set_converting(self, converting: bool):
        self.converting = converting
        self.convert_btn.set_sensitive(not converting)
        self.convert_btn.set_label("Convirtiendo…" if converting else "Convertir")
        self.spinner.set_visible(converting)
        if converting:
            self.spinner.start()
        else:
            self.spinner.stop()

    def run_conversion(self, src, frame, scale, text_anim="none", out=None):
        try:
            # Llamar a la función convert directamente (misma que CLI)
            result = convert(
                src.rstrip("\r\n"),
                frame,
                None,  # page
                out,   # out
                scale,
                True,  # make_comp
                True,  # make_kit
                log=lambda m: print(m, file=sys.stderr),
                text_anim=text_anim,
            )

            # Agregar lista de capas
            capas_dir = os.path.join(result["outdir"], "capas")
            if os.path.isdir(capas_dir):
                result["capas"] = sorted(
                    os.path.join(capas_dir, f)
                    for f in os.listdir(capas_dir)
                )
            else:
                result["capas"] = []

            # UI en hilo principal
            GLib.idle_add(self.on_conversion_done, result)

        except Exception as e:
            GLib.idle_add(self.on_conversion_error, str(e))

    def on_conversion_done(self, result):
        self.set_converting(False)
        self.output.show_result(result)

    def on_conversion_error(self, error_msg):
        self.set_converting(False)
        self.output.show_error(f"Error: {error_msg}")

    def show_error(self, message):
        dialog = Adw.MessageDialog(
            heading="Error",
            body=message,
        )
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        dialog.present(self)

    def on_update_clicked(self, _btn):
        if getattr(sys, "frozen", False):
            self.show_error("Actualización no disponible en modo ejecutable.")
            return

        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if not os.path.isdir(os.path.join(repo_dir, ".git")):
            self.show_error("No es un repositorio git.")
            return

        def run_git():
            try:
                result = subprocess.run(
                    ["git", "-C", repo_dir, "pull", "--ff-only"],
                    capture_output=True, text=True, timeout=180
                )
                msg = (result.stdout + result.stderr).strip() or "(sin salida)"
                GLib.idle_add(self.on_update_done, result.returncode == 0, msg)
            except Exception as e:
                GLib.idle_add(self.on_update_done, False, str(e))

        threading.Thread(target=run_git, daemon=True).start()

    def on_update_done(self, ok, msg):
        if ok:
            # Actualizar label de versión si cambió
            pass
            dialog = Adw.MessageDialog(
                heading="Actualizado",
                body=msg,
            )
        else:
            dialog = Adw.MessageDialog(
                heading="Error al actualizar",
                body=msg,
            )
        dialog.add_response("ok", "OK")
        dialog.present(self)


# -----------------------------------------------------------------------------
# Application class
# -----------------------------------------------------------------------------
class Design2FusionApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.connect("activate", self.on_activate)

    def on_activate(self, app):
        win = MainWindow(app)
        win.present()


# -----------------------------------------------------------------------------
# CSS
# -----------------------------------------------------------------------------
CSS = """
/* GTK4-compatible CSS - using standard GTK properties */
@define-color accent_color #4a90d9;
@define-color text_color #2e3436;
@define-color background_color #f6f5f4;
@define-color base_color #ffffff;
@define-color border_color #c3b79e;
@define-color dim_text_color #6a6d76;
@define-color selected_bg_color #5a526e;

.drop-zone {
    border: 2px dashed #c3b79e;
    border-radius: 16px;
    background: #f6f5f4;
    padding: 48px 24px;
    min-width: 400px;
    min-height: 200px;
}
.drop-zone:hover {
    border-color: #4a90d9;
    background: linear-gradient(180deg, #f0efe9 0%, #f6f5f4 100%);
}
.drop-zone.drag-active {
    border-color: #4a90d9;
    background: linear-gradient(180deg, #e8e7e3 0%, #f6f5f4 100%);
}
.drop-icon { font-size: 48px; margin-bottom: 12px; }
.drop-title { font-size: 18px; font-weight: 600; margin-bottom: 6px; }
.drop-hint { color: #6a6d76; font-size: 13px; }
.drop-formats { margin-top: 16px; font-size: 12px; color: #6a6d76; }
.drop-formats tt { background: #ffffff; padding: 2px 6px; border-radius: 4px; margin: 0 2px; }

.or-divider {
    margin: 24px 0;
    color: #6a6d76;
    font-size: 13px;
    padding-left: 20px;
    padding-right: 20px;
}
.or-divider horizontal {
    border-bottom: 1px solid #c3b79e;
}
.or-label { color: #6a6d76; font-size: 13px; }

.version-bar {
    background: rgba(74, 144, 217, 0.12);
    border-bottom: 1px solid #c3b79e;
    padding: 8px 20px;
}
.version-label { font-size: 12px; font-weight: 600; color: #2e3436; }
.btn-update {
    background: transparent; border: 1px solid #c3b79e; color: #6a6d76;
    padding: 6px 12px; border-radius: 6px; font-size: 13px;
}
.btn-update:hover {
    border-color: #4a90d9;
    color: #4a90d9;
}

.entry, .spinbutton {
    border-radius: 8px;
    border: 1px solid #c3b79e;
    background: #ffffff;
}
.entry:focus, .spinbutton:focus {
    border-color: #4a90d9;
}

.opt-label { font-size: 12px; color: #6a6d76; margin-bottom: 6px; }

.btn-convert {
    padding: 14px 36px;
    border-radius: 10px;
    border: none;
    background: #4a90d9;
    color: #ffffff;
    font-weight: 600;
    font-size: 15px;
}
.btn-convert:hover:not(.disabled) {
    background: #357abd;
}
.btn-convert.disabled {
    opacity: 0.5;
}

.output-section { margin-top: 36px; }
.out-card {
    border: 1px solid #c3b79e;
    border-radius: 14px;
    background: linear-gradient(180deg, #f6f5f4 0%, #ffffff 100%);
}
.out-header {
    background: rgba(74, 144, 217, 0.12);
    border-bottom: 1px solid #c3b79e;
    padding: 16px 20px;
}
.out-badge {
    background: #4a90d9;
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    padding: 4px 10px;
    border-radius: 999px;
    text-transform: uppercase;
}
.out-path { font-family: monospace; font-size: 13px; color: #2e3436; }
.btn-link {
    background: transparent;
    border: 1px solid #c3b79e;
    color: #6a6d76;
    padding: 8px 14px;
    border-radius: 8px;
    font-size: 13px;
}
.btn-link:hover {
    border-color: #4a90d9;
    color: #4a90d9;
}

.preview-frame { border-radius: 10px; border: 1px solid #c3b79e; }
.thumb { border-radius: 8px; background: #ffffff; }
.thumb-label { padding: 6px 8px; font-size: 11px; color: #ffffff; background: linear-gradient(0deg, rgba(0,0,0,0.55), transparent); }
.out-json {
    background: #ffffff;
    border: 1px solid #c3b79e;
    border-radius: 10px;
    padding: 14px;
    font-size: 12px;
    font-family: monospace;
}
.error {
    color: #cc0000;
    background: rgba(204, 0, 0, 0.1);
    border: 1px solid #cc0000;
    padding: 14px;
    border-radius: 10px;
    margin-top: 16px;
}

.main-title { font-size: 28px; font-weight: 700; }
.main-subtitle { color: #6a6d76; font-size: 14px; }
"""

def load_css():
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS.encode())
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------
def main():
    load_css()
    app = Design2FusionApp()
    return app.run([sys.argv[0]] if sys.argv else None)


if __name__ == "__main__":
    sys.exit(main())