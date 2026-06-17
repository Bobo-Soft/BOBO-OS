#!/usr/bin/env python3
# =============================================================================
# BoboPlayer - Media Player complet pentru BOBO OS (APP 01)
# GTK4 + GStreamer playbin3. Video + audio, subtitrari, playlist, istoric.
# Backend video: gtk4paintablesink (preferat) cu fallback Gtk.Video/MediaFile.
# =============================================================================
import os
import sys
import json
import random
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gtk, Gst, GLib, Gdk, Gio, GdkPixbuf  # noqa: E402

Gst.init(None)

APP_ID = "os.bobo.Player"
DATA_DIR = os.path.expanduser("~/.local/share/bobo-player")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
RECENT_FILE = os.path.join(DATA_DIR, "recent.json")
PICTURES_DIR = os.path.expanduser("~/Imagini")
if not os.path.isdir(PICTURES_DIR):
    PICTURES_DIR = os.path.expanduser("~/Pictures")

VIDEO_EXT = (".mp4", ".mkv", ".avi", ".webm", ".mov", ".flv", ".m4v", ".mpg", ".mpeg", ".wmv")
AUDIO_EXT = (".mp3", ".flac", ".ogg", ".wav", ".aac", ".opus", ".m4a")
SUB_EXT = (".srt", ".ass", ".ssa", ".vtt")

# Bitmask GstPlayFlags pentru a activa text/subtitrari + soft colorbalance
PLAY_FLAG_VIDEO = 1 << 0
PLAY_FLAG_AUDIO = 1 << 1
PLAY_FLAG_TEXT = 1 << 2
PLAY_FLAG_SOFT_COLORBALANCE = 1 << 10


def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def _save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except Exception as exc:
        print("[bobo-player] nu pot salva %s: %s" % (path, exc), file=sys.stderr)


