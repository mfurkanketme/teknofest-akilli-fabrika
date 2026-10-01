#!/usr/bin/env python3
"""Gorev 5 kaynak etiketleri ile train/val kopyalarini son kez dogrula."""
from __future__ import annotations

import argparse
import hashlib
from collections import Counter
from pathlib import Path

from etiket_denetcisi import SINIFLAR, etiketleri_oku, goruntu_oku


def sha256(yol: Path) -> str:
    ozet = hashlib.sha256()
    with yol.open("rb") as dosya:
        for parca in iter(lambda: dosya.read(1024 * 1024), b""):
            ozet.update(parca)
    return ozet.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset")
    a = ap.parse_args()

    kok = Path(a.dataset).resolve()
    img_dir = kok / "images"
    lbl_dir = kok / "labels"
    hatalar: list[str] = []
    kaynak_gorseller = sorted(img_dir.glob("tabela_*.jpg"))
    kaynak_adlari = {p.stem for p in kaynak_gorseller}
    etiket_adlari = {p.stem for p in lbl_dir.glob("tabela_*.txt")}
    kaynak_sayaci: Counter[int] = Counter()

    if kaynak_adlari != etiket_adlari:
        for stem in sorted(kaynak_adlari - etiket_adlari):
            hatalar.append(f"Etiketi eksik goruntu: {stem}")
        for stem in sorted(etiket_adlari - kaynak_adlari):
            hatalar.append(f"Gorseli eksik etiket: {stem}")

    for gorsel_yolu in kaynak_gorseller:
        goruntu = goruntu_oku(gorsel_yolu)
        if goruntu is None:
            hatalar.append(f"Okunamayan goruntu: {gorsel_yolu.name}")
            continue
        yukseklik, genislik = goruntu.shape[:2]
        kutular, bicim_hatalari = etiketleri_oku(
            lbl_dir / f"{gorsel_yolu.stem}.txt", genislik, yukseklik
        )
        hatalar.extend(bicim_hatalari)
        kaynak_sayaci.update(kutu.sinif for kutu in kutular)

    for yol in (kok / "classes.txt", lbl_dir / "classes.txt"):
        if not yol.exists():
            hatalar.append(f"Sinif dosyasi yok: {yol}")
        elif yol.read_text(encoding="utf-8").splitlines() != SINIFLAR:
            hatalar.append(f"Sinif sirasi yanlis: {yol}")

    yaml_yolu = kok / "data.yaml"
    beklenen_path = f"path: {kok.as_posix()}"
    yaml = ""
    if not yaml_yolu.exists():
        hatalar.append("data.yaml yok")
    else:
        yaml = yaml_yolu.read_text(encoding="utf-8")
        for beklenen in (
            beklenen_path,
            "train: train/images",
            "val: val/images",
            "  0: yaya",
            "  1: tumsek",
            "  2: hemzemin",
            "  3: park",
        ):
            if beklenen not in yaml:
                hatalar.append(f"data.yaml eksik/yanlis: {beklenen}")

    bolum_adlari: dict[str, set[str]] = {}
    bolum_sayaclari: dict[str, Counter[int]] = {}
    for bolum in ("train", "val"):
        bolum_img = kok / bolum / "images"
        bolum_lbl = kok / bolum / "labels"
        gorsel_adlari = {p.stem for p in bolum_img.glob("tabela_*.jpg")}
        bolum_etiket_adlari = {p.stem for p in bolum_lbl.glob("tabela_*.txt")}
        bolum_adlari[bolum] = gorsel_adlari
        sayac: Counter[int] = Counter()
        if gorsel_adlari != bolum_etiket_adlari:
            hatalar.append(f"{bolum}: goruntu/etiket adlari eslesmiyor")

        for stem in sorted(gorsel_adlari):
            kaynak_img = img_dir / f"{stem}.jpg"
            kopya_img = bolum_img / f"{stem}.jpg"
            kaynak_lbl = lbl_dir / f"{stem}.txt"
            kopya_lbl = bolum_lbl / f"{stem}.txt"
            if sha256(kaynak_img) != sha256(kopya_img):
                hatalar.append(f"{bolum}: goruntu kopyasi farkli: {stem}")
            if sha256(kaynak_lbl) != sha256(kopya_lbl):
                hatalar.append(f"{bolum}: etiket kopyasi farkli: {stem}")
            for satir in kaynak_lbl.read_text(encoding="utf-8").splitlines():
                if satir.strip():
                    sayac[int(satir.split()[0])] += 1
        bolum_sayaclari[bolum] = sayac
        for sinif, ad in enumerate(SINIFLAR):
            if sayac[sinif] == 0:
                hatalar.append(f"{bolum}: {ad} sinifi temsil edilmiyor")

    if bolum_adlari.get("train", set()) & bolum_adlari.get("val", set()):
        hatalar.append("train ve val goruntuleri cakismiyor olmali")
    if (
        bolum_adlari.get("train", set()) | bolum_adlari.get("val", set())
    ) != kaynak_adlari:
        hatalar.append("train/val birlesimi kaynak goruntulere esit degil")

    hash_yolu = kok / "denetim" / "images_sha256.txt"
    degisen_gorseller = 0
    if hash_yolu.exists():
        kayitli = {
            satir.split("  ", 1)[1]: satir.split("  ", 1)[0]
            for satir in hash_yolu.read_text(encoding="utf-8").splitlines()
            if "  " in satir
        }
        for yol in kaynak_gorseller:
            if kayitli.get(yol.name) != sha256(yol):
                degisen_gorseller += 1
                hatalar.append(f"Kaynak goruntu degismis: {yol.name}")

    print("=" * 64)
    print(f"Kaynak goruntu : {len(kaynak_gorseller)}")
    print(f"Kaynak kutu    : {sum(kaynak_sayaci.values())}")
    print(f"Goruntu hash farki: {degisen_gorseller}")
    for sinif, ad in enumerate(SINIFLAR):
        print(
            f"{sinif} {ad:<9} toplam={kaynak_sayaci[sinif]:>3} "
            f"train={bolum_sayaclari.get('train', Counter())[sinif]:>3} "
            f"val={bolum_sayaclari.get('val', Counter())[sinif]:>3}"
        )
    print(
        f"Bolme           : train={len(bolum_adlari.get('train', set()))} "
        f"val={len(bolum_adlari.get('val', set()))}"
    )
    print(f"data.yaml path  : {'DOGRU' if yaml_yolu.exists() and beklenen_path in yaml else 'YANLIS'}")
    print(f"Nihai hata      : {len(hatalar)}")
    for hata in hatalar:
        print("  " + hata)
    print("=" * 64)
    if hatalar:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
