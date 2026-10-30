// Copy this file to config.h (same folder) and fill in real values.
// config.h is git-ignored. NEVER commit real Wi-Fi credentials.
#pragma once

#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// LAN IP of the PC running Docker (mqtt-broker container, port 1883).
// Do NOT use "localhost" or "mqtt-broker" — those do not resolve from the ESP32.
#define MQTT_HOST "192.168.0.100"
#define MQTT_PORT 1883

#define DEVICE_ID "xiao-01"
#define PUBLISH_INTERVAL_MS 10000
