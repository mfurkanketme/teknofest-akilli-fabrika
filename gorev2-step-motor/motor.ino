/*
 * ===========================================================================
 * TEKNOFEST 2026 - Akilli Fabrika Sistemleri Programlama
 * Gorev 2: Step motor surucusu (Arduino Uno tarafi)
 * ===========================================================================
 *
 * BAGLANTI
 *   Motor surucusu : DM556 (PUL / DIR girisli)
 *   PUL            : Arduino D2
 *   DIR            : Arduino D3
 *   Mikro adim     : 1/8   -> motor 1600 adim / tur
 *   Seri hiz       : 115200 baud
 *
 * "Bu baglantiya uymayan kod test duzeneginde calistirilamaz ve
 *  degerlendirilemez."  Bu yuzden pin ve adim sayisi sabittir.
 *
 * Kutuphane: AccelStepper
 *
 * ---------------------------------------------------------------------------
 * TASARIM KARARI: KONUMUN TEK KAYNAGI ARDUINO'DUR
 * ---------------------------------------------------------------------------
 * Adim sayaci burada, AccelStepper icinde tutulur. Bilgisayar arayuzu konumu
 * KENDISI SAYMAZ, yalnizca telemetriden okur. Neden:
 *   - Bir seri baytin kaybolmasi, PC tarafinda sayilan konumu kalici olarak
 *     kaydirir. Motor gercek konumundan sapar ve "kayitli konuma git" yanlis
 *     yere gider.
 *   - Adimlari fiziksel olarak ureten taraf Arduino oldugu icin sayacin da
 *     burada durmasi gerekiyor.
 *
 * ---------------------------------------------------------------------------
 * SERI PROTOKOL  (satir tabanli ASCII, satir sonu '\n')
 * ---------------------------------------------------------------------------
 * PC -> Arduino
 *   PING                      : baglanti testi
 *   START <hiz> <yon>         : surekli don. hiz = adim/sn (>0), yon = 1 | -1
 *   STOP                      : dur (rampali)
 *   GOTO <hedef>              : verilen ADIM konumuna git
 *   POS?                      : anlik telemetri istegi
 *   SIFIRLA                   : mevcut konumu 0 kabul et
 *
 * Arduino -> PC
 *   HAZIR <adim_tur>          : acilista bir kez
 *   OK <komut>                : komut kabul edildi
 *   ERR <sebep>               : komut reddedildi
 *   T <konum> <durum> <hiz>   : telemetri (100 ms'de bir)
 *                               durum: 0=DURUYOR 1=SUREKLI 2=KONUMLANIYOR
 * ===========================================================================
 */

#include <AccelStepper.h>

// ---- Sabitler --------------------------------------------------------------
const uint8_t PUL_PIN   = 2;      // DM556 PUL
const uint8_t DIR_PIN   = 3;      // DM556 DIR
const long ADIM_TUR     = 1600;   // 1/8 mikro adim
const long SERI_HIZ     = 115200;

// ---- Hareket sinirlari ----------------------------------------------------
const float MAKS_HIZ    = 3200.0; // adim/sn  (2 tur/sn)
const float IVME        = 4000.0; // adim/sn^2 - rampa; ani kalkis adim kaybettirir
const uint16_t TELEMETRI_MS = 100;

// AccelStepper::DRIVER = PUL/DIR girisli harici surucu (DM556 tam bu tip)
AccelStepper motor(AccelStepper::DRIVER, PUL_PIN, DIR_PIN);

enum Mod : uint8_t { MOD_DURDU = 0, MOD_SUREKLI = 1, MOD_KONUM = 2 };
Mod mod = MOD_DURDU;

char tampon[48];
uint8_t tampon_uzunluk = 0;
unsigned long son_telemetri = 0;

// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(SERI_HIZ);

  motor.setMaxSpeed(MAKS_HIZ);
  motor.setAcceleration(IVME);
  motor.setCurrentPosition(0);

  // DM556 optokuplorlerinin oturmasi icin kisa bekleme
  delay(200);

  Serial.print(F("HAZIR "));
  Serial.println(ADIM_TUR);
}

