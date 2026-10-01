#!/usr/bin/env python3
"""
TEKNOFEST 2026 - Akilli Fabrika Sistemleri Programlama
Gorev 4: MQTT DINLEYICI  (otonom araci temsil eder)

Ikinci bilgisayarda calisiyor. Broker'in IP adresine baglanip ayni konuya
abone oluyor, gelen mesaji terminale yaziyor.

paho-mqtt 2.x API'si kullaniliyor, ayrintisi yayinci.py icinde.

Bu program Gorev 1'deki yuk_rengi_bekle() hazir eyleminin gercek karsiligi:
MQTT'den renk gelene kadar bekliyor, geldiginde donduruyor.

Kullanim:
    python dinleyici.py --broker 192.168.1.25
    python dinleyici.py --broker 192.168.1.25 --tek    # ilk mesajdan sonra cik
"""
from __future__ import annotations

import argparse
import socket
import sys
import time
from datetime import datetime

import paho.mqtt as paho_paketi
import paho.mqtt.client as mqtt

try:
    # CallbackAPIVersion YALNIZCA paho-mqtt 2.x'te vardir.
    # Bu import 1.x'te ImportError verir -> surum kontrolunun asil dayanagi budur.
    from paho.mqtt.enums import CallbackAPIVersion
except ImportError:
    sys.exit("HATA: paho-mqtt 2.x gerekli (CallbackAPIVersion bulunamadi).\n"
             '  pip install "paho-mqtt==2.1.0"')

KONU = "arac/yuk"
GECERLI_RENKLER = ("RED", "GREEN", "BLUE")


def surum_kontrol() -> None:
    """
    DIKKAT: surum bilgisi 'paho.mqtt' PAKETINDEDIR, 'paho.mqtt.client'
    MODULUNDE DEGIL. getattr(mqtt, "__version__") her zaman None doner ve
    yanlis "surum uyumsuz" hatasi uretir.
    """
    surum = getattr(paho_paketi, "__version__", "bilinmiyor")
    print(f"paho-mqtt surumu: {surum}")
    if not str(surum).startswith("2"):
        sys.exit("HATA: paho-mqtt 2.x gerekli.\n"
                 '  pip install "paho-mqtt==2.1.0"')


def yerel_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "bilinmiyor"
    finally:
        s.close()


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        print(f"[BAGLANDI] broker = {userdata['broker']}")
        client.subscribe(KONU, qos=1)          # abonelik BAGLANTIDAN SONRA yapilir
        print(f"[ABONE]    konu = {KONU}")
        print("-" * 54)
        print("Mesaj bekleniyor...  (Ctrl+C ile cikis)")
    else:
        print(f"[HATA] baglanti reddedildi, kod = {reason_code}")


def on_subscribe(client, userdata, mid, reason_code_list, properties):
    # paho-mqtt 2.x'te bu liste int DEGIL, ReasonCode nesnesi tasir.
    # int(ReasonCode) TypeError veriyor, deger .value alaninda duruyor.
    kodlar = [getattr(r, "value", r) for r in reason_code_list]
    print(f"[ABONELIK ONAYI] qos = {kodlar}")


def on_message(client, userdata, msg):
    metin = msg.payload.decode("utf-8", errors="replace").strip()
    saat = datetime.now().strftime("%H:%M:%S")

    print()
    print("=" * 54)
    print(f"  MESAJ ALINDI      {saat}")
    print(f"  Konu   : {msg.topic}")
    print(f"  Icerik : {metin}")
    if metin in GECERLI_RENKLER:
        print(f"  Durum  : GECERLI RENK -> arac {metin} park alanina gidecek")
        userdata["alinan"] = metin
    else:
        print(f"  Durum  : GECERSIZ ICERIK (beklenen: {' / '.join(GECERLI_RENKLER)})")
    print("=" * 54)

    if userdata.get("tek") and metin in GECERLI_RENKLER:
        client.disconnect()


def main() -> None:
    ap = argparse.ArgumentParser(description="Gorev 4 - MQTT dinleyici (otonom arac)")
    ap.add_argument("--broker", required=True,
                    help="Broker'in (1. bilgisayarin) IP adresi")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--tek", action="store_true",
                    help="Ilk gecerli renkten sonra cik (yuk_rengi_bekle davranisi)")
    a = ap.parse_args()

    surum_kontrol()
    print(f"Bu makinenin IP'si: {yerel_ip()}")
    print("-" * 54)

    veri = {"broker": a.broker, "tek": a.tek, "alinan": None}
    client = mqtt.Client(CallbackAPIVersion.VERSION2,
                         client_id="otonom_arac_dinleyici", userdata=veri)
    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message

    try:
        client.connect(a.broker, a.port, keepalive=60)
    except OSError as e:
        sys.exit(f"Broker'a baglanilamadi ({a.broker}:{a.port}): {e}\n"
                 "Kontrol listesi:\n"
                 "  1) Broker makinesinde mosquitto calisiyor mu?\n"
                 "  2) mosquitto.conf'ta 'listener 1883' + 'allow_anonymous true' var mi?\n"
                 "  3) Broker makinesinin guvenlik duvari 1883/TCP'ye izin veriyor mu?\n"
                 "  4) Iki cihaz AYNI agda mi? (her ikisinde ipconfig)")

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nKullanici durdurdu.")
    finally:
        client.disconnect()
        if veri["alinan"]:
            print(f"Son alinan renk: {veri['alinan']}")


if __name__ == "__main__":
    main()
