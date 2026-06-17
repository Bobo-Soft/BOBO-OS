#!/usr/bin/env python3
# =============================================================================
# BoboCoin - Portofel crypto non-custodial pentru BOBO OS (APP 32)
# GTK4. Generare wallet BIP39 (24 cuvinte), import, balanta (CoinGecko + API
# publice), primire QR, watch-only, criptare locala AES. Avertismente backup.
# =============================================================================
import os
import sys
import json
import threading
import urllib.request
import urllib.parse
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib, Gio, Gdk  # noqa: E402

# Biblioteci crypto (optionale - guarded)
try:
    from mnemonic import Mnemonic
except ImportError:
    Mnemonic = None
try:
    from eth_account import Account
    Account.enable_unaudited_hdwallet_features()
except ImportError:
    Account = None
try:
    import qrcode
except ImportError:
    qrcode = None
try:
    from cryptography.fernet import Fernet
    import base64, hashlib
except ImportError:
    Fernet = None

APP_ID = "os.bobo.Coin"
WALLET_DIR = os.path.expanduser("~/.local/share/bobo-coin")
WALLET_FILE = os.path.join(WALLET_DIR, "wallet.enc")


def fetch_prices():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum&vs_currencies=eur,usd"
        return json.loads(urllib.request.urlopen(url, timeout=8).read())
    except Exception:
        return {}


def eth_balance(addr):
    try:
        url = "https://api.blockcypher.com/v1/eth/main/addrs/%s/balance" % addr.replace("0x", "")
        data = json.loads(urllib.request.urlopen(url, timeout=8).read())
        return data.get("balance", 0) / 1e18
    except Exception:
        return None


def btc_balance(addr):
    try:
        url = "https://blockstream.info/api/address/%s" % addr
        data = json.loads(urllib.request.urlopen(url, timeout=8).read())
        funded = data.get("chain_stats", {}).get("funded_txo_sum", 0)
        spent = data.get("chain_stats", {}).get("spent_txo_sum", 0)
        return (funded - spent) / 1e8
    except Exception:
        return None


class BoboCoinWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboCoin")
        self.set_default_size(640, 620)
        self.wallet = None

        header = Gtk.HeaderBar()
        self.set_titlebar(header)
        new = Gtk.Button(label="Wallet nou")
        new.add_css_class("suggested-action")
        new.connect("clicked", lambda *a: self.create_wallet())
        header.pack_start(new)
        imp = Gtk.Button(label="Importa")
        imp.connect("clicked", lambda *a: self.import_wallet())
        header.pack_start(imp)
        watch = Gtk.Button(label="Watch-only")
        watch.connect("clicked", lambda *a: self.watch_only())
        header.pack_start(watch)
        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        refresh.connect("clicked", lambda *a: self.refresh_balance())
        header.pack_end(refresh)

        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.box.set_margin_top(18)
        self.box.set_margin_bottom(18)
        self.box.set_margin_start(20)
        self.box.set_margin_end(20)
        sw = Gtk.ScrolledWindow()
        sw.set_child(self.box)
        self.set_child(sw)

        if not (Mnemonic and Account):
            self._info("Instaleaza dependentele: pip3 install mnemonic eth-account qrcode cryptography")
        else:
            self._info("Creeaza un wallet nou sau importa unul existent.\nBOBO OS nu stocheaza niciodata cheile pe servere.")

    def _info(self, text):
        self._clear()
        lbl = Gtk.Label(label=text, xalign=0, wrap=True)
        self.box.append(lbl)

    def _clear(self):
        child = self.box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.box.remove(child)
            child = nxt

    # ----------------------------------------------------------- create
    def create_wallet(self):
        if not (Mnemonic and Account):
            return
        mnemo = Mnemonic("english")
        phrase = mnemo.generate(strength=256)  # 24 cuvinte
        acct = Account.from_mnemonic(phrase)
        self.wallet = {"mnemonic": phrase, "eth_address": acct.address, "btc_address": "", "watch": False}
        self._show_backup_warning(phrase)

    def _show_backup_warning(self, phrase):
        win = Gtk.Window(title="IMPORTANT - Salveaza fraza de recuperare", transient_for=self, modal=True)
        win.set_default_size(520, 360)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14, margin_bottom=14, margin_start=14, margin_end=14)
        warn = Gtk.Label(xalign=0, wrap=True)
        warn.set_markup("<span color='#ff5d5d' weight='bold'>ATENTIE:</span> Aceste 24 de cuvinte sunt SINGURA modalitate de recuperare a fondurilor. "
                        "Scrie-le pe hartie si pastreaza-le offline. Oricine le vede iti poate fura banii. BOBO OS NU le poate recupera.")
        box.append(warn)
        phrase_lbl = Gtk.Label(label=phrase, xalign=0, wrap=True, selectable=True)
        phrase_lbl.add_css_class("monospace")
        frame = Gtk.Frame()
        frame.set_child(phrase_lbl)
        box.append(frame)
        self.confirm_chk = Gtk.CheckButton(label="Am scris fraza intr-un loc sigur")
        box.append(self.confirm_chk)
        ok = Gtk.Button(label="Continua")
        ok.add_css_class("suggested-action")

        def do_ok(*a):
            if self.confirm_chk.get_active():
                win.close()
                self._ask_encrypt_password()
        ok.connect("clicked", do_ok)
        box.append(ok)
        win.set_child(box)
        win.present()

    def _ask_encrypt_password(self):
        win = Gtk.Window(title="Parola de criptare wallet", transient_for=self, modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        pw = Gtk.PasswordEntry()
        pw.set_show_peek_icon(True)
        box.append(Gtk.Label(label="Alege o parola pentru a cripta wallet-ul local:", xalign=0))
        box.append(pw)
        save = Gtk.Button(label="Salveaza wallet")
        save.add_css_class("suggested-action")
        save.connect("clicked", lambda *a: (self._save_wallet(pw.get_text()), win.close(), self._show_wallet()))
        box.append(save)
        win.set_child(box)
        win.present()

    def _save_wallet(self, password):
        os.makedirs(WALLET_DIR, exist_ok=True)
        data = json.dumps(self.wallet).encode()
        if Fernet and password:
            key = base64.urlsafe_b64encode(hashlib.sha256(password.encode()).digest())
            data = Fernet(key).encrypt(data)
        with open(WALLET_FILE, "wb") as fh:
            fh.write(data)
        os.chmod(WALLET_FILE, 0o600)

    # ----------------------------------------------------------- import / watch
    def import_wallet(self):
        win = Gtk.Window(title="Importa wallet", transient_for=self, modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        tv = Gtk.TextView()
        tv.set_wrap_mode(Gtk.WrapMode.WORD)
        box.append(Gtk.Label(label="Introdu fraza de recuperare (12/24 cuvinte):", xalign=0))
        box.append(tv)
        btn = Gtk.Button(label="Importa")
        btn.add_css_class("suggested-action")

        def do(*a):
            b = tv.get_buffer()
            phrase = b.get_text(b.get_start_iter(), b.get_end_iter(), True).strip()
            if Account:
                try:
                    acct = Account.from_mnemonic(phrase)
                    self.wallet = {"mnemonic": phrase, "eth_address": acct.address, "btc_address": "", "watch": False}
                    win.close()
                    self._ask_encrypt_password()
                except Exception as e:
                    self._info("Fraza invalida: %s" % e)
        btn.connect("clicked", do)
        box.append(btn)
        win.set_child(box)
        win.present()

    def watch_only(self):
        win = Gtk.Window(title="Watch-only", transient_for=self, modal=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
        eth = Gtk.Entry(placeholder_text="Adresa ETH (0x...)")
        btc = Gtk.Entry(placeholder_text="Adresa BTC")
        box.append(eth)
        box.append(btc)
        btn = Gtk.Button(label="Monitorizeaza")
        btn.add_css_class("suggested-action")
        btn.connect("clicked", lambda *a: (
            setattr(self, "wallet", {"mnemonic": "", "eth_address": eth.get_text(), "btc_address": btc.get_text(), "watch": True}),
            win.close(), self._show_wallet()))
        box.append(btn)
        win.set_child(box)
        win.present()

    # ----------------------------------------------------------- display
    def _show_wallet(self):
        self._clear()
        w = self.wallet
        if w.get("watch"):
            self.box.append(self._badge("Mod WATCH-ONLY (fara chei private)"))
        # ETH
        if w.get("eth_address"):
            self.box.append(self._coin_card("Ethereum (ETH)", w["eth_address"]))
        if w.get("btc_address"):
            self.box.append(self._coin_card("Bitcoin (BTC)", w["btc_address"]))
        self.refresh_balance()

    def _badge(self, text):
        l = Gtk.Label(xalign=0)
        l.set_markup("<span color='#ffb454' weight='bold'>%s</span>" % text)
        return l

    def _coin_card(self, name, address):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("card")
        title = Gtk.Label(xalign=0)
        title.set_markup("<b>%s</b>" % name)
        card.append(title)
        bal = Gtk.Label(label="Balanta: ...", xalign=0)
        card.append(bal)
        if name.startswith("Ethereum"):
            self.eth_bal_label = bal
        else:
            self.btc_bal_label = bal
        addr = Gtk.Label(label=address, xalign=0, selectable=True, wrap=True)
        addr.add_css_class("monospace")
        card.append(addr)
        # QR primire
        if qrcode:
            try:
                qr_path = "/tmp/bobo-coin-%s.png" % name[:3]
                qrcode.make(address).save(qr_path)
                img = Gtk.Image.new_from_file(qr_path)
                img.set_pixel_size(140)
                card.append(img)
            except Exception:
                pass
        copy = Gtk.Button(label="Copiaza adresa")
        copy.connect("clicked", lambda *a: self._copy(address))
        card.append(copy)
        return card

    def refresh_balance(self):
        if not self.wallet:
            return
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self):
        prices = fetch_prices()
        eth_eur = prices.get("ethereum", {}).get("eur", 0)
        btc_eur = prices.get("bitcoin", {}).get("eur", 0)
        if self.wallet.get("eth_address") and hasattr(self, "eth_bal_label"):
            b = eth_balance(self.wallet["eth_address"])
            txt = "Balanta: %.6f ETH  (~%.2f EUR)" % (b, b * eth_eur) if b is not None else "Balanta indisponibila"
            GLib.idle_add(self.eth_bal_label.set_text, txt)
        if self.wallet.get("btc_address") and hasattr(self, "btc_bal_label"):
            b = btc_balance(self.wallet["btc_address"])
            txt = "Balanta: %.8f BTC  (~%.2f EUR)" % (b, b * btc_eur) if b is not None else "Balanta indisponibila"
            GLib.idle_add(self.btc_bal_label.set_text, txt)

    def _copy(self, text):
        import subprocess
        try:
            p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE)
            p.communicate(text.encode())
        except Exception:
            pass
        GLib.spawn_command_line_async("notify-send 'BoboCoin' 'Adresa copiata'")


class BoboCoinApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        BoboCoinWindow(self).present()


def main():
    if "--version" in sys.argv:
        print("BoboCoin 1.0.0 (BOBO OS)")
        return 0
    return BoboCoinApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
