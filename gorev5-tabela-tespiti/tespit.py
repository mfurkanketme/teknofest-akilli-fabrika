#!/usr/bin/env python3
"""
TEKNOFEST 2026 - Akilli Fabrika Sistemleri Programlama
Gorev 5: Egitilmis modelle KAMERADAN CANLI tabela tespiti

Egittigimiz modelle kameradan canli tespit yapiyor. Gordugu her tabelayi
kutuyla cerceveleyip yanina sinif adini ve guven skorunu yaziyor.

Kullanim:
    python tespit.py                         # kamerayi OTOMATIK tarar
    python tespit.py --kamera-tara           # calisan kameralari listele
    python tespit.py --kamera 1 --conf 0.4
    python tespit.py --kayit                 # ekran goruntusu alma modu

Tuslar:
    s  -> anlik kareyi PNG kaydet (tabela_<sinif>.png otomatik adlandirir)
    q  -> cikis
"""
from __future__ import annotations

import argparse
import time
from collections import deque
from pathlib import Path

import cv2

from kamera_ac import kamera_ac, kameralari_listele

SINIF_RENK = {
    "yaya":     (60, 200, 60),
    "tumsek":   (40, 140, 245),
    "hemzemin": (200, 90, 60),
    "park":     (230, 160, 40),
}
VARSAYILAN_MODEL = Path(__file__).resolve().parent / "best.pt"


def imwrite_unicode(yol: Path, bgr) -> bool:
    ok, veri = cv2.imencode(yol.suffix, bgr)
    if not ok:
        return False
    veri.tofile(str(yol))
    return True


def benzersiz_yol(yol: Path) -> Path:
    if not yol.exists():
        return yol
    for i in range(1, 10_000):
        aday = yol.with_name(f"{yol.stem}_{i:03d}{yol.suffix}")
        if not aday.exists():
            return aday
    raise RuntimeError(f"Benzersiz dosya adi bulunamadi: {yol}")


