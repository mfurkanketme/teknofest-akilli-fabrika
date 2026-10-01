#!/usr/bin/env python3
"""
TEKNOFEST 2026 - Akilli Fabrika Sistemleri Programlama
Gorev 4: MQTT YAYINCI  (robot kolu temsil eder)

Broker olarak mosquitto kullaniyoruz. Bu program paho-mqtt ile arac/yuk
konusuna RED, GREEN veya BLUE mesajlarindan birini gonderiyor.

paho-mqtt 2.x gerekiyor, 1.x API'si ile calismiyor.

------------------------------------------------------------------------------
PAHO-MQTT 2.x FARKI
------------------------------------------------------------------------------
2.0 surumunde geri cagirma (callback) imzalari degisti ve Client kurucusu artik
hangi API surumunun kullanilacagini ACIKCA istiyor:

    1.x:  mqtt.Client()
          def on_connect(client, userdata, flags, rc)

    2.x:  mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
          def on_connect(client, userdata, flags, reason_code, properties)

CallbackAPIVersion verilmezse 2.x DeprecationWarning veriyor. 1.x imzasiyla yazilmis
kod ise sessizce hic cagrilmayan geri cagirmalarla calisir. Bu dosya bastan
2.x API'sine gore yazdik.

Kullanim:
    python yayinci.py --renk RED
    python yayinci.py --renk GREEN --broker 192.168.1.25
    python yayinci.py --dongu            # uc rengi sirayla gonder (gosterim icin)
"""
from __future__ import annotations

import argparse
import socket
import sys
import time

import paho.mqtt as paho_paketi
import paho.mqtt.client as mqtt

try:
    # CallbackAPIVersion YALNIZCA paho-mqtt 2.x'te vardir.
    # Bu import 1.x'te ImportError verir -> surum kontrolunun asil dayanagi budur.
    from paho.mqtt.enums import CallbackAPIVersion
except ImportError:
    sys.exit("HATA: paho-mqtt 2.x gerekli (CallbackAPIVersion bulunamadi).\n"
             '  pip install "paho-mqtt==2.1.0"')

KONU = "arac/yuk"                       # iki taraf da bu konuyu kullaniyor
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
    """Bu makinenin ag uzerindeki IP'si (ipconfig ciktisiyla eslesmeli)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))       # paket gonderilmez, sadece rota secilir
        return s.getsockname()[0]
    except OSError:
        return "bilinmiyor"
    finally:
        s.close()


# ------------------------------------------------------------------ callbacks
def on_connect(client, userdata, flags, reason_code, properties):
    """paho-mqtt 2.x imzasi: 5 parametre (1.x'te 4 idi)."""
    if reason_code == 0:
        print(f"[BAGLANDI] broker = {userdata['broker']}:{userdata['port']}")
    else:
        print(f"[HATA] baglanti reddedildi, kod = {reason_code}")


def on_publish(client, userdata, mid, reason_code=None, properties=None):
    print(f"[ONAY] broker mesaji aldi (mid={mid})")


def on_disconnect(client, userdata, flags, reason_code, properties):
    print(f"[KAPANDI] reason_code = {reason_code}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Gorev 4 - MQTT yayinci (robot kol)")
    ap.add_argument("--broker", default="localhost",
                    help="Broker IP'si. Ayni makinede ise localhost.")
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--renk", default="RED", choices=GECERLI_RENKLER)
    ap.add_argument("--dongu", action="store_true",
                    help="RED, GREEN, BLUE renklerini sirayla gonder")
    ap.add_argument("--aralik", type=float, default=2.0)
    a = ap.parse_args()

    surum_kontrol()
    print(f"Bu makinenin IP'si: {yerel_ip()}")
    print(f"Konu (topic)      : {KONU}")
    print("-" * 54)

    client = mqtt.Client(CallbackAPIVersion.VERSION2,
                         client_id="robot_kol_yayinci",
                         userdata={"broker": a.broker, "port": a.port})
    client.on_connect = on_connect
    client.on_publish = on_publish
    client.on_disconnect = on_disconnect

    try:
        client.connect(a.broker, a.port, keepalive=60)
    except OSError as e:
        sys.exit(f"Broker'a baglanilamadi ({a.broker}:{a.port}): {e}\n"
                 "Kontrol listesi:\n"
                 "  1) mosquitto calisiyor mu?\n"
                 "  2) mosquitto.conf icinde 'listener 1883' ve\n"
                 "     'allow_anonymous true' satirlari var mi?\n"
                 "  3) Windows Guvenlik Duvari 1883/TCP portuna izin veriyor mu?\n"
                 "  4) Iki cihaz AYNI agda mi? (ipconfig ile karsilastirin)")

    client.loop_start()
    time.sleep(0.4)                      # baglanti geri cagirmasinin donmesi icin

    try:
        renkler = GECERLI_RENKLER if a.dongu else (a.renk,)
        for renk in renkler:
            # qos=1: mesajin broker'a ulastigi ONAYLANIR (Gorev 4 kaniti icin onemli)
            sonuc = client.publish(KONU, payload=renk, qos=1, retain=False)
            try:
                sonuc.wait_for_publish(timeout=5)
            except (RuntimeError, ValueError) as e:
                sys.exit(f"Mesaj gonderilemedi ({renk}): {e}\n"
                         "Broker calisiyor mu ve baglanti kopmus olabilir mi, kontrol edin.")
            print(f"[GONDERILDI] {KONU} <- {renk}")
            if a.dongu:
                time.sleep(a.aralik)
    finally:
        time.sleep(0.4)
        client.loop_stop()
        client.disconnect()
        print("-" * 54)
        print("Yayinci kapandi.")


if __name__ == "__main__":
    main()
