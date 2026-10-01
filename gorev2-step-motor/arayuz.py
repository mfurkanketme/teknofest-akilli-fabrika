#!/usr/bin/env python3
"""
TEKNOFEST 2026 - Akilli Fabrika Sistemleri Programlama
Gorev 2: Step motor kontrol arayuzu (tkinter + pyserial)

Arayuzdeki butonlar: baslangici kaydet, baslat, durdur, konumu kaydet,
baslangica git, kayitli konuma git.
Motorun anlik konumu (adim) ve o anki durumu ekranda gorunur.
Kaydedilen konumlar konumlar.json icinde tutulur, program kapatilip
tekrar acildiginda kayitlar durur.

Baglanti: DM556 surucu, PUL=D2, DIR=D3, 1/8 mikro adim (1600 adim/tur),
115200 baud. Pin ve zamanlama ayrintilari motor.ino icinde.

Python 3.10, pyserial 3.5, tkinter 8.6 ile yazildi.

Kullanim:
    python arayuz.py                 # portlari tarar
    python arayuz.py --port COM5
    python arayuz.py --sahte         # donanim olmadan benzetim modu
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import random
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk

# ---------------------------------------------------------------------------
# Sabit degerler
# ---------------------------------------------------------------------------
SERI_HIZ    = 115200
ADIM_TUR    = 1600          # 1/8 mikro adim
MAKS_HIZ    = 3200.0        # adim/sn - motor.ino ile AYNI olmali

JSON_DOSYA  = Path(__file__).resolve().parent / "konumlar.json"

DURUM_ADI = {0: "DURUYOR", 1: "DÖNÜYOR (sürekli)", 2: "KONUMLANIYOR"}


# ===========================================================================
#  Konum deposu - konumlar.json
# ===========================================================================
class KonumDeposu:
    """
    konumlar.json okuma/yazma.

    Yazma ATOMIKTIR: once .tmp dosyasina yazilir, sonra os.replace ile
    yerine konur. Neden: kaydetme sirasinda program kapanirsa (veya guc
    giderse) yarim yazilmis bir JSON kalirsa dosya bir daha okunamaz ve
    TUM kayitlar kaybolur. os.replace isletim sistemi seviyesinde atomiktir.
    """

    def __init__(self, yol: Path = JSON_DOSYA) -> None:
        self.yol = yol
        self.veri: dict = {"baslangic": None, "kayitli": None,
                           "adim_tur": ADIM_TUR, "guncelleme": None}
        self.yukle()

    def yukle(self) -> None:
        if not self.yol.exists():
            return
        try:
            okunan = json.loads(self.yol.read_text(encoding="utf-8"))
            if isinstance(okunan, dict):
                self.veri.update(okunan)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[UYARI] {self.yol.name} okunamadi ({e}), varsayilanlar kullanilacak.")

    def kaydet(self, anahtar: str, adim: int) -> None:
        self.veri[anahtar] = int(adim)
        self.veri["adim_tur"] = ADIM_TUR
        self.veri["guncelleme"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._yaz()

    def _yaz(self) -> None:
        gecici = self.yol.with_suffix(".json.tmp")
        gecici.write_text(json.dumps(self.veri, indent=2, ensure_ascii=False),
                          encoding="utf-8")
        os.replace(gecici, self.yol)          # atomik degistirme

    def al(self, anahtar: str):
        return self.veri.get(anahtar)


# ===========================================================================
#  SERI KATMAN
# ===========================================================================
@dataclass
class Telemetri:
    konum: int = 0
    durum: int = 0
    hiz: int = 0


class SeriBaglanti:
    """
    Arka planda seri portu okur, satirlari kuyruga koyar.

    tkinter thread-safe DEGILDIR: baska bir thread'den arayuze dokunmak
    rastgele donmalara yol acar. Bu yuzden okuma thread'i yalnizca kuyruga
    yazar, arayuz kuyruktan `after()` ile okur.
    """

    def __init__(self, port: str, kuyruk: queue.Queue) -> None:
        self.port = port
        self.kuyruk = kuyruk
        self._ser = None
        self._calisiyor = False
        self._thread: threading.Thread | None = None

    def ac(self) -> None:
        import serial                       # pyserial
        self._ser = serial.Serial(self.port, SERI_HIZ, timeout=0.2)
        # Arduino Uno DTR ile RESET atiyor, acilisin bitmesini beklemek sart.
        time.sleep(2.0)
        self._ser.reset_input_buffer()
        self._calisiyor = True
        self._thread = threading.Thread(target=self._oku, daemon=True)
        self._thread.start()

    def _oku(self) -> None:
        artik = ""
        while self._calisiyor:
            try:
                veri = self._ser.read(256).decode("ascii", errors="ignore")
            except Exception as e:                      # noqa: BLE001
                self.kuyruk.put(("HATA", f"seri okuma: {e}"))
                break
            if not veri:
                continue
            artik += veri
            while "\n" in artik:
                satir, artik = artik.split("\n", 1)
                satir = satir.strip()
                if satir:
                    self.kuyruk.put(("SATIR", satir))

    def gonder(self, komut: str) -> None:
        if self._ser is None:
            return
        try:
            self._ser.write((komut + "\n").encode("ascii"))
            self.kuyruk.put(("GIDEN", komut))
        except Exception as e:                          # noqa: BLE001
            self.kuyruk.put(("HATA", f"seri yazma: {e}"))

    def kapat(self) -> None:
        self._calisiyor = False
        if self._thread:
            self._thread.join(timeout=1.0)
        if self._ser:
            try:
                self._ser.close()
            except Exception:                           # noqa: BLE001
                pass
            self._ser = None


class SahteBaglanti:
    """
    Donanim olmadan tum arayuzu calistirmak icin motor benzetimi.

    Ayni arayuzu (ac / gonder / kapat) sundugu icin uygulama tarafi
    gercek porttan haberdar degildir. Ekran goruntusu almak, arayuzu
    denemek ve mantigi dogrulamak icin kullanilir.
    """

    def __init__(self, port: str, kuyruk: queue.Queue) -> None:
        self.kuyruk = kuyruk
        self._calisiyor = False
        self._thread: threading.Thread | None = None
        self.konum = 0.0
        self.mod = 0            # 0 durdu, 1 surekli, 2 konumlaniyor
        self.hiz = 0.0
        self.hedef = 0

    def ac(self) -> None:
        self._calisiyor = True
        self.kuyruk.put(("SATIR", f"HAZIR {ADIM_TUR}"))
        self._thread = threading.Thread(target=self._dongu, daemon=True)
        self._thread.start()

    def _dongu(self) -> None:
        periyot = 0.05
        while self._calisiyor:
            if self.mod == 1:
                self.konum += self.hiz * periyot
            elif self.mod == 2:
                fark = self.hedef - self.konum
                adim = MAKS_HIZ * periyot
                if abs(fark) <= adim:
                    self.konum = float(self.hedef)
                    self.mod, self.hiz = 0, 0.0
                    self.kuyruk.put(("SATIR", "OK VARDI"))
                else:
                    yon = 1 if fark > 0 else -1
                    self.konum += yon * adim
                    self.hiz = yon * MAKS_HIZ
            self.kuyruk.put(("SATIR",
                             f"T {int(self.konum)} {self.mod} {int(self.hiz)}"))
            time.sleep(periyot)

    def gonder(self, komut: str) -> None:
        self.kuyruk.put(("GIDEN", komut))
        p = komut.split()
        if p[0] == "PING":
            self.kuyruk.put(("SATIR", "OK PING"))
        elif p[0] == "START" and len(p) == 3:
            self.hiz = float(p[1]) * int(p[2])
            self.mod = 1
            self.kuyruk.put(("SATIR", "OK START"))
        elif p[0] == "STOP":
            self.hedef = int(self.konum)
            self.mod, self.hiz = 0, 0.0
            self.kuyruk.put(("SATIR", "OK STOP"))
        elif p[0] == "GOTO" and len(p) == 2:
            self.hedef = int(p[1])
            self.mod = 2
            self.kuyruk.put(("SATIR", f"OK GOTO {self.hedef}"))
        elif p[0] == "SIFIRLA":
            self.konum = 0.0
            self.kuyruk.put(("SATIR", "OK SIFIRLA"))

    def kapat(self) -> None:
        self._calisiyor = False
        if self._thread:
            self._thread.join(timeout=1.0)


def portlari_tara() -> list[str]:
    try:
        from serial.tools import list_ports
        return [p.device for p in list_ports.comports()]
    except ImportError:
        return []


# ===========================================================================
#  ARAYUZ
# ===========================================================================
ZEMIN   = "#eceff3"
KART    = "#ffffff"
KOYU    = "#1f2933"
VURGU   = "#2d6cdf"
YESIL   = "#1e7d43"
KIRMIZI = "#c0392b"
GRI     = "#7a8794"


class Uygulama(tk.Tk):
    def __init__(self, port: str | None, sahte: bool) -> None:
        super().__init__()
        self.title("Step Motor Kontrol Paneli")
        self.geometry("880x640")
        self.minsize(860, 620)
        self.configure(bg=ZEMIN)

        self.kuyruk: queue.Queue = queue.Queue()
        self.depo = KonumDeposu()
        self.baglanti = None
        self.sahte = sahte
        self.tel = Telemetri()
        self.son_yon = 0
        self.son_hiz = 0

        self._arayuzu_kur()
        self._portlari_yenile(secili=port)
        self.protocol("WM_DELETE_WINDOW", self._kapat)
        self.after(50, self._kuyrugu_isle)

        if port or sahte:
            self.after(300, self._baglan)

    # ------------------------------------------------------------- arayuz
    def _arayuzu_kur(self) -> None:
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        s.configure("TFrame", background=ZEMIN)
        s.configure("Kart.TFrame", background=KART, relief="flat")
        s.configure("TLabel", background=KART, foreground=KOYU)
        s.configure("Zemin.TLabel", background=ZEMIN, foreground=KOYU)
        s.configure("Baslik.TLabel", background=KART, foreground=GRI,
                    font=("Segoe UI", 9))
        s.configure("Deger.TLabel", background=KART, foreground=KOYU,
                    font=("Consolas", 30, "bold"))
        s.configure("Alt.TLabel", background=KART, foreground=GRI,
                    font=("Segoe UI", 9))
        s.configure("TButton", font=("Segoe UI", 10), padding=(6, 9))
        s.configure("Ana.TButton", font=("Segoe UI", 10, "bold"), padding=(6, 11))

        # ---------- ust: baglanti ----------
        ust = ttk.Frame(self, style="Kart.TFrame", padding=10)
        ust.pack(fill="x", padx=12, pady=(12, 8))

        ttk.Label(ust, text="Seri port:").pack(side="left")
        self.port_secim = ttk.Combobox(ust, width=16, state="readonly")
        self.port_secim.pack(side="left", padx=(6, 4))
        ttk.Button(ust, text="Yenile", width=8,
                   command=lambda: self._portlari_yenile()).pack(side="left")
        self.btn_baglan = ttk.Button(ust, text="Bağlan", width=11,
                                     command=self._baglan_kes)
        self.btn_baglan.pack(side="left", padx=6)

        self.lbl_baglanti = ttk.Label(ust, text="● Bağlı değil",
                                      foreground=KIRMIZI,
                                      font=("Segoe UI", 10, "bold"))
        self.lbl_baglanti.pack(side="left", padx=12)
        ttk.Label(ust, text=f"{SERI_HIZ} baud, DM556, PUL=D2, DIR=D3, "
                            f"{ADIM_TUR} adım/tur",
                  style="Alt.TLabel").pack(side="right")

        # ---------- orta: durum gostergeleri ----------
        orta = ttk.Frame(self, style="Kart.TFrame", padding=14)
        orta.pack(fill="x", padx=12, pady=4)
        for i in range(3):
            orta.columnconfigure(i, weight=1)

        def gosterge(sutun, baslik):
            ttk.Label(orta, text=baslik, style="Baslik.TLabel").grid(
                row=0, column=sutun, sticky="w")
            d = ttk.Label(orta, text="-", style="Deger.TLabel")
            d.grid(row=1, column=sutun, sticky="w", pady=(2, 0))
            a = ttk.Label(orta, text="", style="Alt.TLabel")
            a.grid(row=2, column=sutun, sticky="w")
            return d, a

        self.lbl_konum, self.lbl_tur = gosterge(0, "Konum (adım)")
        self.lbl_durum, self.lbl_hiz = gosterge(1, "Durum")
        self.lbl_kayit, self.lbl_kayit_alt = gosterge(2, "Kayıtlı konumlar")
        self.lbl_durum.configure(font=("Segoe UI", 17, "bold"))
        self.lbl_kayit.configure(font=("Consolas", 14, "bold"))

        # ---------- butonlar ----------
        btn_kart = ttk.Frame(self, style="Kart.TFrame", padding=12)
        btn_kart.pack(fill="x", padx=12, pady=8)
        ttk.Label(btn_kart, text="Motor kontrolü", style="Baslik.TLabel"
                  ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        for i in range(3):
            btn_kart.columnconfigure(i, weight=1)

        self.butonlar: dict[str, ttk.Button] = {}

        def buton(satir, sutun, anahtar, metin, komut, stil="TButton"):
            b = ttk.Button(btn_kart, text=metin, command=komut, style=stil)
            b.grid(row=satir, column=sutun, sticky="ew", padx=5, pady=5)
            self.butonlar[anahtar] = b
            return b

        buton(1, 0, "bas_kaydet", "Başlangıcı kaydet", self._baslangici_kaydet)
        buton(1, 1, "basla",      "Başlat",              self._basla, "Ana.TButton")
        buton(1, 2, "dur",        "Durdur",                self._dur,   "Ana.TButton")
        buton(2, 0, "kon_kaydet", "Konumu kaydet",      self._konumu_kaydet)
        buton(2, 1, "bas_git",    "Başlangıca git",     self._baslangica_git)
        buton(2, 2, "kay_git",    "Kayıtlı konuma git", self._kayitli_konuma_git)

        ek = ttk.Frame(btn_kart, style="Kart.TFrame")
        ek.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(ek, text="Konumu sıfırla", width=26,
                   command=self._sifirla).pack(side="left")
        ttk.Button(ek, text="Kayıt dosyasını aç", width=20,
                   command=self._json_goster).pack(side="left", padx=6)

        # ---------- kayit ----------
        alt = ttk.Frame(self, style="Kart.TFrame", padding=(10, 8))
        alt.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        ttk.Label(alt, text="Kayıtlar", style="Baslik.TLabel").pack(anchor="w")
        cerceve = ttk.Frame(alt, style="Kart.TFrame")
        cerceve.pack(fill="both", expand=True, pady=(4, 0))
        self.kayit = tk.Text(cerceve, height=8, bg="#f7f9fb", fg=KOYU,
                             font=("Consolas", 9), relief="flat",
                             wrap="none", state="disabled")
        kaydirici = ttk.Scrollbar(cerceve, command=self.kayit.yview)
        self.kayit.configure(yscrollcommand=kaydirici.set)
        self.kayit.pack(side="left", fill="both", expand=True)
        kaydirici.pack(side="right", fill="y")

        self._kayitli_gosterimi_tazele()
        self._butonlari_ayarla(bagli=False)

    # ------------------------------------------------------------ yardimci
    def _yaz(self, metin: str, tur: str = "bilgi") -> None:
        onek = {"bilgi": "  ", "giden": ">> ", "gelen": "<< ", "hata": "!! "}[tur]
        self.kayit.configure(state="normal")
        self.kayit.insert("end", f"[{time.strftime('%H:%M:%S')}] {onek}{metin}\n")
        self.kayit.see("end")
        self.kayit.configure(state="disabled")

    def _portlari_yenile(self, secili: str | None = None) -> None:
        portlar = portlari_tara()
        if self.sahte:
            portlar = ["SAHTE (benzetim)"] + portlar
        self.port_secim["values"] = portlar or ["(port bulunamadı)"]
        if secili and secili in portlar:
            self.port_secim.set(secili)
        elif portlar:
            self.port_secim.current(0)

    def _butonlari_ayarla(self, bagli: bool) -> None:
        durum = "normal" if bagli else "disabled"
        for b in self.butonlar.values():
            b.configure(state=durum)

    def _kayitli_gosterimi_tazele(self) -> None:
        b, k = self.depo.al("baslangic"), self.depo.al("kayitli")
        self.lbl_kayit.configure(
            text=f"{'-' if b is None else b}  /  {'-' if k is None else k}")
        self.lbl_kayit_alt.configure(text="başlangıç  /  kayıtlı  (adım)")

    # ----------------------------------------------------------- baglanti
    def _baglan_kes(self) -> None:
        self._kes() if self.baglanti else self._baglan()

    def _baglan(self) -> None:
        port = self.port_secim.get()
        if not port or port.startswith("("):
            messagebox.showwarning("Port yok", "Bağlanılacak bir seri port seçin.")
            return
        try:
            if port.startswith("SAHTE"):
                self.baglanti = SahteBaglanti(port, self.kuyruk)
            else:
                self.baglanti = SeriBaglanti(port, self.kuyruk)
            self.baglanti.ac()
        except Exception as e:                          # noqa: BLE001
            self.baglanti = None
            messagebox.showerror("Bağlantı hatası",
                                 f"{port} açılamadı:\n{e}\n\n"
                                 "Arduino IDE'nin Seri Monitörü açık olabilir, "
                                 "aynı portu iki program birden kullanamaz.")
            return

        self.lbl_baglanti.configure(text=f"● Bağlı: {port}", foreground=YESIL)
        self.btn_baglan.configure(text="Kes")
        self._butonlari_ayarla(bagli=True)
        self._yaz(f"{port} açıldı ({SERI_HIZ} baud)")
        self.baglanti.gonder("PING")

    def _kes(self) -> None:
        if self.baglanti:
            self.baglanti.gonder("STOP")
            time.sleep(0.15)
            self.baglanti.kapat()
            self.baglanti = None
        self.lbl_baglanti.configure(text="● Bağlı değil", foreground=KIRMIZI)
        self.btn_baglan.configure(text="Bağlan")
        self._butonlari_ayarla(bagli=False)
        self._yaz("bağlantı kapatıldı")

    def _gonder(self, komut: str) -> None:
        if not self.baglanti:
            messagebox.showwarning("Bağlantı yok", "Önce Arduino'ya bağlanın.")
            return
        self.baglanti.gonder(komut)

    # -------------------------------------------------- zorunlu 6 buton
    def _baslangici_kaydet(self) -> None:
        self.depo.kaydet("baslangic", self.tel.konum)
        self._kayitli_gosterimi_tazele()
        self._yaz(f"Başlangıç kaydedildi: {self.tel.konum} adım")

    def _basla(self) -> None:
        # Motor rastgele yonde ve hizda donmeye basliyor.
        # Rastgeleligi PC tarafinda uretiyoruz ki secilen deger arayuzde
        # gorunsun ve kayitlara yazilabilsin. Arduino'da uretilseydi
        # kullanici hangi hiz/yonun secildigini goremezdi.
        yon = random.choice((1, -1))
        hiz = random.randint(int(MAKS_HIZ * 0.25), int(MAKS_HIZ * 0.85))
        self.son_yon, self.son_hiz = yon, hiz
        self._gonder(f"START {hiz} {yon}")
        self._yaz(f"Başlat: yön={'saat yönü' if yon > 0 else 'ters'}, "
                  f"hız={hiz} adım/sn ({hiz/ADIM_TUR:.2f} tur/sn)")

    def _dur(self) -> None:
        self._gonder("STOP")
        self._yaz("Durdur: yavaşlayarak duruyor")

    def _konumu_kaydet(self) -> None:
        if self.tel.durum != 0:
            messagebox.showinfo(
                "Motor duruyor mu?",
                "Motor hâlâ hareket hâlinde.\n\n"
                "Konumu kaydetmeden önce motoru durdurun. "
                "Hareket sırasında kaydedilen değer, kayıt anıyla motorun "
                "gerçekten durduğu an arasında farklı olur.")
            return
        self.depo.kaydet("kayitli", self.tel.konum)
        self._kayitli_gosterimi_tazele()
        self._yaz(f"Konum kaydedildi: {self.tel.konum} adım")

    def _baslangica_git(self) -> None:
        hedef = self.depo.al("baslangic")
        if hedef is None:
            messagebox.showwarning("Kayıt yok",
                                   "Önce başlangıç konumunu kaydedin.")
            return
        self._gonder(f"GOTO {hedef}")
        self._yaz(f"Başlangıca gidiliyor, hedef {hedef} adım")

    def _kayitli_konuma_git(self) -> None:
        hedef = self.depo.al("kayitli")
        if hedef is None:
            messagebox.showwarning("Kayıt yok",
                                   "Önce KONUMU KAYDET ile bir konum kaydedin.")
            return
        self._gonder(f"GOTO {hedef}")
        self._yaz(f"Kayıtlı konuma gidiliyor, hedef {hedef} adım")

    def _sifirla(self) -> None:
        self._gonder("SIFIRLA")
        self._yaz("konum sayacı sıfırlandı")

    def _json_goster(self) -> None:
        if not JSON_DOSYA.exists():
            messagebox.showinfo("Dosya yok",
                                "Henüz kayıtlı konum yok, önce bir konum kaydedin.")
            return
        messagebox.showinfo(f"{JSON_DOSYA.name}",
                            JSON_DOSYA.read_text(encoding="utf-8"))

    # ------------------------------------------------------- kuyruk isleme
    def _kuyrugu_isle(self) -> None:
        try:
            while True:
                tur, veri = self.kuyruk.get_nowait()
                if tur == "SATIR":
                    self._satir_isle(veri)
                elif tur == "GIDEN":
                    self._yaz(veri, "giden")
                elif tur == "HATA":
                    self._yaz(veri, "hata")
        except queue.Empty:
            pass
        self.after(50, self._kuyrugu_isle)

    def _satir_isle(self, satir: str) -> None:
        if satir.startswith("T "):
            p = satir.split()
            if len(p) >= 4:
                try:
                    self.tel = Telemetri(int(p[1]), int(p[2]), int(p[3]))
                except ValueError:
                    return
                self._gostergeleri_tazele()
            return                                   # telemetri kayda yazilmaz
        self._yaz(satir, "gelen")
        if satir.startswith("HAZIR"):
            self._yaz("Arduino bağlandı, adım/tur = " + satir.split()[-1])

    def _gostergeleri_tazele(self) -> None:
        self.lbl_konum.configure(text=f"{self.tel.konum:+d}")
        self.lbl_tur.configure(
            text=f"{self.tel.konum / ADIM_TUR:+.3f} tur, "
                 f"{(self.tel.konum % ADIM_TUR) * 360 / ADIM_TUR:6.1f}°")

        ad = DURUM_ADI.get(self.tel.durum, "?")
        self.lbl_durum.configure(
            text=ad, foreground=YESIL if self.tel.durum else GRI)
        if self.tel.durum:
            self.lbl_hiz.configure(
                text=f"{abs(self.tel.hiz)} adım/sn, "
                     f"{'saat yönü' if self.tel.hiz > 0 else 'ters yön'}")
        else:
            self.lbl_hiz.configure(text="hareket yok")

    def _kapat(self) -> None:
        if self.baglanti:
            self._kes()
        self.destroy()


def main() -> None:
    ap = argparse.ArgumentParser(description="Step motor kontrol paneli")
    ap.add_argument("--port", default=None, help="Örn. COM5 veya /dev/ttyUSB0")
    ap.add_argument("--sahte", action="store_true",
                    help="Donanım olmadan benzetim modunu etkinleştir")
    a = ap.parse_args()
    Uygulama(port=a.port, sahte=a.sahte).mainloop()


if __name__ == "__main__":
    main()