class DosyaKaynagi:
    """
    cv2.VideoCapture ile ayni arayuzu sunan dosya tabanli kaynak.

    Amac: kamera hic acilmadiginda (surucu/gizlilik sorunu, kamera yok) ayni
    tespit hattini goruntu dosyasi veya video uzerinde calistirabilmek.
    tespit.py'nin geri kalani kaynagin ne oldugunu BILMEZ.

    Not: tespit.py canli tespit icin yazildi. Kamera yolu
    varsayilan ve birincil yoldur. Bu sinif yalnizca yedektir.
    """

    UZANTILAR = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

    def __init__(self, kaynak: str) -> None:
        yol = Path(kaynak)
        self._video = None
        self._goruntuler: list[Path] = []
        self._i = 0

        if yol.is_dir():
            self._goruntuler = sorted(
                p for p in yol.iterdir() if p.suffix.lower() in self.UZANTILAR)
            if not self._goruntuler:
                raise SystemExit(f"Klasorde goruntu yok: {yol}")
            self.aciklama = f"{len(self._goruntuler)} goruntu"
        elif yol.suffix.lower() in self.UZANTILAR:
            self._goruntuler = [yol]
            self.aciklama = "tek goruntu"
        else:
            self._video = cv2.VideoCapture(str(yol))
            if not self._video.isOpened():
                raise SystemExit(f"Kaynak acilamadi: {yol}")
            self.aciklama = "video"

    def read(self):
        if self._video is not None:
            return self._video.read()
        if not self._goruntuler:
            return False, None
        # Turkce karakterli yollarda cv2.imread bos doner -> imdecode kullan
        import numpy as np
        veri = np.fromfile(str(self._goruntuler[self._i]), dtype=np.uint8)
        kare = cv2.imdecode(veri, cv2.IMREAD_COLOR)
        return (kare is not None), kare

    def ilerle(self) -> None:
        if self._goruntuler:
            self._i = (self._i + 1) % len(self._goruntuler)

    def geri(self) -> None:
        if self._goruntuler:
            self._i = (self._i - 1) % len(self._goruntuler)

    @property
    def ad(self) -> str:
        return self._goruntuler[self._i].name if self._goruntuler else "video"

    def release(self) -> None:
        if self._video is not None:
            self._video.release()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=str(VARSAYILAN_MODEL))
    ap.add_argument("--kamera", type=int, default=-1,
                help="-1 = otomatik tara (varsayilan)")
    ap.add_argument("--conf", type=float, default=0.45)
    ap.add_argument("--iou", type=float, default=0.50)
    ap.add_argument("--genislik", type=int, default=1280)
    ap.add_argument("--yukseklik", type=int, default=720)
    ap.add_argument("--kayit", action="store_true",
                    help="Ekran goruntulerini ekran_goruntuleri klasorune kaydet")
    ap.add_argument("--kayit-dizini", default=None,
                    help="Ekran goruntusu kayit klasoru")
    ap.add_argument("--kamera-tara", action="store_true",
                    help="Calisan kamera index/backend ikililerini listele ve cik")
    ap.add_argument("--kaynak", default=None,
                    help="Kamera yerine goruntu dosyasi, klasor veya video kullan. "
                         "Kamera hic acilmadiginda yedek yoldur.")
    a = ap.parse_args()

    if a.kamera_tara:
        kameralari_listele()
        return

    model_yolu = Path(a.model)
    if not model_yolu.exists():
        raise SystemExit(f"Model bulunamadi: {model_yolu}\n"
                         "Once egitim.py ile modeli egitin.")

    from ultralytics import YOLO
    model = YOLO(str(model_yolu))
    isimler = model.names
    print(f"Model yuklendi: {model_yolu.name}   siniflar: {list(isimler.values())}")

    if a.kaynak:
        kam = DosyaKaynagi(a.kaynak)
        print(f"Kaynak: {a.kaynak}  ({kam.aciklama})")
        print("Sonraki goruntu icin BOSLUK, kaydetmek icin s, cikis icin q.")
    else:
        # index -1 verilirse tum indexler taranir
        try:
            kam = kamera_ac(None if a.kamera < 0 else a.kamera,
                            a.genislik, a.yukseklik)
        except RuntimeError as e:
            raise SystemExit(
                str(e) + "\n\n"
                "YEDEK YOL: kamera hic acilmiyorsa --kaynak ile dosyadan calisin:\n"
                '   python tespit.py --kaynak "..\\..\\Akilli Fabrika...\\Tabelalar"\n'
                "   python tespit.py --kaynak C:\\yol\\tabela_foto.jpg")

    # Ilk cikarim CUDA cekirdegi derledigi icin yavas kaliyor, onceden isitiyoruz.
    ok, kare = kam.read()
    if ok:
        model.predict(kare, conf=a.conf, verbose=False)

    fps_tampon: deque[float] = deque(maxlen=30)
    if a.kayit_dizini:
        kayit_dizini = Path(a.kayit_dizini)
    elif a.kayit:
        kayit_dizini = Path(__file__).resolve().parent / "ekran_goruntuleri"
    else:
        kayit_dizini = Path(__file__).resolve().parent
    kayit_dizini.mkdir(parents=True, exist_ok=True)
    print("\n[s] ekran goruntusu kaydet   [q] cikis\n")

    try:
        while True:
            t0 = time.perf_counter()
            ok, kare = kam.read()
            if not ok:
                print("Kare alinamadi.")
                break

            sonuc = model.predict(kare, conf=a.conf, iou=a.iou,
                                  imgsz=640, verbose=False)[0]

            gorulen: list[str] = []
            for kutu in sonuc.boxes:
                x1, y1, x2, y2 = kutu.xyxy[0].int().tolist()
                sid = int(kutu.cls.item())
                guven = float(kutu.conf.item())
                ad = isimler.get(sid, str(sid))
                renk = SINIF_RENK.get(ad, (0, 255, 255))

                cv2.rectangle(kare, (x1, y1), (x2, y2), renk, 2)

                etiket = f"{ad} {guven:.2f}"
                (tw, th), _ = cv2.getTextSize(etiket, cv2.FONT_HERSHEY_SIMPLEX, 0.62, 2)
                # Etiket zemini: metin acik/koyu arka planda okunmaz kalmasin
                cv2.rectangle(kare, (x1, y1 - th - 9), (x1 + tw + 6, y1), renk, -1)
                cv2.putText(kare, etiket, (x1 + 3, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 0, 0), 2)
                gorulen.append(f"{ad}({guven:.2f})")

            fps_tampon.append(1.0 / max(time.perf_counter() - t0, 1e-6))
            fps = sum(fps_tampon) / len(fps_tampon)
            cv2.putText(kare, f"FPS {fps:4.1f}   conf>{a.conf}", (12, 28),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            if gorulen:
                print("TESPIT: " + ", ".join(gorulen))

            cv2.imshow("TEKNOFEST 2026 - Tabela Tespiti", kare)

            tus = cv2.waitKey(1) & 0xFF
            if tus == ord("q"):
                break
            if isinstance(kam, DosyaKaynagi):
                if tus == 32:            # BOSLUK -> sonraki goruntu
                    kam.ilerle()
                elif tus in (ord("b"), 8):   # b veya BACKSPACE -> onceki
                    kam.geri()
            if tus == ord("s"):
                if gorulen:
                    # En yuksek guvenli sinifa gore isimlendir
                    en_iyi = max(sonuc.boxes, key=lambda b: float(b.conf.item()))
                    ad = isimler.get(int(en_iyi.cls.item()), "tespit")
                else:
                    ad = "tespit"
                hedef = benzersiz_yol(kayit_dizini / f"tabela_{ad}.png")
                if imwrite_unicode(hedef, kare):
                    print(f"  -> kaydedildi: {hedef.name}")
                else:
                    print(f"  -> kaydedilemedi: {hedef}")
    finally:
        kam.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
