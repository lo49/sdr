#include "Packet.h"
#include "Network.h"
#include "Display.h"
#include "ArduinoBridge.h"
#include "CLI.h"

const long int AVG_BEACON_TIME = 30000;

Ptr<Network> Net;

void setup()
{
	Serial.begin(115200);
	oled_init();

	oled_show("Starting...", "", "", "");
	Buffer callsign = arduino_nvram_callsign_load();
	Net = net(callsign);

	oled_show("Net configured", callsign.cold(), "", "");
	Serial.print(callsign.cold());
	Serial.println(" ready");
	Serial.println();
}

void loop()
{
	while (Serial.available() > 0) {
		cli_type(Serial.read());
	}

	Net->run_tasks(millis());
}
