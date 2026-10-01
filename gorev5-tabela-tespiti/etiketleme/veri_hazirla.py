#!/usr/bin/env python3
"""
Etiketleme sonrasi DOGRULAMA + train/val bolme + data.yaml uretimi.

Neden ayri bir dogrulama adimi?
    YOLO bozuk etiket satirini sessizce atlar. 100 epoch egitimden sonra
    "model neden kotu" diye bakarken 3 saat kaybedersiniz. Once burada yakalayin.

Bolme stratejisi: STRATIFIED (tabakali).
    Rastgele bolerseniz az sayidaki bir sinif (orn. tumsek) tamamen val'e veya
    tamamen train'e dusebilir. Burada her sinifin train/val'de temsil edilmesi
    icin goruntuler "icerdigi sinif kombinasyonuna" gore gruplanip bolunur.
"""
from __future__ import annotations

import argparse
import random
import shutil
from collections import Counter, defaultdict
from pathlib import Path

SINIFLAR = ["yaya", "tumsek", "hemzemin", "park"]


def etiket_oku(txt: Path) -> tuple[list[tuple[int, float, float, float, float]], list[str]]:
    kutular, hatalar = [], []
    if not txt.exists():
        return kutular, [f"{txt.name}: dosya yok"]

    for no, satir in enumerate(txt.read_text(encoding="utf-8").splitlines(), 1):
        satir = satir.strip()
        if not satir:
            continue
        parca = satir.split()
        if len(parca) != 5:
            hatalar.append(f"{txt.name}:{no} 5 alan bekleniyor, {len(parca)} var")
            continue
        try:
            c = int(parca[0])
            x, y, w, h = (float(v) for v in parca[1:])
        except ValueError:
            hatalar.append(f"{txt.name}:{no} sayisal olmayan deger")
            continue

        if not (0 <= c < len(SINIFLAR)):
            hatalar.append(f"{txt.name}:{no} gecersiz sinif id {c}")
            continue
        if not all(0.0 <= v <= 1.0 for v in (x, y, w, h)):
            hatalar.append(f"{txt.name}:{no} koordinat 0-1 disinda: {x},{y},{w},{h}")
            continue
        if w <= 0.005 or h <= 0.005:
            hatalar.append(f"{txt.name}:{no} kutu asiri kucuk (w={w:.4f} h={h:.4f})")
            continue
        if x - w / 2 < -0.01 or x + w / 2 > 1.01 or y - h / 2 < -0.01 or y + h / 2 > 1.01:
            hatalar.append(f"{txt.name}:{no} kutu goruntu disina tasiyor")
            continue

        kutular.append((c, x, y, w, h))
    return kutular, hatalar


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset")
    ap.add_argument("--val-orani", type=float, default=0.2)
    ap.add_argument("--tohum", type=int, default=42)
    a = ap.parse_args()

    kok = Path(a.dataset).resolve()
    img_dir, lbl_dir = kok / "images", kok / "labels"
    if not img_dir.is_dir():
        raise SystemExit(f"Bulunamadi: {img_dir}")

    gorseller = sorted(p for p in img_dir.iterdir()
                       if p.suffix.lower() in (".jpg", ".jpeg", ".png"))

    tum_hatalar: list[str] = []
    sinif_sayaci: Counter[int] = Counter()
    bos_gorseller: list[str] = []
    imza_grup: dict[frozenset, list[Path]] = defaultdict(list)
    gorsel_siniflari: dict[str, frozenset[int]] = {}

    for g in gorseller:
        kutular, hatalar = etiket_oku(lbl_dir / f"{g.stem}.txt")
        tum_hatalar += hatalar
        for c, *_ in kutular:
            sinif_sayaci[c] += 1
        if not kutular:
            bos_gorseller.append(g.name)
        imza = frozenset(c for c, *_ in kutular)
        gorsel_siniflari[g.stem] = imza
        imza_grup[imza].append(g)

    print("=" * 64)
    print(f"Goruntu sayisi      : {len(gorseller)}")
    print(f"Toplam kutu         : {sum(sinif_sayaci.values())}")
    for i, ad in enumerate(SINIFLAR):
        n = sinif_sayaci[i]
        uyari = "   <-- AZ! daha fazla ornek gerekli" if n < 30 else ""
        print(f"   {i} {ad:<10}: {n:>4}{uyari}")
    print(f"Etiketsiz goruntu   : {len(bos_gorseller)} "
          f"(negatif ornek olarak KALSIN, silmeyin)")

    if tum_hatalar:
        print(f"\n!! {len(tum_hatalar)} HATA bulundu — egitimden ONCE duzeltin:")
        for h in tum_hatalar[:25]:
            print("   " + h)
        if len(tum_hatalar) > 25:
            print(f"   ... ve {len(tum_hatalar) - 25} tane daha")
        raise SystemExit(1)
    print("\nEtiket dogrulamasi: TEMIZ")

    # ---- Tabakali bolme ---------------------------------------------------
    rnd = random.Random(a.tohum)
    train, val = [], []
    for _, grup in sorted(imza_grup.items(), key=lambda kv: str(sorted(kv[0]))):
        grup = grup[:]
        rnd.shuffle(grup)
        kesim = max(1, round(len(grup) * a.val_orani)) if len(grup) > 2 else 0
        val += grup[:kesim]
        train += grup[kesim:]

    for c, ad in enumerate(SINIFLAR):
        train_var = any(c in gorsel_siniflari[g.stem] for g in train)
        val_var = any(c in gorsel_siniflari[g.stem] for g in val)
        if not train_var or not val_var:
            raise SystemExit(
                f"Tabakali bolme basarisiz: {ad} "
                f"train={train_var} val={val_var}"
            )

    # Eski kopyalar kalirsa duzeltilmis labels/ yerine bayat etiketler
    # egitime girebilir. Yalnizca dataset altindaki iki hedefi temizle.
    for ad in ("train", "val"):
        hedef_kok = (kok / ad).resolve()
        if hedef_kok.parent != kok:
            raise SystemExit(f"Guvenli olmayan bolme hedefi: {hedef_kok}")
        if hedef_kok.exists():
            shutil.rmtree(hedef_kok)

    for ad, kume in (("train", train), ("val", val)):
        (kok / ad / "images").mkdir(parents=True, exist_ok=True)
        (kok / ad / "labels").mkdir(parents=True, exist_ok=True)
        for g in kume:
            shutil.copy2(g, kok / ad / "images" / g.name)
            src = lbl_dir / f"{g.stem}.txt"
            hedef = kok / ad / "labels" / f"{g.stem}.txt"
            if src.exists():
                shutil.copy2(src, hedef)
            else:
                hedef.write_text("", encoding="utf-8")

    yaml_metni = (
        f"# TEKNOFEST 2026 - Akilli Fabrika - Gorev 5\n"
        f"path: {kok.as_posix()}\n"
        f"train: train/images\n"
        f"val: val/images\n\n"
        f"nc: {len(SINIFLAR)}\n"
        f"names:\n" + "".join(f"  {i}: {ad}\n" for i, ad in enumerate(SINIFLAR))
    )
    (kok / "data.yaml").write_text(yaml_metni, encoding="utf-8")

    print(f"\nBolme  : train={len(train)}  val={len(val)}")
    for ad, kume in (("train", train), ("val", val)):
        sayac: Counter[int] = Counter()
        for g in kume:
            kutular, _ = etiket_oku(lbl_dir / f"{g.stem}.txt")
            sayac.update(c for c, *_ in kutular)
        dagilim = ", ".join(
            f"{SINIFLAR[c]}={sayac[c]}" for c in range(len(SINIFLAR))
        )
        print(f"   {ad:<5}: {dagilim}")
    print(f"Yazildi: {kok / 'data.yaml'}")
    print("=" * 64)


if __name__ == "__main__":
    main()
