#!/usr/bin/env python3
"""
BoboSign — digital document signing for BOBO OS (GTK4).
Signs PDFs (eIDAS-style) with pyhanko using a PKCS#12 (.p12/.pfx) certificate,
optional RFC-3161 TSA timestamp, and verifies existing signatures. Can generate
a self-signed test certificate for local use.
"""
import os
import sys

import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, GLib  # noqa: E402


class BoboSignWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="BoboSign")
        self.set_default_size(620, 460)
        self.pdf = None
        self.cert = None

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin_top=14, margin_bottom=14, margin_start=16, margin_end=16)
        self.set_child(box)
        title = Gtk.Label(); title.set_markup("<span size='x-large' weight='bold'>BoboSign — Semnătură digitală</span>"); title.set_xalign(0)
        box.append(title)

        self.pdf_lbl = Gtk.Label(label="Niciun PDF selectat", xalign=0)
        pdfb = Gtk.Button(label="Alege PDF…"); pdfb.connect("clicked", lambda *a: self._pick_pdf())
        box.append(pdfb); box.append(self.pdf_lbl)

        self.cert_lbl = Gtk.Label(label="Niciun certificat (.p12/.pfx)", xalign=0)
        certb = Gtk.Button(label="Alege certificat…"); certb.connect("clicked", lambda *a: self._pick_cert())
        box.append(certb); box.append(self.cert_lbl)

        self.pw = Gtk.PasswordEntry(); self.pw.set_show_peek_icon(True); box.append(Gtk.Label(label="Parolă certificat:", xalign=0)); box.append(self.pw)
        self.tsa = Gtk.CheckButton(label="Adaugă timestamp TSA (freetsa.org)"); box.append(self.tsa)

        btns = Gtk.Box(spacing=8)
        gen = Gtk.Button(label="Generează cert. test"); gen.connect("clicked", lambda *a: self._gen_cert())
        sign = Gtk.Button(label="Semnează"); sign.add_css_class("suggested-action"); sign.connect("clicked", lambda *a: self._sign())
        verify = Gtk.Button(label="Verifică semnături"); verify.connect("clicked", lambda *a: self._verify())
        for w in (gen, sign, verify):
            btns.append(w)
        box.append(btns)

        self.status = Gtk.Label(xalign=0, wrap=True); box.append(self.status)

    def _pick_pdf(self):
        d = Gtk.FileDialog(); d.open(self, None, lambda dd, r: self._set(dd, r, "pdf"))

    def _pick_cert(self):
        d = Gtk.FileDialog(); d.open(self, None, lambda dd, r: self._set(dd, r, "cert"))

    def _set(self, dialog, res, which):
        try:
            f = dialog.open_finish(res)
        except GLib.Error:
            return
        if not f:
            return
        if which == "pdf":
            self.pdf = f.get_path(); self.pdf_lbl.set_text(self.pdf)
        else:
            self.cert = f.get_path(); self.cert_lbl.set_text(self.cert)

    def _gen_cert(self):
        """Generate a self-signed PKCS#12 test cert with cryptography."""
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives.serialization import pkcs12
            import datetime
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, u"BOBO OS User")])
            cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                    .public_key(key.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(datetime.datetime.utcnow())
                    .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=825))
                    .sign(key, hashes.SHA256()))
            out = os.path.expanduser("~/bobo-sign-test.p12")
            data = pkcs12.serialize_key_and_certificates(b"bobo", key, cert, None,
                                                         serialization.BestAvailableEncryption(b"bobo"))
            open(out, "wb").write(data)
            self.cert = out; self.cert_lbl.set_text(out); self.pw.set_text("bobo")
            self.status.set_text("Certificat test creat: %s (parolă: bobo)" % out)
        except Exception as e:
            self.status.set_text("Generare cert eșuată: %s" % e)

    def _sign(self):
        if not (self.pdf and self.cert):
            self.status.set_text("Selectează PDF + certificat."); return
        try:
            from pyhanko.sign import signers
            from pyhanko.sign.timestamps import HTTPTimeStamper
            from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
            signer = signers.SimpleSigner.load_pkcs12(self.cert, passphrase=self.pw.get_text().encode())
            out = self.pdf.replace(".pdf", "-semnat.pdf")
            tsa = HTTPTimeStamper("https://freetsa.org/tsr") if self.tsa.get_active() else None
            with open(self.pdf, "rb") as inf, open(out, "wb") as outf:
                w = IncrementalPdfFileWriter(inf)
                signers.sign_pdf(w, signers.PdfSignatureMetadata(field_name="BoboSign"),
                                 signer=signer, timestamper=tsa, output=outf)
            self.status.set_text("Semnat: %s" % out)
        except Exception as e:
            self.status.set_text("Semnare eșuată: %s" % e)

    def _verify(self):
        if not self.pdf:
            self.status.set_text("Selectează un PDF."); return
        try:
            from pyhanko.pdf_utils.reader import PdfFileReader
            from pyhanko.sign.validation import validate_pdf_signature
            with open(self.pdf, "rb") as fh:
                r = PdfFileReader(fh)
                sigs = r.embedded_signatures
                if not sigs:
                    self.status.set_text("PDF-ul nu conține semnături."); return
                msgs = []
                for s in sigs:
                    status = validate_pdf_signature(s)
                    msgs.append("%s: intact=%s" % (s.field_name, status.intact))
                self.status.set_text("Semnături: " + "; ".join(msgs))
        except Exception as e:
            self.status.set_text("Verificare eșuată: %s" % e)


class BoboSignApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="os.bobo.Sign", flags=Gio_flags())
        self.win = None

    def do_activate(self):
        if not self.win:
            self.win = BoboSignWindow(self)
        self.win.present()


def Gio_flags():
    from gi.repository import Gio
    return Gio.ApplicationFlags.FLAGS_NONE


def main():
    if "--version" in sys.argv:
        print("BoboSign 1.0.0 (BOBO OS)"); return 0
    return BoboSignApp().run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
