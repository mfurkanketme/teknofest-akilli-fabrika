#!/usr/bin/env python3
"""
TEKNOFEST 2026 - Akilli Fabrika Sistemleri Programlama
Gorev 5: Tabela tespiti icin YOLO egitimi

EGITIM AYARLARI:
    Taban model : yolov8l
    Epochs      : 100
    Batch size  : -1  (otomatik)
    Image size  : 640

Bu degerleri bilerek sabit yazdik, komut satirindan degistirilemiyor. Farkli
surum veya boyutla (yolov8n/s/m/x gibi) egitilen modeller kabul
edilmediginden riske girmedik.

Kullanim:
    python egitim.py --data data.yaml
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

# --- Egitim ayarlari, degistirilmiyor -------------------------------------
TABAN_MODEL = "yolov8l.pt"
EPOCHS      = 100
BATCH       = -1        # -1 = GPU belleginin %60'ina gore otomatik
IMGSZ       = 640
SINIFLAR    = ["yaya", "tumsek", "hemzemin", "park"]


def ortam_kontrol() -> str:
    try:
        import torch
    except ImportError:
        sys.exit("torch kurulu degil.  pip install ultralytics==8.4.*")

    if torch.cuda.is_available():
        ad = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"GPU : {ad}  ({vram:.1f} GB VRAM)")
        if vram < 6:
            print("UYARI: yolov8l + batch=-1 icin 6 GB'tan az VRAM risklidir.")
            print("       'CUDA out of memory' alirsaniz once diger GPU")
            print("       uygulamalarini kapatin (tarayici, oyun, Docker).")
        return "0"

    print("!! GPU BULUNAMADI - CPU ile 100 epoch yolov8l pratikte bitmez.")
    print("   Kontrol: nvidia-smi calisiyor mu? torch CUDA surumu dogru mu?")
    print("   Dogru kurulum ornegi (CUDA 12.1):")
    print("     pip install torch --index-url https://download.pytorch.org/whl/cu121")
    if input("   Yine de CPU ile devam? (e/H): ").strip().lower() != "e":
        sys.exit(1)
    return "cpu"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="data.yaml yolu")
    ap.add_argument("--proje", default="egitim_ciktisi")
    ap.add_argument("--ad", default="tabela")
    ap.add_argument("--devam", action="store_true",
                    help="Yarida kalan egitimi son checkpoint'ten surdur")
    a = ap.parse_args()

    data_yolu = Path(a.data).resolve()
    if not data_yolu.exists():
        sys.exit(f"data.yaml bulunamadi: {data_yolu}\n"
                 "Once veri_hazirla.py calistirin.")

    cihaz = ortam_kontrol()

    from ultralytics import YOLO
    import ultralytics
    print(f"ultralytics {ultralytics.__version__}  (beklenen: 8.4.x)")

    model = YOLO(TABAN_MODEL)

    print("\n" + "=" * 64)
    print(f"  model={TABAN_MODEL}  epochs={EPOCHS}  batch={BATCH}  imgsz={IMGSZ}")
    print("=" * 64 + "\n")

    model.train(
        data=str(data_yolu),
        epochs=EPOCHS,
        batch=BATCH,
        imgsz=IMGSZ,
        device=cihaz,
        project=a.proje,
        name=a.ad,
        exist_ok=True,
        resume=a.devam,
        # 100 epoch tamamlanmadan erken durma olmasin.
        patience=EPOCHS,
        seed=42,            # tekrar uretilebilirlik
        deterministic=True,
        plots=True,         # results.png -> egitim_grafik.png icin gerekli
        val=True,
    )

    # Kayit klasorunu TAHMIN ETME - ultralytics'ten sor.
    # 'project' goreli verildiginde ultralytics onu settings['runs_dir']
    # altina tasir (ornek: <cwd>\runs\detect\egitim_ciktisi\tabela).
    # Yolu elle kurmak yanlis klasore bakmaya yol acar.
    kayit = Path(model.trainer.save_dir)
    print(f"\nEgitim ciktisi: {kayit}")

    kaynak_pt = kayit / "weights" / "best.pt"
    if not kaynak_pt.exists():
        sys.exit(f"best.pt uretilmedi: {kaynak_pt}")

    # --- Teslim dosyalarini bu klasore kopyala ---------------------------
    burasi = Path(__file__).resolve().parent
    shutil.copy2(kaynak_pt, burasi / "best.pt")       # ISIM DEGISTIRILMEZ

    grafik = kayit / "results.png"
    if grafik.exists():
        shutil.copy2(grafik, burasi / "egitim_grafik.png")

    print("\n" + "=" * 64)
    print(f"  best.pt          -> {burasi / 'best.pt'}")
    print(f"  egitim_grafik.png-> {burasi / 'egitim_grafik.png'}")
    print("\n  Sonraki adim: tespit.py ile 4 tabela icin ekran goruntusu alin.")
    print("  NOT: .engine dosyasi ISTENMIYOR, yalnizca .pt teslim edilecek.")
    print("=" * 64)


if __name__ == "__main__":
    main()
