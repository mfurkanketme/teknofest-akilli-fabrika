"""
Dayanikli kamera acma yardimcisi.

Neden gerekli?
    cv2.VideoCapture(index, CAP_DSHOW) Windows'ta her zaman calismaz:
      - opencv-python 5.x'te DSHOW davranisi degisti,
      - bazi USB kameralar yalnizca MSMF ile acilir,
      - dahili laptop kameralari bazen index 0'da degil 1'de olur,
      - Windows gizlilik ayari "masaustu uygulamalari" icin kapaliysa
        backend "generally available but can't be used" hatasi verir.

Bu yardimci, calisan ILK kombinasyonu bulana kadar backend x index
kombinasyonlarini dener ve neyin denendigini ekrana yazar.
"""
from __future__ import annotations

import cv2


def _backendler() -> list[tuple[str, int]]:
    adaylar = [("VARSAYILAN", 0)]
    for ad in ("CAP_MSMF", "CAP_DSHOW", "CAP_V4L2", "CAP_AVFOUNDATION"):
        if hasattr(cv2, ad):
            adaylar.append((ad.replace("CAP_", ""), getattr(cv2, ad)))
    return adaylar


def kamera_ac(index: int | None = None, genislik: int = 1280,
              yukseklik: int = 720, sessiz: bool = False):
    """
    Calisan bir cv2.VideoCapture dondurur. Bulunamazsa RuntimeError firlatir.

    index verilirse yalnizca o index denenir (tum backend'lerle).
    index None ise 0..3 arasi taranir.
    """
    indeksler = [index] if index is not None else [0, 1, 2, 3]
    denenen = []

    for idx in indeksler:
        for ad, bayrak in _backendler():
            denenen.append(f"index {idx} / {ad}")
            try:
                kam = cv2.VideoCapture(idx, bayrak) if bayrak else cv2.VideoCapture(idx)
            except Exception:                       # noqa: BLE001
                continue
            if not kam.isOpened():
                kam.release()
                continue

            kam.set(cv2.CAP_PROP_FRAME_WIDTH, genislik)
            kam.set(cv2.CAP_PROP_FRAME_HEIGHT, yukseklik)

            # Acilmis gorunup kare vermeyen surucu oluyor, gercekten okuyor mu diye bak
            ok, kare = kam.read()
            if not ok or kare is None:
                kam.release()
                continue

            g = int(kam.get(cv2.CAP_PROP_FRAME_WIDTH))
            y = int(kam.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if not sessiz:
                print(f"Kamera acildi: index {idx}, backend {ad}, {g}x{y}")
            return kam

    raise RuntimeError(
        "Hicbir kamera acilamadi.\n"
        "Denenen kombinasyonlar:\n   " + "\n   ".join(denenen) + "\n\n"
        "Kontrol listesi:\n"
        "  1) Kamerayi kullanan baska bir uygulama var mi?\n"
        "     (Teams, Zoom, Windows Kamera, tarayici sekmesi, OBS)\n"
        "  2) Windows Ayarlar > Gizlilik ve guvenlik > Kamera:\n"
        "     'Uygulamalarin kameraniza erismesine izin ver' ve\n"
        "     'Masaustu uygulamalarinin kameraniza erismesine izin ver' ACIK mi?\n"
        "  3) Aygit Yoneticisi'nde kamera surucusu saglikli mi?\n"
        "  4) Harici USB kamera ise kabloyu cikarip takin.\n"
        "  5) Farkli bir index deneyin: --kamera 1 / --kamera 2"
    )


def kameralari_listele(max_index: int = 5) -> None:
    """Hangi index/backend ikililerinin calistigini tarar ve yazar."""
    print("Kamera taramasi:")
    bulundu = False
    for idx in range(max_index):
        for ad, bayrak in _backendler():
            try:
                kam = cv2.VideoCapture(idx, bayrak) if bayrak else cv2.VideoCapture(idx)
                ok = kam.isOpened() and kam.read()[0]
                if ok:
                    g = int(kam.get(cv2.CAP_PROP_FRAME_WIDTH))
                    y = int(kam.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    print(f"   [CALISIYOR] index {idx}  backend {ad:<12} {g}x{y}")
                    bulundu = True
                kam.release()
            except Exception:                       # noqa: BLE001
                pass
    if not bulundu:
        print("   Calisan kamera bulunamadi.")


if __name__ == "__main__":
    kameralari_listele()
