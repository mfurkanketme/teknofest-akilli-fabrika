#!/usr/bin/env python3
"""
TABELA ON-ETIKETLEME ARACI  (Gorev 5 yardimcisi)
=================================================
Organizasyonun verdigi 129 gorsel ETIKETSIZ geldi. Elle etiketlemede zamanin
%90'i "kutuyu cizmek"e gider; sinif atamak tek tusluk istir. Bu script klasik
goruntu isleme ile TASLAK kutulari uretir, siz labelImg'de yalnizca duzeltirsiniz.

>>> Bu bir MODEL DEGILDIR. Ciktisi taslaktir ve MUTLAKA elle dogrulanmalidir.
>>> Teslim edilen best.pt, sizin dogruladiginiz etiketlerle egitilecektir.

YONTEM
------
1) HSV'de kirmizi (iki aralik) ve mavi maskeleri cikarilir.
2) Morfolojik kapama ile tabela govdesi butunlestirilir.
3) Konturlar alan / en-boy / doluluk ile elenir.
4) Sekil: approxPolyDP -> ucgen mi dortgen mi?
5) Ucgense ic piktogram analiz edilir:
      - TUMSEK   : tek, genis, alt-orta yerlesimli koyu kubbe
      - HEMZEMIN : cok sayida dikey cizgi -> yuksek dikey kenar yogunlugu
      - YAYA     : ince uzun insan figuru + alt tarafta cizgiler
6) Mavi dortgense "P" ile "T kavsak" ayrimi yapilir (beyaz piksel dagilimi).

Kullanim:
    python on_etiketle.py --girdi ../../"...Tabelalar" --cikti dataset
    python on_etiketle.py --girdi ... --cikti dataset --onizleme
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import cv2
import numpy as np

SINIFLAR = ["yaya", "tumsek", "hemzemin", "park"]   # data.yaml ile AYNI sira

# --- HSV esikleri -----------------------------------------------------------
# Kirmizi HSV'de 0 derecenin iki yaninda kaldigi icin IKI aralik gerekir.
KIRMIZI_1 = (np.array([0, 90, 70]),   np.array([10, 255, 255]))
KIRMIZI_2 = (np.array([168, 90, 70]), np.array([180, 255, 255]))
MAVI      = (np.array([95, 110, 60]), np.array([130, 255, 255]))

MIN_ALAN = 900          # 1280x800 goruntude cok kucuk lekeler tabela degildir
MAX_ALAN = 90_000


def imread_unicode(yol: Path) -> np.ndarray | None:
    veri = np.fromfile(str(yol), dtype=np.uint8)
    if veri.size == 0:
        return None
    return cv2.imdecode(veri, cv2.IMREAD_COLOR)


def imwrite_unicode(yol: Path, bgr: np.ndarray) -> bool:
    ok, veri = cv2.imencode(yol.suffix, bgr)
    if not ok:
        return False
    veri.tofile(str(yol))
    return True


def _maske(hsv: np.ndarray, renk: str) -> np.ndarray:
    if renk == "kirmizi":
        m = cv2.inRange(hsv, *KIRMIZI_1) | cv2.inRange(hsv, *KIRMIZI_2)
    else:
        m = cv2.inRange(hsv, *MAVI)
    cekirdek = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cekirdek, iterations=1)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cekirdek, iterations=3)
    return m


def _ucgen_ic_analiz(bgr: np.ndarray) -> tuple[str, float]:
    """
    Ucgen tabelanin ICINDEKI koyu piktogrami siniflandirir.
    Donen: (sinif_adi, guven 0..1)
    """
    h, w = bgr.shape[:2]
    if h < 12 or w < 12:
        return "yaya", 0.0

    # Ucgenin ic bolgesi: kenardaki kirmizi cerceveyi disarida birak
    ic = bgr[int(h * 0.42):int(h * 0.92), int(w * 0.22):int(w * 0.78)]
    if ic.size == 0:
        return "yaya", 0.0

    gri = cv2.cvtColor(ic, cv2.COLOR_BGR2GRAY)
    gri = cv2.GaussianBlur(gri, (3, 3), 0)
    _, koyu = cv2.threshold(gri, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    ih, iw = koyu.shape
    toplam = float(ih * iw)
    if toplam == 0:
        return "yaya", 0.0

    doluluk = float(np.count_nonzero(koyu)) / toplam

    # --- Ozellik 1: dikey cizgi yogunlugu (hemzemin gecidin parmaklik deseni)
    sobel_x = cv2.Sobel(koyu, cv2.CV_32F, 1, 0, ksize=3)
    dikey_kenar = float(np.count_nonzero(np.abs(sobel_x) > 200)) / toplam

    # --- Ozellik 2: baglantili bilesen sayisi
    n, _, istat, _ = cv2.connectedComponentsWithStats(koyu, connectivity=8)
    anlamli = [i for i in range(1, n) if istat[i, cv2.CC_STAT_AREA] > toplam * 0.01]

    # --- Ozellik 3: kutlenin dikey agirlik merkezi (tumsekte ASAGIDA)
    ys, xs = np.nonzero(koyu)
    if len(ys) == 0:
        return "yaya", 0.0
    merkez_y = float(ys.mean()) / ih

    # --- Ozellik 4: en buyuk bilesenin en-boy orani (tumsek GENIS ve BASIK)
    if anlamli:
        eb = max(anlamli, key=lambda i: istat[i, cv2.CC_STAT_AREA])
        bw, bh = istat[eb, cv2.CC_STAT_WIDTH], istat[eb, cv2.CC_STAT_HEIGHT]
        en_boy = bw / max(bh, 1)
    else:
        en_boy = 1.0

    # --- Karar agaci ------------------------------------------------------
    # HEMZEMIN: parmaklik -> cok dikey kenar, birden fazla ince bilesen
    if dikey_kenar > 0.055 and len(anlamli) >= 3:
        return "hemzemin", 0.70

    # TUMSEK: tek genis basik kubbe, kutle asagida
    if en_boy > 1.6 and merkez_y > 0.55 and len(anlamli) <= 2:
        return "tumsek", 0.75

    # YAYA: dik figur (en_boy < 1), doluluk orta
    if en_boy < 1.0 and 0.05 < doluluk < 0.45:
        return "yaya", 0.65

    # Ayirt edilemedi -> en olasi tahmin, dusuk guven
    return ("tumsek" if merkez_y > 0.6 else "yaya"), 0.30


def _mavi_ic_analiz(bgr: np.ndarray) -> tuple[str | None, float]:
    """
    Mavi dortgen: 'P' (park) mi, 'T kavsak' mi?
    P harfi tek ve SOLA yatkin/dikey; T kavsak isareti YATAY bir cubuk icerir.
    """
    h, w = bgr.shape[:2]
    if h < 14 or w < 14:
        return None, 0.0

    ic = bgr[int(h * 0.15):int(h * 0.85), int(w * 0.15):int(w * 0.85)]
    if ic.size == 0:
        return None, 0.0

    hsv = cv2.cvtColor(ic, cv2.COLOR_BGR2HSV)
    # Mavi zemin uzerindeki BEYAZ pikseller = piktogram
    beyaz = cv2.inRange(hsv, np.array([0, 0, 165]), np.array([180, 70, 255]))

    ih, iw = beyaz.shape
    toplam = float(ih * iw)
    oran = float(np.count_nonzero(beyaz)) / max(toplam, 1)
    if oran < 0.03:
        return None, 0.0

    n, _, istat, _ = cv2.connectedComponentsWithStats(beyaz, connectivity=8)
    anlamli = [i for i in range(1, n) if istat[i, cv2.CC_STAT_AREA] > toplam * 0.02]
    if not anlamli:
        return None, 0.0

    eb = max(anlamli, key=lambda i: istat[i, cv2.CC_STAT_AREA])
    bw, bh = istat[eb, cv2.CC_STAT_WIDTH], istat[eb, cv2.CC_STAT_HEIGHT]
    en_boy = bw / max(bh, 1)

    # 'P' dikey uzanir (en_boy < 1). 'T' yatay cubugu yuzunden genis olur.
    if en_boy < 0.95:
        return "park", 0.70
    return None, 0.0        # T kavsak -> etiketlenmeyecek (dagitici nesne)


def kareleri_bul(bgr: np.ndarray) -> list[tuple[str, float, int, int, int, int]]:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    bulunan = []

    for renk in ("kirmizi", "mavi"):
        m = _maske(hsv, renk)
        konturlar, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for k in konturlar:
            alan = cv2.contourArea(k)
            if not (MIN_ALAN < alan < MAX_ALAN):
                continue

            x, y, w, h = cv2.boundingRect(k)
            en_boy = w / max(h, 1)
            if not (0.45 < en_boy < 2.2):
                continue                       # tabelalar kabaca kare cerceveli

            cevre = cv2.arcLength(k, True)
            kose = cv2.approxPolyDP(k, 0.035 * cevre, True)
            doluluk = alan / max(w * h, 1)

            kirp = bgr[y:y + h, x:x + w]

            if renk == "kirmizi":
                # Ucgen: doluluk ~0.5 (ucgen alani / kutu alani), 3-5 kose
                # Yuvarlak yasak tabelasi: doluluk ~0.78 -> ELENIR
                if not (0.34 < doluluk < 0.68):
                    continue
                if not (3 <= len(kose) <= 6):
                    continue
                sinif, guven = _ucgen_ic_analiz(kirp)
            else:
                if doluluk < 0.72:             # dortgen dolu olmali
                    continue
                sinif, guven = _mavi_ic_analiz(kirp)
                if sinif is None:
                    continue

            bulunan.append((sinif, guven, x, y, w, h))

    return bulunan


def yolo_satiri(sinif: str, x: int, y: int, w: int, h: int,
                gw: int, gh: int) -> str:
    cx = (x + w / 2) / gw
    cy = (y + h / 2) / gh
    return f"{SINIFLAR.index(sinif)} {cx:.6f} {cy:.6f} {w / gw:.6f} {h / gh:.6f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--girdi", required=True, help="Tabelalar klasoru")
    ap.add_argument("--cikti", default="dataset", help="Cikti klasoru")
    ap.add_argument("--onizleme", action="store_true",
                    help="Kutulari cizilmis JPG'ler de uret (gozle kontrol icin)")
    a = ap.parse_args()

    girdi = Path(a.girdi)
    cikti = Path(a.cikti)
    (cikti / "images").mkdir(parents=True, exist_ok=True)
    (cikti / "labels").mkdir(parents=True, exist_ok=True)
    if a.onizleme:
        (cikti / "onizleme").mkdir(parents=True, exist_ok=True)

    dosyalar = sorted(p for p in girdi.iterdir()
                      if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if not dosyalar:
        raise SystemExit(f"Goruntu bulunamadi: {girdi}")

    sayac = {s: 0 for s in SINIFLAR}
    dusuk_guven = []
    kutusuz = []
    okunamayan = []

    for i, p in enumerate(dosyalar):
        bgr = imread_unicode(p)
        if bgr is None:
            okunamayan.append(p.name)
            continue
        gh, gw = bgr.shape[:2]

        # Dosya adlarini normalize et: bosluk/parantez YOLO'da sorun cikarir
        yeni_ad = f"tabela_{i:04d}"
        shutil.copy2(p, cikti / "images" / f"{yeni_ad}{p.suffix.lower()}")

        kutular = kareleri_bul(bgr)
        satirlar = []
        for sinif, guven, x, y, w, h in kutular:
            satirlar.append(yolo_satiri(sinif, x, y, w, h, gw, gh))
            sayac[sinif] += 1
            if guven < 0.5:
                dusuk_guven.append(yeni_ad)

        (cikti / "labels" / f"{yeni_ad}.txt").write_text(
            "\n".join(satirlar), encoding="utf-8")

        if not kutular:
            kutusuz.append(yeni_ad)

        if a.onizleme:
            gorsel = bgr.copy()
            for sinif, guven, x, y, w, h in kutular:
                renk = (0, 255, 0) if guven >= 0.5 else (0, 165, 255)
                cv2.rectangle(gorsel, (x, y), (x + w, y + h), renk, 2)
                cv2.putText(gorsel, f"{sinif} {guven:.2f}", (x, max(y - 6, 12)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.55, renk, 2)
            imwrite_unicode(cikti / "onizleme" / f"{yeni_ad}.jpg", gorsel)

    print("=" * 62)
    print(f"Islenen goruntu      : {len(dosyalar)}")
    if okunamayan:
        print(f"Okunamayan goruntu   : {len(okunamayan)}")
        print("   " + ", ".join(okunamayan[:15]) + ("..." if len(okunamayan) > 15 else ""))
    print(f"Uretilen taslak kutu : {sum(sayac.values())}")
    for s in SINIFLAR:
        print(f"   {s:<10}: {sayac[s]}")
    print(f"Dusuk guvenli kutu   : {len(set(dusuk_guven))} goruntude "
          f"-> ONCE BUNLARI KONTROL EDIN")
    print(f"Hic kutu bulunamayan : {len(kutusuz)} goruntu "
          f"-> ELLE etiketlenmeli")
    if kutusuz:
        print("   " + ", ".join(kutusuz[:15]) + ("..." if len(kutusuz) > 15 else ""))
    print("=" * 62)
    print("SONRAKI ADIM: labelImg ile kutulari duzeltin.")
    print(f"   labelImg {cikti/'images'} {cikti/'classes.txt'} {cikti/'labels'}")

    icerik = "\n".join(SINIFLAR) + "\n"
    (cikti / "classes.txt").write_text(icerik, encoding="utf-8")
    (cikti / "labels" / "classes.txt").write_text(icerik, encoding="utf-8")


if __name__ == "__main__":
    main()
