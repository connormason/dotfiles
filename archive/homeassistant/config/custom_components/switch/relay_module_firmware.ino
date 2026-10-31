#include <string>

int FW_VERSION = 5;

bool ON_RELAY_STATE = LOW;
int INITIALIZED_PIN_RANGE_MIN = 0;
int INITIALIZED_PIN_RANGE_MAX = 7;

// Get firmware version
int getFWVersion(String arg) {
    Serial.println("Getting FW version...");
    return FW_VERSION;
}

// Turn on inputted relay pin
int turnOn(String relayPin) {
    Serial.printlnf("Turning on relay %s...", relayPin.c_str());
    int relayNum = relayPin.toInt();
    digitalWrite(relayNum, ON_RELAY_STATE);
    return relayNum;
}

// Turn off inputted relay
int turnOff(String relayPin) {
    Serial.printlnf("Turning off relay %s...", relayPin.c_str());
    int relayNum = relayPin.toInt();
    digitalWrite(relayNum, not ON_RELAY_STATE);
    return relayNum;
}

// Get state of specific relay
int getState(String relayPin) {
    Serial.printlnf("Getting state of relay %s...", relayPin.c_str());
    int relayNum = relayPin.toInt();
    return digitalRead(relayNum) == ON_RELAY_STATE;
}

void setup() {
    Serial.begin(9600);

    // Initialize pins
    for (unsigned int i = INITIALIZED_PIN_RANGE_MIN; i < INITIALIZED_PIN_RANGE_MAX; ++i) {
        pinMode(i, OUTPUT);
        digitalWrite(i, not ON_RELAY_STATE);
    }

    // Expose functions
    Particle.function("get_fw_version", getFWVersion);
    Particle.function("turn_on", turnOn);
    Particle.function("turn_off", turnOff);
    Particle.function("get_state", getState);
}

void loop() {
    // Do nothing, only exposing functions
}
