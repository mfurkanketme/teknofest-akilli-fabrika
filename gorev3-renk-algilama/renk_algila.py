#!/usr/bin/env python3
"""
TEKNOFEST 2026 - Akilli Fabrika Sistemleri Programlama
Gorev 3: HSV renk uzayinda kirmizi, yesil ve mavi kup algilama

Kameradan gelen canli goruntuyu HSV'ye cevirip her renk icin ayri maske
cikariyoruz. Bulunan renk hem goruntu penceresinde etiket olarak hem de
terminalde RED / GREEN / BLUE seklinde gorunuyor.

Kirmizi digerlerinden farkli davraniyor, nedenini asagida anlattik.

Python 3.10, OpenCV 4.5.4 ve NumPy 1.26.4 ile yazildi.

------------------------------------------------------------------------------
KIRMIZI NEDEN AYRI ELE ALINIYOR
------------------------------------------------------------------------------
HSV'de renk tonu (Hue) dairesel bir eksen: 0 ile 179 (OpenCV olcegi) uc uca
ekli. Kirmizi tam bu birlesme noktasinda oturuyor, yani hem 0'in hemen ustunde
hem de 179'un hemen altinda kirmizi cikiyor:

    0 ...... 10 ................................ 170 ...... 179
    [kirmizi]                                     [kirmizi]

Bu yuzden tek bir cv2.inRange araligi kirmiziyi yakalayamiyor, iki ayri aralik
cikarip bitwise_or ile birlestiriyoruz. Yesil (~35-85) ve mavi (~100-130) tek
aralikta kaldigi icin onlarda bu sorun yok.

Kullanim:
    python renk_algila.py                 # kamerayi OTOMATIK tarar
    python renk_algila.py --kamera-tara   # calisan kameralari listele
    python renk_algila.py --kamera 1
    python renk_algila.py --ayar          # HSV esiklerini canli ayarlama modu

Tuslar:
    s -> ekran goruntusu kaydet (kirmizi.png / yesil.png / mavi.png)
    q -> cikis
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
import numpy as np

from kamera_ac import kamera_ac, kameralari_listele

# ---------------------------------------------------------------------------
# HSV esikleri  (OpenCV olcegi: H 0-179, S 0-255, V 0-255)
# Kirmizi IKI aralik - yukaridaki aciklamaya bakiniz.
# ---------------------------------------------------------------------------
ESIKLER: dict[str, list[tuple[np.ndarray, np.ndarray]]] = {
    "RED": [
        (np.array([  0, 120,  80]), np.array([ 10, 255, 255])),   # 0'in ustu
        (np.array([170, 120,  80]), np.array([179, 255, 255])),   # 179'un alti
    ],
    "GREEN": [
        (np.array([ 40,  90,  70]), np.array([ 85, 255, 255])),
    ],
    "BLUE": [
        (np.array([100, 110,  60]), np.array([130, 255, 255])),
    ],
}

# Ekranda gosterilecek renkler (BGR)
CIZIM_RENGI = {"RED": (0, 0, 255), "GREEN": (0, 200, 0), "BLUE": (255, 60, 0)}

MIN_ALAN = 1500          # bu alandan kucuk lekeler gurultu sayilir
CEKIRDEK = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))


def maske_uret(hsv: np.ndarray, renk: str) -> np.ndarray:
    """Bir renk icin birlesik maske uretir ve morfolojik olarak temizler."""
    maske = None
    for alt, ust in ESIKLER[renk]:
        m = cv2.inRange(hsv, alt, ust)
        maske = m if maske is None else cv2.bitwise_or(maske, m)   # <-- kirmizi icin

    # Acma (open): tek piksel gurultuyu siler
    maske = cv2.morphologyEx(maske, cv2.MORPH_OPEN, CEKIRDEK, iterations=1)
    # Kapama (close): kupun uzerindeki parlama deliklerini doldurur
    maske = cv2.morphologyEx(maske, cv2.MORPH_CLOSE, CEKIRDEK, iterations=2)
    return maske


def en_buyuk_bolge(maske: np.ndarray) -> tuple[int, tuple[int, int, int, int]] | None:
    """Maskedeki en buyuk baglantili bolgeyi dondurur: (alan, (x,y,w,h))."""
    konturlar, _ = cv2.findContours(maske, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not konturlar:
        return None
    en = max(konturlar, key=cv2.contourArea)
    alan = int(cv2.contourArea(en))
    if alan < MIN_ALAN:
        return None
    return alan, cv2.boundingRect(en)


def renk_belirle(bgr: np.ndarray):
    """
    Kareyi isler ve baskin rengi dondurur.
    Donen: (renk_adi | None, alan, kutu | None, maskeler)
    """
    # Bulaniklastirma: JPEG/sensor gurultusunu azaltir, esik kararini kararli kilar
    bulanik = cv2.GaussianBlur(bgr, (5, 5), 0)
    hsv = cv2.cvtColor(bulanik, cv2.COLOR_BGR2HSV)

    maskeler = {ad: maske_uret(hsv, ad) for ad in ESIKLER}

    en_iyi_ad, en_iyi_alan, en_iyi_kutu = None, 0, None
    for ad, m in maskeler.items():
        sonuc = en_buyuk_bolge(m)
        if sonuc and sonuc[0] > en_iyi_alan:
            en_iyi_ad, en_iyi_alan, en_iyi_kutu = ad, sonuc[0], sonuc[1]

    return en_iyi_ad, en_iyi_alan, en_iyi_kutu, maskeler


def ayar_penceresi_ac() -> None:
    """HSV esiklerini sahada canli ayarlamak icin kaydiraclar."""
    cv2.namedWindow("HSV Ayar", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("HSV Ayar", 420, 260)
    for ad, deger, ust in (("H alt", 0, 179), ("H ust", 10, 179),
                           ("S alt", 120, 255), ("V alt", 80, 255)):
        cv2.createTrackbar(ad, "HSV Ayar", deger, ust, lambda v: None)


def main() -> None:
    ap = argparse.ArgumentParser(description="Gorev 3 - HSV renk algilama")
    ap.add_argument("--kamera", type=int, default=-1,
                    help="-1 = otomatik tara (varsayilan)")
    ap.add_argument("--genislik", type=int, default=1280)
    ap.add_argument("--yukseklik", type=int, default=720)
    ap.add_argument("--ayar", action="store_true",
                    help="HSV esiklerini canli ayarlamak icin kaydirac penceresi")
    ap.add_argument("--maske-goster", action="store_true",
                    help="Maskeleri ayri pencerede goster (hata ayiklama)")
    ap.add_argument("--kamera-tara", action="store_true",
                    help="Calisan kamera index/backend ikililerini listele ve cik")
    a = ap.parse_args()

    if a.kamera_tara:
        kameralari_listele()
        return

    try:
        kam = kamera_ac(None if a.kamera < 0 else a.kamera,
                        a.genislik, a.yukseklik)
    except RuntimeError as e:
        raise SystemExit(str(e))

    if a.ayar:
        ayar_penceresi_ac()

    print("=" * 58)
    print("  GOREV 3 - HSV RENK ALGILAMA")
    print("  [s] ekran goruntusu kaydet     [q] cikis")
    print("=" * 58)

    kayit_dizini = Path(__file__).resolve().parent
    dosya_adi = {"RED": "kirmizi.png", "GREEN": "yesil.png", "BLUE": "mavi.png"}
    onceki, sabit_sayaci = None, 0

    try:
        while True:
            ok, kare = kam.read()
            if not ok:
                print("Kare alinamadi.")
                break

            if a.ayar:
                h_alt = cv2.getTrackbarPos("H alt", "HSV Ayar")
                h_ust = cv2.getTrackbarPos("H ust", "HSV Ayar")
                s_alt = cv2.getTrackbarPos("S alt", "HSV Ayar")
                v_alt = cv2.getTrackbarPos("V alt", "HSV Ayar")
                ESIKLER["RED"][0] = (np.array([h_alt, s_alt, v_alt]),
                                     np.array([h_ust, 255, 255]))

            renk, alan, kutu, maskeler = renk_belirle(kare)

            if renk:
                x, y, w, h = kutu
                cizim = CIZIM_RENGI[renk]
                cv2.rectangle(kare, (x, y), (x + w, y + h), cizim, 3)
                etiket = f"{renk}  ({alan} px)"
                (tw, th), _ = cv2.getTextSize(etiket, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
                cv2.rectangle(kare, (x, y - th - 14), (x + tw + 12, y), cizim, -1)
                cv2.putText(kare, etiket, (x + 6, y - 8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)

                # --- Terminal ciktisi ---
                # Ayni renk her karede tekrar basilmasin, sadece degisince ve arada bir bas.
                if renk != onceki or sabit_sayaci % 30 == 0:
                    print(f"TESPIT EDILEN RENK: {renk}    (alan = {alan} px)")
                sabit_sayaci = sabit_sayaci + 1 if renk == onceki else 0
                onceki = renk
            else:
                if onceki is not None:
                    print("TESPIT EDILEN RENK: -  (renk bulunamadi)")
                onceki, sabit_sayaci = None, 0
                cv2.putText(kare, "RENK YOK", (20, 46),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (60, 60, 60), 2)

            cv2.putText(kare, "TEKNOFEST 2026 - Gorev 3 - HSV Renk Algilama",
                        (16, kare.shape[0] - 18), cv2.FONT_HERSHEY_SIMPLEX,
                        0.62, (255, 255, 255), 2)
            cv2.imshow("Gorev 3 - HSV Renk Algilama", kare)

            if a.maske_goster:
                birlesik = np.hstack([maskeler["RED"], maskeler["GREEN"], maskeler["BLUE"]])
                cv2.imshow("Maskeler  [KIRMIZI | YESIL | MAVI]",
                           cv2.resize(birlesik, None, fx=0.34, fy=0.34))

            tus = cv2.waitKey(1) & 0xFF
            if tus == ord("q"):
                break
            if tus == ord("s"):
                ad = dosya_adi.get(renk, "ekran.png")
                cv2.imwrite(str(kayit_dizini / ad), kare)
                print(f"  -> kaydedildi: {ad}")
    finally:
        kam.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
