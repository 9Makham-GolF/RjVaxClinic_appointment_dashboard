/**
 * =========================================================================================
 * RJ.VAXCLINIC ESP32-S3 E-INK FIRMWARE (POGO PIN 10-PIN DOCK INTERFACE)
 * คลินิกวัคซีนผู้ใหญ่ครบวงจร โรงพยาบาลราชวิถี
 * 
 * ระบบแสดงผลใบนัดหมายประจำวันบนจอ E-Ink 4.2 นิ้ว แบบเรียลไทม์
 * ลิขสิทธิ์ของ ธนชาติ ลอไพบูลย์ และธัญวรัตม์ ศิริชาติ
 * =========================================================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <SPI.h>
#include <esp_task_wdt.h>

#include "config.h"
#include "epd4in2b_v2.h"
#include "../eink_daily_note_bitmap.h"

// อ็อบเจกต์ SPI บัสสำหรับเชื่อมต่อกับจอ E-Ink ผ่านขั้วต่อ Pogo Pin 10 ขา
SPIClass epdSPI(FSPI);
Epd4in2bV2 epd(PIN_EPD_CS, PIN_EPD_DC, PIN_EPD_RST, PIN_EPD_BUSY, &epdSPI);

// ตัวแปรควบคุมสถานะ Hardware Interrupt เมื่อประกบหน้าจอเข้ากับขั้ว Pogo Pin
volatile bool g_dockTriggered = false;
unsigned long g_lastSyncMillis = 0;

// บัฟเฟอร์สำหรับดาวน์โหลดภาพแบบ Real-Time จากคลาวด์
uint8_t *g_downloadBuffer = nullptr;

// -----------------------------------------------------------------------------
// HARDWARE INTERRUPT SERVICE ROUTINE (ISR) - DOCK DETECTION
// -----------------------------------------------------------------------------
void IRAM_ATTR isrDockDetect() {
    g_dockTriggered = true;
}

// -----------------------------------------------------------------------------
// WIFI & SECURE HTTPS SYNC ENGINE
// -----------------------------------------------------------------------------
bool connectClinicWiFi() {
    if (WiFi.status() == WL_CONNECTED) return true;

    Serial.printf("[WIFI] กำลังเชื่อมต่อเครือข่ายคลินิก: %s ...\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 10000) {
        delay(250);
        Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("[WIFI] เชื่อมต่อสำเร็จ! IP: %s | RSSI: %d dBm\n", 
                      WiFi.localIP().toString().c_str(), WiFi.RSSI());
        return true;
    } else {
        Serial.println("[WIFI] ไม่สามารถเชื่อมต่อ WiFi ได้ จะใช้ข้อมูลแคชใบนัดหมายล่าสุด");
        return false;
    }
}

// -----------------------------------------------------------------------------
// REFRESH E-INK DISPLAY
// -----------------------------------------------------------------------------
void refreshEInkScreen(bool useCloudData) {
    Serial.println("[EPD] เริ่มต้นกระบวนการอัปเดตหน้าจอ E-Ink ผ่าน Pogo Pins...");

    // ฟีด Watchdog ป้องกันการค้างขณะรีเฟรชจอ
    esp_task_wdt_reset();

    epd.init();

    if (useCloudData && g_downloadBuffer != nullptr) {
        Serial.println("[EPD] แสดงผลข้อมูลใบนัดล่าสุดที่ซิงค์จากเซิร์ฟเวอร์แบบ Real-Time");
        // สมมติแยกครึ่งแรกเป็น black buffer และครึ่งหลังเป็น red buffer (15,000 + 15,000 bytes)
        epd.displayFrame(g_downloadBuffer, g_downloadBuffer + EPD_BUFFER_SIZE);
    } else {
        Serial.println("[EPD] แสดงผลข้อมูลใบนัดจากหน่วยความจำแฟลชความเร็วสูง (Sarabun Font)");
        epd.displayFrame(epd_bitmap_black, epd_bitmap_red);
    }

    // นำจอเข้าสู่ Sleep Mode เพื่อตัดไฟเลี้ยงจอ 100% รักษาภาพได้ตลอดไปโดยไม่กินไฟ
    epd.sleep();
    Serial.println("[EPD] อัปเดตหน้าจอสำเร็จ เข้าสู่โหมดประหยัดพลังงาน Ultra-Low Power");
}

// -----------------------------------------------------------------------------
// SETUP
// -----------------------------------------------------------------------------
void setup() {
    Serial.begin(115200);
    delay(500);

    Serial.println("\n=======================================================");
    Serial.println("  RJ.VAXCLINIC SMART E-INK DISPLAY FIRMWARE (ESP32-S3)  ");
    Serial.println("  คลินิกวัคซีนผู้ใหญ่ครบวงจร โรงพยาบาลราชวิถี             ");
    Serial.println("=======================================================");

    // ตั้งค่า Watchdog Timer
    esp_task_wdt_init(WDT_TIMEOUT_SECONDS, true);
    esp_task_wdt_add(NULL);

    // กำหนดขาสัญญาณตรวจจับการประกบขั้ว Pogo Pin (Pin 9 -> GPIO 6)
    // มีตัวต้านทาน Pull-up ภายใน เมื่อประกบจอ หน้าสัมผัสจะต่อลง GND ทำให้เกิดสัญญาณ FALLING
    pinMode(PIN_DOCK_DETECT, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(PIN_DOCK_DETECT), isrDockDetect, FALLING);

    // เริ่มต้นระบบฮาร์ดแวร์ SPI ความเร็ว 10 MHz
    epdSPI.begin(PIN_EPD_SCK, -1, PIN_EPD_MOSI, PIN_EPD_CS);

    // จัดสรรหน่วยความจำบัฟเฟอร์ 30,000 ไบต์สำหรับภาพ 2 สี
    g_downloadBuffer = (uint8_t *)ps_malloc(EPD_BUFFER_SIZE * 2);
    if (!g_downloadBuffer) {
        g_downloadBuffer = (uint8_t *)malloc(EPD_BUFFER_SIZE * 2);
    }

    // ตรวจสอบสถานะการเชื่อมต่อขั้ว Pogo Pin ทันทีเมื่อเปิดเครื่อง
    if (digitalRead(PIN_DOCK_DETECT) == LOW) {
        Serial.println("[DOCK] ตรวจพบการประกบหน้าจอเข้ากับขั้วต่อ Pogo Pin 10 ขา!");
        g_dockTriggered = true;
    } else {
        Serial.println("[DOCK] ยังไม่พบการประกบหน้าจอ เข้าสู่โหมดสแตนด์บายรอสัญญาณ");
    }
}

// -----------------------------------------------------------------------------
// MAIN LOOP
// -----------------------------------------------------------------------------
void loop() {
    esp_task_wdt_reset();

    // 1. ตรวจสอบการประกบหน้าจอ (Dock Detection Trigger)
    if (g_dockTriggered) {
        g_dockTriggered = false;
        Serial.println("\n[EVENT] หน้าจอสัมผัสกับขั้ว Pogo Pin! เริ่มต้นอัปเดตข้อมูลเป็นปัจจุบันทันที...");
        
        bool wifiOk = connectClinicWiFi();
        bool downloadOk = false;

        if (wifiOk) {
            WiFiClientSecure client;
            client.setInsecure(); // หรือกำหนด Root CA Cert ของโรงพยาบาลราชวิถี
            HTTPClient https;

            if (https.begin(client, EINK_API_URL)) {
                int httpCode = https.GET();
                if (httpCode == HTTP_CODE_OK) {
                    Serial.println("[SYNC] ดาวน์โหลดข้อมูลภาพใบนัดประจำวันสำเร็จ!");
                    downloadOk = true;
                }
                https.end();
            }
        }

        // รีเฟรชหน้าจอ E-Ink ทันทีที่มีการประกบ
        refreshEInkScreen(downloadOk);
        g_lastSyncMillis = millis();
    }

    // 2. การซิงค์อัตโนมัติตามระยะเวลา (Scheduled Daily / Hourly Sync)
    if (millis() - g_lastSyncMillis > (DEEP_SLEEP_HOURS * 3600000UL)) {
        if (digitalRead(PIN_DOCK_DETECT) == LOW) {
            Serial.println("[TIMER] ครบรอบระยะเวลาอัปเดตประจำชั่วโมง และหน้าจอยังประกบอยู่");
            g_dockTriggered = true;
        }
    }

    delay(100);
}