def _fmt_time(nanoseconds):
    """Formateaza nanosecunde GStreamer ca H:MM:SS sau MM:SS."""
    if nanoseconds is None or nanoseconds < 0:
        return "0:00"
    secs = int(nanoseconds // Gst.SECOND)
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    if h:
        return "%d:%02d:%02d" % (h, m, s)
    return "%d:%02d" % (m, s)


def _find_subtitle(media_path):
    """Cauta un fisier de subtitrare cu acelasi nume langa fisierul media."""
    base = os.path.splitext(media_path)[0]
    for ext in SUB_EXT:
        cand = base + ext
        if os.path.isfile(cand):
            return cand
    return None


class BoboPlayerWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboPlayer")
        self.set_default_size(960, 600)

        self.playlist = []          # liste de cai absolute
        self.current_index = -1
        self.is_fullscreen = False
        self.repeat_mode = "off"    # off | one | all
        self.shuffle = False
        self.controls_hide_id = 0
        self.duration = 0
        self.seeking = False

        self.history = _load_json(HISTORY_FILE, {})
        self.recent = _load_json(RECENT_FILE, [])

        self._build_pipeline()
        self._build_ui()
        self._install_shortcuts()

        # Tick periodic pentru actualizarea barei de progres (4x/sec)
        GLib.timeout_add(250, self._on_tick)

    # ---------------------------------------------------------------- pipeline
    def _build_pipeline(self):
        """Construieste playbin3 + videobalance pentru reglaje de imagine."""
        self.playbin = Gst.ElementFactory.make("playbin3", "playbin")
        if self.playbin is None:
            self.playbin = Gst.ElementFactory.make("playbin", "playbin")

        # Activeaza video+audio+text(subtitrari)+colorbalance soft
        flags = PLAY_FLAG_VIDEO | PLAY_FLAG_AUDIO | PLAY_FLAG_TEXT | PLAY_FLAG_SOFT_COLORBALANCE
        self.playbin.set_property("flags", flags)

        # videobalance permite luminozitate/contrast/saturatie
        self.balance = Gst.ElementFactory.make("videobalance", "balance")

        # Sink video catre GTK4 (paintable). Daca lipseste -> fallback Gtk.Video.
        self.gtk_sink = Gst.ElementFactory.make("gtk4paintablesink", "gtksink")
        self.use_paintable = self.gtk_sink is not None
        if self.use_paintable:
            # Inseram videobalance in fata sink-ului printr-un bin
            sink_bin = Gst.Bin.new("sinkbin")
            conv = Gst.ElementFactory.make("videoconvert", "conv")
            sink_bin.add(self.balance)
            sink_bin.add(conv)
            sink_bin.add(self.gtk_sink)
            self.balance.link(conv)
            conv.link(self.gtk_sink)
            ghost = Gst.GhostPad.new("sink", self.balance.get_static_pad("sink"))
            sink_bin.add_pad(ghost)
            self.playbin.set_property("video-sink", sink_bin)

        # Bus pentru evenimente (EOS, erori, schimbari de stare)
        bus = self.playbin.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", self._on_eos)
        bus.connect("message::error", self._on_error)

    # ---------------------------------------------------------------------- UI
    def _build_ui(self):
        # CSS propriu
        css = Gtk.CssProvider()
        css_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")
        if os.path.exists(css_path):
            css.load_from_path(css_path)
            Gtk.StyleContext.add_provider_for_display(
                Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

        header = Gtk.HeaderBar()
        self.set_titlebar(header)

        open_btn = Gtk.Button.new_from_icon_name("document-open-symbolic")
        open_btn.set_tooltip_text("Deschide fisiere")
        open_btn.connect("clicked", self._on_open_clicked)
        header.pack_start(open_btn)

        self.playlist_btn = Gtk.ToggleButton()
        self.playlist_btn.set_icon_name("view-list-symbolic")
        self.playlist_btn.set_tooltip_text("Playlist")
        self.playlist_btn.connect("toggled", self._on_playlist_toggle)
        header.pack_end(self.playlist_btn)

        # Meniu Vizualizare (reglaje imagine)
        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("emblem-photos-symbolic")
        menu_btn.set_tooltip_text("Imagine: luminozitate/contrast/saturatie")
        menu_btn.set_popover(self._build_image_popover())
        header.pack_end(menu_btn)

        # Layout principal: video (overlay cu controale) | playlist
        self.split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.set_child(self.split)

        self.overlay = Gtk.Overlay()
        self.split.set_start_child(self.overlay)
        self.split.set_resize_start_child(True)
        self.split.set_shrink_start_child(False)

        # Suprafata video
        if self.use_paintable:
            self.video_widget = Gtk.Picture()
            self.video_widget.set_paintable(self.gtk_sink.get_property("paintable"))
            self.video_widget.set_content_fit(Gtk.ContentFit.CONTAIN)
        else:
            # Fallback robust: Gtk.Video (foloseste GStreamer sub capota)
            self.video_widget = Gtk.Video()
        self.video_widget.add_css_class("bobo-video")
        self.video_widget.set_hexpand(True)
        self.video_widget.set_vexpand(True)
        self.overlay.set_child(self.video_widget)

        # Click pe video = play/pause; miscarea mouse-ului = arata controalele
        click = Gtk.GestureClick()
        click.connect("released", lambda *a: self.toggle_play())
        self.video_widget.add_controller(click)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", lambda *a: self._show_controls())
        self.overlay.add_controller(motion)

        # Bara de controale (overlay jos)
        self.controls = self._build_controls()
        self.overlay.add_overlay(self.controls)

        # Panou playlist (dreapta)
        self.playlist_panel = self._build_playlist_panel()
        self.split.set_end_child(self.playlist_panel)
        self.split.set_resize_end_child(False)
        self.split.set_shrink_end_child(False)
        self.playlist_panel.set_visible(False)

        # Daca nu am argumente, arata fisierele recente
        self._refresh_recent_view()

    def _build_controls(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.add_css_class("bobo-controls")
        box.set_valign(Gtk.Align.END)
        box.set_margin_start(8)
        box.set_margin_end(8)
        box.set_margin_bottom(8)

        # Bara de pozitie cu etichete timp
        seek_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.pos_label = Gtk.Label(label="0:00")
        self.dur_label = Gtk.Label(label="0:00")
        self.seek_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1000, 1)
        self.seek_scale.set_hexpand(True)
        self.seek_scale.set_draw_value(False)
        self.seek_scale.connect("change-value", self._on_seek)
        # Tooltip cu thumbnail la hover pe bara
        seek_motion = Gtk.EventControllerMotion()
        seek_motion.connect("motion", self._on_seek_hover)
        self.seek_scale.add_controller(seek_motion)
        seek_row.append(self.pos_label)
        seek_row.append(self.seek_scale)
        seek_row.append(self.dur_label)
        box.append(seek_row)

        # Rand butoane
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_row.set_halign(Gtk.Align.CENTER)

        self.prev_btn = self._icon_button("media-skip-backward-symbolic", self.prev_track, "Anterior")
        self.play_btn = self._icon_button("media-playback-start-symbolic", lambda *a: self.toggle_play(), "Play/Pauza")
        self.next_btn = self._icon_button("media-skip-forward-symbolic", self.next_track, "Urmator")
        btn_row.append(self.prev_btn)
        btn_row.append(self.play_btn)
        btn_row.append(self.next_btn)

        self.shuffle_btn = Gtk.ToggleButton()
        self.shuffle_btn.set_icon_name("media-playlist-shuffle-symbolic")
        self.shuffle_btn.set_tooltip_text("Amestecare")
        self.shuffle_btn.connect("toggled", self._on_shuffle_toggle)
        btn_row.append(self.shuffle_btn)

        self.repeat_btn = self._icon_button("media-playlist-repeat-symbolic", self._cycle_repeat, "Repetare: off/all/one")
        btn_row.append(self.repeat_btn)

        # Volum + mute
        self.mute_btn = self._icon_button("audio-volume-high-symbolic", self._toggle_mute, "Mut")
        btn_row.append(self.mute_btn)
        self.vol_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1.0, 0.01)
        self.vol_scale.set_size_request(110, -1)
        self.vol_scale.set_value(1.0)
        self.vol_scale.set_draw_value(False)
        self.vol_scale.connect("value-changed", lambda s: self.playbin.set_property("volume", s.get_value()))
        btn_row.append(self.vol_scale)

        self.fs_btn = self._icon_button("view-fullscreen-symbolic", lambda *a: self.toggle_fullscreen(), "Ecran complet")
        btn_row.append(self.fs_btn)

        box.append(btn_row)
        return box

    def _build_playlist_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_size_request(260, -1)
        box.add_css_class("bobo-playlist")

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        header.set_margin_top(6)
        header.set_margin_start(6)
        header.set_margin_end(6)
        title = Gtk.Label(label="Playlist")
        title.set_hexpand(True)
        title.set_xalign(0)
        title.add_css_class("title-4")
        clear = Gtk.Button.new_from_icon_name("edit-clear-all-symbolic")
        clear.set_tooltip_text("Goleste playlist")
        clear.connect("clicked", lambda *a: self._clear_playlist())
        header.append(title)
        header.append(clear)
        box.append(header)

        scroller = Gtk.ScrolledWindow()
        scroller.set_vexpand(True)
        self.playlist_list = Gtk.ListBox()
        self.playlist_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.playlist_list.connect("row-activated", self._on_playlist_row_activated)
        scroller.set_child(self.playlist_list)
        box.append(scroller)

        # Suport drag & drop fisiere pe playlist
        drop = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop.connect("drop", self._on_drop)
        self.playlist_list.add_controller(drop)
        return box

    def _build_image_popover(self):
        pop = Gtk.Popover()
        grid = Gtk.Grid(row_spacing=6, column_spacing=8)
        grid.set_margin_top(10)
        grid.set_margin_bottom(10)
        grid.set_margin_start(10)
        grid.set_margin_end(10)
        for row, (label, prop, lo, hi) in enumerate(
            [("Luminozitate", "brightness", -1, 1),
             ("Contrast", "contrast", 0, 2),
             ("Saturatie", "saturation", 0, 2)]
        ):
            grid.attach(Gtk.Label(label=label, xalign=0), 0, row, 1, 1)
            scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 0.05)
            scale.set_size_request(160, -1)
            scale.set_value(1.0 if prop != "brightness" else 0.0)
            scale.connect("value-changed",
                          lambda s, p=prop: self.balance.set_property(p, s.get_value()) if self.balance else None)
            grid.attach(scale, 1, row, 1, 1)
        pop.set_child(grid)
        return pop

    def _icon_button(self, icon, cb, tip):
        b = Gtk.Button.new_from_icon_name(icon)
        b.set_tooltip_text(tip)
        b.connect("clicked", cb)
        return b

    # ------------------------------------------------------------- shortcuts
    def _install_shortcuts(self):
        keymap = {
            "space": lambda: self.toggle_play(),
            "f": lambda: self.toggle_fullscreen(),
            "m": lambda: self._toggle_mute(),
            "q": lambda: self.close(),
            "Right": lambda: self.seek_relative(10),
            "Left": lambda: self.seek_relative(-10),
            "<Shift>Right": lambda: self.seek_relative(60),
            "<Shift>Left": lambda: self.seek_relative(-60),
            "<Ctrl>s": lambda: self.screenshot(),
            "Escape": lambda: self.toggle_fullscreen() if self.is_fullscreen else None,
        }
        ctrl = Gtk.ShortcutController()
        ctrl.set_scope(Gtk.ShortcutScope.GLOBAL)
        for accel, fn in keymap.items():
            trigger = Gtk.ShortcutTrigger.parse_string(accel)
            action = Gtk.CallbackAction.new(lambda w, a, f=fn: (f(), True)[1])
            ctrl.add_shortcut(Gtk.Shortcut.new(trigger, action))
        self.add_controller(ctrl)

    # ------------------------------------------------------------- playback
    def load_files(self, paths):
        added = []
        for p in paths:
            ap = os.path.abspath(p)
            if os.path.isfile(ap) and ap.lower().endswith(VIDEO_EXT + AUDIO_EXT):
                self.playlist.append(ap)
                added.append(ap)
        self._refresh_playlist_view()
        if added and self.current_index < 0:
            self.play_index(self.playlist.index(added[0]))

    def play_index(self, index):
        if index < 0 or index >= len(self.playlist):
            return
        self.current_index = index
        path = self.playlist[index]
        uri = Gst.filename_to_uri(path)

        self.playbin.set_state(Gst.State.NULL)
        if self.use_paintable:
            self.playbin.set_property("uri", uri)
            sub = _find_subtitle(path)
            if sub:
                self.playbin.set_property("suburi", Gst.filename_to_uri(sub))
        else:
            # fallback Gtk.Video
            self.video_widget.set_filename(path)

        # Reia de la pozitia salvata, daca exista
        resume = self.history.get(path, 0)
        self.playbin.set_state(Gst.State.PLAYING)
        if resume > 5:
            GLib.timeout_add(400, lambda: self._do_resume(resume))

        self._update_recent(path)
        self.set_title("BoboPlayer - " + os.path.basename(path))
        self.play_btn.set_icon_name("media-playback-pause-symbolic")
        self._refresh_playlist_view()

    def _do_resume(self, secs):
        self.playbin.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, secs * Gst.SECOND)
        return False

    def toggle_play(self):
        if self.current_index < 0 and self.playlist:
            self.play_index(0)
            return
        ok, state, _ = self.playbin.get_state(0)
        if state == Gst.State.PLAYING:
            self.playbin.set_state(Gst.State.PAUSED)
            self.play_btn.set_icon_name("media-playback-start-symbolic")
        else:
            self.playbin.set_state(Gst.State.PLAYING)
            self.play_btn.set_icon_name("media-playback-pause-symbolic")

    def next_track(self, *args):
        if not self.playlist:
            return
        if self.shuffle:
            idx = random.randrange(len(self.playlist))
        else:
            idx = self.current_index + 1
            if idx >= len(self.playlist):
                idx = 0
        self.play_index(idx)

    def prev_track(self, *args):
        if not self.playlist:
            return
        idx = self.current_index - 1
        if idx < 0:
            idx = len(self.playlist) - 1
        self.play_index(idx)

    def seek_relative(self, seconds):
        ok, pos = self.playbin.query_position(Gst.Format.TIME)
        if not ok:
            return
        target = max(0, pos + seconds * Gst.SECOND)
        self.playbin.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, target)

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.unfullscreen()
            self.is_fullscreen = False
        else:
            self.fullscreen()
            self.is_fullscreen = True
        self._show_controls()

    def _toggle_mute(self, *args):
        muted = not self.playbin.get_property("mute")
        self.playbin.set_property("mute", muted)
        self.mute_btn.set_icon_name("audio-volume-muted-symbolic" if muted else "audio-volume-high-symbolic")

    def _cycle_repeat(self, *args):
        order = {"off": "all", "all": "one", "one": "off"}
        self.repeat_mode = order[self.repeat_mode]
        icons = {"off": "media-playlist-repeat-symbolic",
                 "all": "media-playlist-repeat-symbolic",
                 "one": "media-playlist-repeat-song-symbolic"}
        self.repeat_btn.set_icon_name(icons[self.repeat_mode])
        if self.repeat_mode == "off":
            self.repeat_btn.remove_css_class("bobo-active")
        else:
            self.repeat_btn.add_css_class("bobo-active")

    def _on_shuffle_toggle(self, btn):
        self.shuffle = btn.get_active()

    def screenshot(self):
        """Salveaza cadrul curent ca PNG in ~/Imagini."""
        sample = self.playbin.get_property("sample") if not self.use_paintable else None
        try:
            caps = Gst.Caps.from_string("video/x-raw,format=RGB")
            sample = self.playbin.emit("convert-sample", caps)
        except Exception:
            sample = None
        if sample is None:
            self._notify("Screenshot indisponibil pentru acest flux")
            return
        buf = sample.get_buffer()
        s = sample.get_caps().get_structure(0)
        w = s.get_value("width")
        h = s.get_value("height")
        ok, mapinfo = buf.map(Gst.MapFlags.READ)
        if not ok:
            return
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_data(
                mapinfo.data, GdkPixbuf.Colorspace.RGB, False, 8, w, h, w * 3
            )
            os.makedirs(PICTURES_DIR, exist_ok=True)
            base = os.path.splitext(os.path.basename(self.playlist[self.current_index]))[0]
            out = os.path.join(PICTURES_DIR, "%s-frame.png" % base)
            n = 1
            while os.path.exists(out):
                out = os.path.join(PICTURES_DIR, "%s-frame-%d.png" % (base, n))
                n += 1
            pixbuf.savev(out, "png", [], [])
            self._notify("Captura salvata: %s" % out)
        finally:
            buf.unmap(mapinfo)

    # ------------------------------------------------------------- callbacks
    def _on_tick(self):
        if self.current_index < 0:
            return True
        ok_d, dur = self.playbin.query_duration(Gst.Format.TIME)
        ok_p, pos = self.playbin.query_position(Gst.Format.TIME)
        if ok_d and dur > 0:
            self.duration = dur
            self.dur_label.set_text(_fmt_time(dur))
            if ok_p and not self.seeking:
                self.seek_scale.set_value(pos / dur * 1000)
                self.pos_label.set_text(_fmt_time(pos))
                # salveaza pozitia pentru "remember position"
                path = self.playlist[self.current_index]
                self.history[path] = int(pos // Gst.SECOND)
        return True

    def _on_seek(self, scale, scroll, value):
        if self.duration <= 0:
            return False
        target = int(value / 1000 * self.duration)
        self.playbin.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT, target)
        return False

    def _on_seek_hover(self, ctrl, x, y):
        # Tooltip cu timpul la pozitia cursorului pe bara
        w = self.seek_scale.get_allocated_width()
        if w > 0 and self.duration > 0:
            frac = max(0.0, min(1.0, x / w))
            self.seek_scale.set_tooltip_text(_fmt_time(int(frac * self.duration)))

    def _on_eos(self, bus, msg):
        if self.repeat_mode == "one":
            self.play_index(self.current_index)
        elif self.current_index < len(self.playlist) - 1 or self.repeat_mode == "all":
            self.next_track()
        else:
            self.playbin.set_state(Gst.State.NULL)
            self.play_btn.set_icon_name("media-playback-start-symbolic")

    def _on_error(self, bus, msg):
        err, dbg = msg.parse_error()
        self._notify("Eroare redare: %s" % err.message)
        self.playbin.set_state(Gst.State.NULL)

    def _on_open_clicked(self, *args):
        dialog = Gtk.FileDialog()
        dialog.set_title("Deschide fisiere media")
        dialog.open_multiple(self, None, self._on_open_finished)

    def _on_open_finished(self, dialog, result):
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return
        paths = [files.get_item(i).get_path() for i in range(files.get_n_items())]
        self.load_files([p for p in paths if p])

    def _on_drop(self, target, value, x, y):
        if isinstance(value, Gio.File):
            p = value.get_path()
            if p:
                self.load_files([p])
                return True
        return False

    def _on_playlist_toggle(self, btn):
        self.playlist_panel.set_visible(btn.get_active())

    def _on_playlist_row_activated(self, listbox, row):
        idx = row.get_index()
        if 0 <= idx < len(self.playlist):
            self.play_index(idx)

    # ---------------------------------------------------------- helpers UI
    def _show_controls(self):
        self.controls.set_visible(True)
        if self.controls_hide_id:
            GLib.source_remove(self.controls_hide_id)
            self.controls_hide_id = 0
        if self.is_fullscreen:
            # auto-hide dupa 3 secunde in fullscreen
            self.controls_hide_id = GLib.timeout_add_seconds(3, self._hide_controls)

    def _hide_controls(self):
        if self.is_fullscreen:
            self.controls.set_visible(False)
        self.controls_hide_id = 0
        return False

    def _refresh_playlist_view(self):
        child = self.playlist_list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.playlist_list.remove(child)
            child = nxt
        for i, path in enumerate(self.playlist):
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label=os.path.basename(path), xalign=0)
            label.set_ellipsize(3)  # PANGO_ELLIPSIZE_END
            label.set_margin_top(6)
            label.set_margin_bottom(6)
            label.set_margin_start(8)
            if i == self.current_index:
                label.add_css_class("bobo-accent")
            row.set_child(label)
            self.playlist_list.append(row)

    def _refresh_recent_view(self):
        if self.playlist:
            return
        # Daca nu sunt fisiere, populeaza playlistul cu recente (afisare)
        for path in self.recent[:20]:
            if os.path.isfile(path):
                self.playlist.append(path)
        self._refresh_playlist_view()
        if self.recent:
            self.playlist_btn.set_active(True)

    def _clear_playlist(self):
        self.playlist = []
        self.current_index = -1
        self.playbin.set_state(Gst.State.NULL)
        self._refresh_playlist_view()

    def _update_recent(self, path):
        if path in self.recent:
            self.recent.remove(path)
        self.recent.insert(0, path)
        self.recent = self.recent[:20]

    def _notify(self, text):
        print("[bobo-player] %s" % text)
        try:
            GLib.spawn_command_line_async("notify-send -a BoboPlayer 'BoboPlayer' '%s'" % text.replace("'", ""))
        except Exception:
            pass

    def do_close_request(self):
        # Persista istoric + recente la inchidere
        _save_json(HISTORY_FILE, self.history)
        _save_json(RECENT_FILE, self.recent)
        self.playbin.set_state(Gst.State.NULL)
        return False


class BoboPlayerApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.win = None

    def do_activate(self):
        if not self.win:
            self.win = BoboPlayerWindow(self)
        self.win.present()

    def do_open(self, files, n_files, hint):
        self.do_activate()
        paths = [f.get_path() for f in files if f.get_path()]
        if paths:
            self.win.load_files(paths)


def main():
    if "--version" in sys.argv:
        print("BoboPlayer 1.0.0 (BOBO OS)")
        return 0
    app = BoboPlayerApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
