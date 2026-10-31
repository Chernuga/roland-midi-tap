/*
 * RolandTapSerial -- same USB-MIDI impersonation, but logs over UART
 * (the CH340 connector) instead of WiFi.
 *
 * Use this for bring-up/debugging while the board is powered from the PC.
 * Do NOT connect both USB ports at once unless your board has VBUS
 * backfeed protection -- use the WiFi firmware for real captures.
 */
#include "USB.h"
#include "USBMIDI.h"

USBMIDI MIDI;

static uint32_t t0 = 0;
static uint32_t pkts = 0;
static uint32_t lastReport = 0;

void setup() {
  Serial.begin(115200);
  delay(1500);

  Serial.println();
  Serial.println(F("=== RolandTap (UART) ==="));
  Serial.printf("chip=%s rev=%d cores=%d\n", ESP.getChipModel(),
                ESP.getChipRevision(), ESP.getChipCores());

  USB.VID(0x1410);
  USB.PID(0x0290);
  USB.manufacturerName("Roland");
  USB.productName("Roland Digital Piano");
  USB.serialNumber("RDP000001");

  MIDI.begin();
  USB.begin();

  t0 = millis();
  lastReport = t0;
  Serial.println(F("USB-MIDI device up, waiting for host packets..."));
}

void loop() {
  midiEventPacket_t pkt;
  bool got = false;

  while (MIDI.readPacket(&pkt)) {
    if (!got) {
      Serial.printf("[%lu] RX", (unsigned long)(millis() - t0));
      got = true;
    }
    Serial.printf(" %02X %02X %02X %02X",
                  pkt.header, pkt.byte1, pkt.byte2, pkt.byte3);
    pkts++;
  }
  if (got) Serial.println();

  if (millis() - lastReport >= 5000) {
    lastReport = millis();
    Serial.printf("[%lu] alive packets=%lu\n",
                  (unsigned long)(millis() - t0), (unsigned long)pkts);
  }

  delay(1);
}