// ---------------------------------------------------------------------------
void loop() {
  seri_oku();

  // Hareket uretimi: her iki mod da her dongude cagrilmali
  if (mod == MOD_SUREKLI) {
    motor.runSpeed();                 // sabit hizda surekli adim uret
  } else if (mod == MOD_KONUM) {
    if (motor.distanceToGo() == 0) {
      mod = MOD_DURDU;                // hedefe varildi
      Serial.println(F("OK VARDI"));
    } else {
      motor.run();                    // rampali konumlanma
    }
  }

  telemetri_gonder();
}

// ---------------------------------------------------------------------------
void seri_oku() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();

    if (c == '\n' || c == '\r') {
      if (tampon_uzunluk > 0) {
        tampon[tampon_uzunluk] = '\0';
        komut_isle(tampon);
        tampon_uzunluk = 0;
      }
    } else if (tampon_uzunluk < sizeof(tampon) - 1) {
      tampon[tampon_uzunluk++] = c;
    } else {
      // Tampon tasmasi: satiri at, sessiz bozulma yerine acik hata ver
      tampon_uzunluk = 0;
      Serial.println(F("ERR SATIR_UZUN"));
    }
  }
}

// ---------------------------------------------------------------------------
void komut_isle(char *satir) {
  char *komut = strtok(satir, " ");
  if (komut == NULL) return;

  // ---- PING ----
  if (strcmp(komut, "PING") == 0) {
    Serial.println(F("OK PING"));
    return;
  }

  // ---- START <hiz> <yon> ----
  if (strcmp(komut, "START") == 0) {
    char *p_hiz = strtok(NULL, " ");
    char *p_yon = strtok(NULL, " ");
    if (p_hiz == NULL || p_yon == NULL) {
      Serial.println(F("ERR START_PARAMETRE"));
      return;
    }
    float hiz = atof(p_hiz);
    int yon = atoi(p_yon);

    if (hiz <= 0.0 || hiz > MAKS_HIZ) { Serial.println(F("ERR HIZ_ARALIK")); return; }
    if (yon != 1 && yon != -1)        { Serial.println(F("ERR YON"));        return; }

    motor.setSpeed(hiz * (float)yon);   // isaret = yon
    mod = MOD_SUREKLI;
    Serial.println(F("OK START"));
    return;
  }

  // ---- STOP ----
  if (strcmp(komut, "STOP") == 0) {
    // Rampali duruş: motor.stop() mevcut ivmeye gore duracak hedefi kurar.
    // Ani kesme (setSpeed(0)) yuksek hizda adim kaybettiriyor, konum sayaci
    // gercek konumdan sapar. Bu yuzden rampa kullanilir.
    motor.stop();
    motor.setSpeed(0);
    mod = MOD_KONUM;                  // rampanin bitmesini run() tamamlar
    Serial.println(F("OK STOP"));
    return;
  }

  // ---- GOTO <hedef> ----
  if (strcmp(komut, "GOTO") == 0) {
    char *p_hedef = strtok(NULL, " ");
    if (p_hedef == NULL) { Serial.println(F("ERR GOTO_PARAMETRE")); return; }

    long hedef = atol(p_hedef);
    motor.setMaxSpeed(MAKS_HIZ);
    motor.moveTo(hedef);
    mod = MOD_KONUM;
    Serial.print(F("OK GOTO "));
    Serial.println(hedef);
    return;
  }

  // ---- POS? ----
  if (strcmp(komut, "POS?") == 0) {
    telemetri_yaz();
    return;
  }

  // ---- SIFIRLA ----
  if (strcmp(komut, "SIFIRLA") == 0) {
    if (mod != MOD_DURDU) { Serial.println(F("ERR HAREKET_HALINDE")); return; }
    motor.setCurrentPosition(0);
    Serial.println(F("OK SIFIRLA"));
    return;
  }

  Serial.print(F("ERR BILINMEYEN "));
  Serial.println(komut);
}

// ---------------------------------------------------------------------------
void telemetri_gonder() {
  unsigned long simdi = millis();
  if (simdi - son_telemetri >= TELEMETRI_MS) {
    son_telemetri = simdi;
    telemetri_yaz();
  }
}

void telemetri_yaz() {
  Serial.print(F("T "));
  Serial.print(motor.currentPosition());
  Serial.print(' ');
  Serial.print((uint8_t)mod);
  Serial.print(' ');
  Serial.println((long)motor.speed());
}
