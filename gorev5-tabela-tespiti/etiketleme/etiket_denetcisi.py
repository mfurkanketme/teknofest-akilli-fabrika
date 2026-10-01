#!/usr/bin/env python3
"""
Gorev 5 YOLO veri seti icin salt-okunur etiket denetimi.

Urettikleri:
  - sinif basina tum kirpintilarin mozaigi
  - HSV ile bulunan etiketsiz renk adaylari
  - buyuk kutu ve yuksek IoU listeleri
  - bicim, eslesme ve sinif dagilimi raporu

Bu betik images/ ve labels/ altindaki kaynak dosyalari degistirmez. Yalnizca
dataset/denetim klasorunu yeniden uretir.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import math
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


SINIFLAR = ["yaya", "tumsek", "hemzemin", "park"]
RENKLER = [
    (60, 200, 60),
    (40, 140, 245),
    (200, 90, 60),
    (230, 160, 40),
]
GORUNTU_UZANTILARI = {".jpg", ".jpeg", ".png"}


@dataclass(frozen=True)
class Kutu:
    dosya: Path
    satir: int
    sinif: int
    x: float
    y: float
    w: float
    h: float
    x1: int
    y1: int
    x2: int
    y2: int


def goruntu_oku(yol: Path) -> np.ndarray | None:
    veri = np.fromfile(str(yol), dtype=np.uint8)
    if veri.size == 0:
        return None
    return cv2.imdecode(veri, cv2.IMREAD_COLOR)


def goruntu_yaz(yol: Path, goruntu: np.ndarray) -> None:
    uzanti = yol.suffix.lower() or ".jpg"
    ok, veri = cv2.imencode(uzanti, goruntu)
    if not ok:
        raise RuntimeError(f"Goruntu kodlanamadi: {yol}")
    veri.tofile(str(yol))


def kutuyu_piksele_cevir(
    x: float, y: float, w: float, h: float, genislik: int, yukseklik: int
) -> tuple[int, int, int, int]:
    x1 = max(0, min(genislik - 1, round((x - w / 2) * genislik)))
    y1 = max(0, min(yukseklik - 1, round((y - h / 2) * yukseklik)))
    x2 = max(x1 + 1, min(genislik, round((x + w / 2) * genislik)))
    y2 = max(y1 + 1, min(yukseklik, round((y + h / 2) * yukseklik)))
    return x1, y1, x2, y2


def etiketleri_oku(
    etiket_yolu: Path, genislik: int, yukseklik: int
) -> tuple[list[Kutu], list[str]]:
    kutular: list[Kutu] = []
    hatalar: list[str] = []
    if not etiket_yolu.exists():
        return kutular, [f"{etiket_yolu.name}: etiket dosyasi yok"]

    for satir_no, ham in enumerate(
        etiket_yolu.read_text(encoding="utf-8").splitlines(), 1
    ):
        satir = ham.strip()
        if not satir:
            continue
        alanlar = satir.split()
        if len(alanlar) != 5:
            hatalar.append(
                f"{etiket_yolu.name}:{satir_no}: 5 alan bekleniyor, "
                f"{len(alanlar)} bulundu"
            )
            continue
        try:
            sinif = int(alanlar[0])
            x, y, w, h = (float(v) for v in alanlar[1:])
        except ValueError:
            hatalar.append(f"{etiket_yolu.name}:{satir_no}: sayisal olmayan deger")
            continue

        satir_hatalari: list[str] = []
        if sinif not in range(len(SINIFLAR)):
            satir_hatalari.append(f"sinif_id={sinif}")
        if not all(math.isfinite(v) and 0.0 <= v <= 1.0 for v in (x, y, w, h)):
            satir_hatalari.append("koordinat 0-1 disinda veya sonlu degil")
        if w <= 0.005 or h <= 0.005:
            satir_hatalari.append(f"kutu cok kucuk w={w:.6f} h={h:.6f}")
        if all(math.isfinite(v) for v in (x, y, w, h)):
            if (
                x - w / 2 < -0.01
                or x + w / 2 > 1.01
                or y - h / 2 < -0.01
                or y + h / 2 > 1.01
            ):
                satir_hatalari.append("kutu goruntu sinirini 0.01'den fazla asiyor")
        if satir_hatalari:
            hatalar.append(
                f"{etiket_yolu.name}:{satir_no}: " + "; ".join(satir_hatalari)
            )
            continue

        x1, y1, x2, y2 = kutuyu_piksele_cevir(
            x, y, w, h, genislik, yukseklik
        )
        kutular.append(
            Kutu(
                etiket_yolu,
                satir_no,
                sinif,
                x,
                y,
                w,
                h,
                x1,
                y1,
                x2,
                y2,
            )
        )
    return kutular, hatalar


def iou(a: Kutu, b: Kutu) -> float:
    ix1 = max(a.x1, b.x1)
    iy1 = max(a.y1, b.y1)
    ix2 = min(a.x2, b.x2)
    iy2 = min(a.y2, b.y2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    kesisim = (ix2 - ix1) * (iy2 - iy1)
    alan_a = (a.x2 - a.x1) * (a.y2 - a.y1)
    alan_b = (b.x2 - b.x1) * (b.y2 - b.y1)
    return kesisim / max(alan_a + alan_b - kesisim, 1)


def kirpinti_hazirla(
    goruntu: np.ndarray, kutu: tuple[int, int, int, int], boyut: int = 72
) -> np.ndarray:
    x1, y1, x2, y2 = kutu
    parca = goruntu[y1:y2, x1:x2]
    if parca.size == 0:
        return np.zeros((boyut, boyut, 3), dtype=np.uint8)
    return cv2.resize(parca, (boyut, boyut), interpolation=cv2.INTER_AREA)


def mozaik_yaz(
    yol: Path,
    oge_listesi: list[tuple[np.ndarray, str, tuple[int, int, int]]],
    sutun: int = 14,
    parca_boyutu: int = 72,
) -> None:
    altlik = 18
    if not oge_listesi:
        bos = np.full((90, 320, 3), 245, dtype=np.uint8)
        cv2.putText(
            bos,
            "Aday yok",
            (12, 48),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 0),
            2,
            cv2.LINE_AA,
        )
        goruntu_yaz(yol, bos)
        return

    satir = math.ceil(len(oge_listesi) / sutun)
    tuval = np.full(
        (satir * (parca_boyutu + altlik), sutun * parca_boyutu, 3),
        245,
        dtype=np.uint8,
    )
    for no, (parca, etiket, renk) in enumerate(oge_listesi):
        r, c = divmod(no, sutun)
        x = c * parca_boyutu
        y = r * (parca_boyutu + altlik)
        if parca.shape[:2] != (parca_boyutu, parca_boyutu):
            parca = cv2.resize(
                parca,
                (parca_boyutu, parca_boyutu),
                interpolation=cv2.INTER_AREA,
            )
        tuval[y : y + parca_boyutu, x : x + parca_boyutu] = parca
        cv2.rectangle(
            tuval,
            (x, y),
            (x + parca_boyutu - 1, y + parca_boyutu - 1),
            renk,
            2,
        )
        cv2.putText(
            tuval,
            etiket[:11],
            (x + 2, y + parca_boyutu + 13),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.32,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
    goruntu_yaz(yol, tuval)


def merkez_etiket_icinde(
    merkez: tuple[float, float], kutular: list[Kutu]
) -> bool:
    cx, cy = merkez
    return any(k.x1 <= cx <= k.x2 and k.y1 <= cy <= k.y2 for k in kutular)


def hsv_adaylari(
    goruntu: np.ndarray, kutular: list[Kutu]
) -> list[tuple[str, tuple[int, int, int, int], float, float]]:
    hsv = cv2.cvtColor(goruntu, cv2.COLOR_BGR2HSV)
    kirmizi_1 = cv2.inRange(hsv, (0, 70, 45), (10, 255, 255))
    kirmizi_2 = cv2.inRange(hsv, (168, 70, 45), (179, 255, 255))
    mavi = cv2.inRange(hsv, (95, 65, 40), (130, 255, 255))
    cekirdek = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    maskeler = {
        "kirmizi": cv2.morphologyEx(
            cv2.bitwise_or(kirmizi_1, kirmizi_2), cv2.MORPH_CLOSE, cekirdek
        ),
        "mavi": cv2.morphologyEx(mavi, cv2.MORPH_CLOSE, cekirdek),
    }

    adaylar: list[tuple[str, tuple[int, int, int, int], float, float]] = []
    for tur, maske in maskeler.items():
        konturlar, _ = cv2.findContours(
            maske, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        for kontur in konturlar:
            alan = cv2.contourArea(kontur)
            if not 2000 <= alan <= 90000:
                continue
            x, y, w, h = cv2.boundingRect(kontur)
            oran = w / max(h, 1)
            doluluk = alan / max(w * h, 1)
            if not 0.6 <= oran <= 1.8:
                continue
            if tur == "kirmizi" and not 0.34 <= doluluk <= 0.68:
                continue
            if tur == "mavi" and doluluk <= 0.72:
                continue
            if merkez_etiket_icinde((x + w / 2, y + h / 2), kutular):
                continue
            adaylar.append((tur, (x, y, x + w, y + h), alan, doluluk))
    return adaylar


def sha256(yol: Path) -> str:
    ozet = hashlib.sha256()
    with yol.open("rb") as dosya:
        for parca in iter(lambda: dosya.read(1024 * 1024), b""):
            ozet.update(parca)
    return ozet.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset")
    ap.add_argument("--cikti", default="denetim")
    a = ap.parse_args()

    kok = Path(a.dataset).resolve()
    img_dir = kok / "images"
    lbl_dir = kok / "labels"
    cikti = (kok / a.cikti).resolve()
    if not img_dir.is_dir() or not lbl_dir.is_dir():
        raise SystemExit("dataset/images veya dataset/labels bulunamadi")
    if cikti == kok or kok not in cikti.parents:
        raise SystemExit("Cikti klasoru dataset altinda olmali")
    if cikti.exists():
        shutil.rmtree(cikti)
    cikti.mkdir(parents=True)

    gorseller = sorted(
        p for p in img_dir.iterdir() if p.suffix.lower() in GORUNTU_UZANTILARI
    )
    etiketler = sorted(lbl_dir.glob("*.txt"))
    gorsel_adlari = {p.stem for p in gorseller}
    etiket_adlari = {p.stem for p in etiketler if p.name != "classes.txt"}

    bicim_hatalari: list[str] = []
    okunamayanlar: list[str] = []
    tum_kutular: list[Kutu] = []
    gorsel_kutulari: dict[str, list[Kutu]] = {}
    gorsel_cache: dict[str, np.ndarray] = {}
    boyutlar: Counter[tuple[int, int]] = Counter()

    for gorsel_yolu in gorseller:
        goruntu = goruntu_oku(gorsel_yolu)
        if goruntu is None:
            okunamayanlar.append(gorsel_yolu.name)
            continue
        yukseklik, genislik = goruntu.shape[:2]
        boyutlar[(genislik, yukseklik)] += 1
        gorsel_cache[gorsel_yolu.stem] = goruntu
        kutular, hatalar = etiketleri_oku(
            lbl_dir / f"{gorsel_yolu.stem}.txt", genislik, yukseklik
        )
        bicim_hatalari.extend(hatalar)
        gorsel_kutulari[gorsel_yolu.stem] = kutular
        tum_kutular.extend(kutular)

    # Sinif mozaikleri ve kaynak indeksi.
    indeks_yolu = cikti / "kirpinti_indeksi.csv"
    with indeks_yolu.open("w", newline="", encoding="utf-8-sig") as dosya:
        yazici = csv.writer(dosya)
        yazici.writerow(["sinif_id", "sinif", "sira", "dosya", "satir"])
        for sinif, ad in enumerate(SINIFLAR):
            ogeler: list[tuple[np.ndarray, str, tuple[int, int, int]]] = []
            sinif_kutulari = [k for k in tum_kutular if k.sinif == sinif]
            for sira, kutu in enumerate(sinif_kutulari, 1):
                goruntu = gorsel_cache[kutu.dosya.stem]
                parca = kirpinti_hazirla(
                    goruntu, (kutu.x1, kutu.y1, kutu.x2, kutu.y2)
                )
                ogeler.append(
                    (parca, f"{kutu.dosya.stem[-4:]}:{kutu.satir}", RENKLER[sinif])
                )
                yazici.writerow(
                    [sinif, ad, sira, kutu.dosya.name, kutu.satir]
                )
            mozaik_yaz(cikti / f"sinif_{sinif}_{ad}.png", ogeler)

    # Atlanmis tabela icin renk adaylari.
    hsv_kayitlari: list[
        tuple[str, str, tuple[int, int, int, int], float, float]
    ] = []
    hsv_ogeleri: list[tuple[np.ndarray, str, tuple[int, int, int]]] = []
    for stem, goruntu in gorsel_cache.items():
        for sira, (tur, kutu, alan, doluluk) in enumerate(
            hsv_adaylari(goruntu, gorsel_kutulari.get(stem, [])), 1
        ):
            hsv_kayitlari.append((stem, tur, kutu, alan, doluluk))
            hsv_ogeleri.append(
                (
                    kirpinti_hazirla(goruntu, kutu),
                    f"{stem[-4:]}:{tur[0]}{sira}",
                    (0, 0, 255) if tur == "kirmizi" else (255, 0, 0),
                )
            )
    mozaik_yaz(cikti / "atlanmis_tabela_adaylari.png", hsv_ogeleri)
    with (cikti / "atlanmis_tabela_adaylari.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as dosya:
        yazici = csv.writer(dosya)
        yazici.writerow(
            ["gorsel", "renk", "x1", "y1", "x2", "y2", "alan", "doluluk"]
        )
        for stem, tur, (x1, y1, x2, y2), alan, doluluk in hsv_kayitlari:
            yazici.writerow(
                [stem + ".jpg", tur, x1, y1, x2, y2, f"{alan:.1f}", f"{doluluk:.4f}"]
            )

    # Geometrik tutarsizliklar.
    genislikler = sorted(k.w for k in tum_kutular)
    yukseklikler = sorted(k.h for k in tum_kutular)
    medyan_w = float(np.median(genislikler)) if genislikler else 0.0
    medyan_h = float(np.median(yukseklikler)) if yukseklikler else 0.0
    buyukler = [
        k
        for k in tum_kutular
        if k.w > 1.8 * medyan_w or k.h > 1.8 * medyan_h
    ]
    iou_suphelileri: list[tuple[str, Kutu, Kutu, float]] = []
    for stem, kutular in gorsel_kutulari.items():
        for i, a_kutu in enumerate(kutular):
            for b_kutu in kutular[i + 1 :]:
                oran = iou(a_kutu, b_kutu)
                if oran > 0.30:
                    iou_suphelileri.append((stem, a_kutu, b_kutu, oran))

    buyuk_ogeler: list[tuple[np.ndarray, str, tuple[int, int, int]]] = []
    for kutu in buyukler:
        goruntu = gorsel_cache[kutu.dosya.stem]
        buyuk_ogeler.append(
            (
                kirpinti_hazirla(
                    goruntu, (kutu.x1, kutu.y1, kutu.x2, kutu.y2)
                ),
                f"{kutu.dosya.stem[-4:]}:{kutu.satir}",
                RENKLER[kutu.sinif],
            )
        )
    mozaik_yaz(cikti / "buyuk_kutu_suphelileri.png", buyuk_ogeler)

    sinif_sayaci = Counter(k.sinif for k in tum_kutular)
    rapor: list[str] = [
        "GOREV 5 ETIKET DENETIM RAPORU",
        "=" * 64,
        f"Goruntu sayisi: {len(gorseller)}",
        f"Etiket dosyasi: {len(etiket_adlari)}",
        f"Toplam kutu: {len(tum_kutular)}",
        f"Goruntu boyutlari: {dict(boyutlar)}",
        "",
        "SINIF DAGILIMI",
    ]
    for sinif, ad in enumerate(SINIFLAR):
        uyari = " UYARI: 30'un altinda" if sinif_sayaci[sinif] < 30 else ""
        rapor.append(f"  {sinif} {ad}: {sinif_sayaci[sinif]}{uyari}")

    rapor.extend(
        [
            "",
            "BICIMSEL DOGRULAMA",
            f"  Hata sayisi: {len(bicim_hatalari)}",
        ]
    )
    rapor.extend(f"  {hata}" for hata in bicim_hatalari)
    rapor.extend(f"  Okunamayan goruntu: {ad}" for ad in okunamayanlar)

    eksik_etiket = sorted(gorsel_adlari - etiket_adlari)
    fazla_etiket = sorted(etiket_adlari - gorsel_adlari)
    rapor.extend(
        [
            "",
            "ESLESME",
            f"  Etiketi eksik goruntu: {len(eksik_etiket)}",
            f"  Gorseli eksik etiket: {len(fazla_etiket)}",
        ]
    )
    rapor.extend(f"  Eksik: {ad}" for ad in eksik_etiket)
    rapor.extend(f"  Fazla: {ad}" for ad in fazla_etiket)

    rapor.extend(
        [
            "",
            "HSV ETIKETSIZ ADAYLARI",
            f"  Aday sayisi: {len(hsv_kayitlari)}",
        ]
    )
    for stem, tur, kutu, alan, doluluk in hsv_kayitlari:
        rapor.append(
            f"  {stem}.jpg {tur} kutu={kutu} alan={alan:.1f} "
            f"doluluk={doluluk:.3f}"
        )

    rapor.extend(
        [
            "",
            "GEOMETRI",
            f"  Medyan w={medyan_w:.6f} h={medyan_h:.6f}",
            f"  1.8x medyani asan kutu: {len(buyukler)}",
        ]
    )
    for kutu in buyukler:
        rapor.append(
            f"  {kutu.dosya.name}:{kutu.satir} {SINIFLAR[kutu.sinif]} "
            f"w={kutu.w:.6f} h={kutu.h:.6f}"
        )
    rapor.append(f"  IoU > 0.30 cift: {len(iou_suphelileri)}")
    for stem, a_kutu, b_kutu, oran in iou_suphelileri:
        rapor.append(
            f"  {stem}.txt:{a_kutu.satir},{b_kutu.satir} IoU={oran:.3f}"
        )

    (cikti / "denetim_raporu.txt").write_text(
        "\n".join(rapor) + "\n", encoding="utf-8"
    )
    with (cikti / "images_sha256.txt").open("w", encoding="utf-8") as dosya:
        for yol in gorseller:
            dosya.write(f"{sha256(yol)}  {yol.name}\n")

    print("\n".join(rapor[:22]))
    print(f"\nRapor ve mozaikler: {cikti}")


if __name__ == "__main__":
    main()
