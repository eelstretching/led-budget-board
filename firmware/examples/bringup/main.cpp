// Bring-up test for a freshly assembled budget board (Pico 2 W in the sockets).
//
// - The Pico's LED (on the radio chip) blinks at 1 Hz: proves the radio answers.
// - A high level walks over the 16 output pins, one pin per second, so a meter or a scope on a shroud
//   pin (or an LED + resistor to GND) shows each channel in turn. The report says which shroud pin to
//   look at. NOTE: if strands are plugged in the walking pin sends them garbage: run it unplugged.
// - Once a second over USB serial: uptime, die temperature, whether USB power is present, and the
//   state of the I2C lines. Every 10 s the full report, including an I2C scan.
// - The debug UART (J4: GP16 TX, GP17 RX, 115200 8N1) echoes every byte back, and sends a line a
//   second of its own, so a USB-serial adapter on J4 can be checked in both directions.
//
// Keys on the USB serial: p pause/resume the walk, n step to the next pin (paused), a all outputs
// high, z all low, s walk the spare pins (J6) instead, o walk the outputs, ? help.
#include <cstdio>

#include "hardware/adc.h"
#include "hardware/i2c.h"
#include "hardware/uart.h"
#include "pico/cyw43_arch.h"
#include "pico/stdlib.h"
#include "pico/unique_id.h"

static const uint8_t OUTPUT_PINS[16] = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15};
static const uint8_t SPARE_PINS[6] = {18, 19, 22, 26, 27, 28};
static const int SPARE_HEADER_PIN[6] = {2, 3, 4, 5, 6, 7};   // J6 pin numbers, pin 1 is GND

enum class Mode { WALK, ALL_HIGH, ALL_LOW };
static Mode mode = Mode::WALK;
static bool spare = false;      // walking the J6 pins rather than the shroud pins
static bool paused = false;
static int walkIndex = 0;
static uint32_t uartBytes = 0;
static bool radioOk = false;
static int radioErr = 0;

static void allLow() {
    for (uint8_t p : OUTPUT_PINS) gpio_put(p, 0);
    for (uint8_t p : SPARE_PINS) gpio_put(p, 0);
}

static void describe(int index) {
    if (spare) {
        printf("  GP%d high: J6 pin %d\n", SPARE_PINS[index], SPARE_HEADER_PIN[index]);
    } else {
        int pin = OUTPUT_PINS[index];
        printf("  GP%d high: OUT%d strand %d, shroud J%d pin %d\n", pin, pin / 8 + 1, pin % 8 + 1,
               pin / 8 + 2, 2 * (pin % 8 + 1));
    }
}

// Set the walking pin for walkIndex and clear every other pin.
static void applyWalk() {
    allLow();
    if (spare) {
        gpio_put(SPARE_PINS[walkIndex], 1);
    } else {
        gpio_put(OUTPUT_PINS[walkIndex], 1);
    }
    describe(walkIndex);
}

static void applyMode() {
    if (mode == Mode::WALK) {
        applyWalk();
    } else if (mode == Mode::ALL_HIGH) {
        allLow();
        for (uint8_t p : OUTPUT_PINS) gpio_put(p, 1);
        printf("  all 16 outputs high\n");
    } else {
        allLow();
        printf("  all outputs low\n");
    }
}

static void stepWalk() {
    int n = spare ? 6 : 16;
    walkIndex = (walkIndex + 1) % n;
    applyWalk();
}

static void help() {
    printf("keys: p pause/resume  n next pin (paused)  a all high  z all low  s spare pins  "
           "o outputs  ? help\n");
}

static void handleKey(int c) {
    switch (c) {
    case 'p': paused = !paused; mode = Mode::WALK; printf("%s\n", paused ? "paused" : "walking"); applyMode(); break;
    case 'n': if (paused) { mode = Mode::WALK; stepWalk(); } break;
    case 'a': mode = Mode::ALL_HIGH; spare = false; applyMode(); break;
    case 'z': mode = Mode::ALL_LOW; applyMode(); break;
    case 's': spare = true; walkIndex = 0; mode = Mode::WALK; printf("walking the spare pins (J6)\n"); applyMode(); break;
    case 'o': spare = false; walkIndex = 0; mode = Mode::WALK; printf("walking the outputs\n"); applyMode(); break;
    case '?': help(); break;
    default: break;
    }
}

static float dieTemperatureC() {
    adc_select_input(ADC_TEMPERATURE_CHANNEL_NUM);   // input 4 on the 60-pin RP2350A of a Pico 2 W (8 on the RP2350B)
    uint16_t raw = adc_read();
    float v = raw * 3.3f / 4096.0f;
    return 27.0f - (v - 0.706f) / 0.001721f;
}

// Whether anything answers at each I2C address (7-bit), with a quick read.
static void scanI2c() {
    printf("I2C0 scan (SDA GP20, SCL GP21): ");
    int found = 0;
    for (int addr = 0x08; addr < 0x78; addr++) {
        uint8_t b;
        if (i2c_read_timeout_us(i2c0, addr, &b, 1, false, 2000) >= 0) {
            printf("0x%02x ", addr);
            found++;
        }
    }
    printf(found ? "\n" : "nothing answered (nothing plugged in)\n");
}

static void fullReport() {
    pico_unique_board_id_t id;
    pico_get_unique_board_id(&id);
    printf("\n==== led-budget-board bringup ====\nBoard ID: ");
    for (int i = 0; i < PICO_UNIQUE_BOARD_ID_SIZE_BYTES; i++) printf("%02x", id.id[i]);
    printf("\nRadio: %s", radioOk ? "answers (LED blinks)" : "NOT answering");
    if (!radioOk) printf(" (cyw43 error %d)", radioErr);
    printf("\nUART J4 (GP16 TX / GP17 RX): %lu bytes echoed so far\n", static_cast<unsigned long>(uartBytes));
    scanI2c();
    help();
}

int main() {
    stdio_init_all();

    adc_init();
    adc_set_temp_sensor_enabled(true);

    for (uint8_t p : OUTPUT_PINS) { gpio_init(p); gpio_set_dir(p, GPIO_OUT); }
    for (uint8_t p : SPARE_PINS) { gpio_init(p); gpio_set_dir(p, GPIO_OUT); }
    allLow();

    // The debug UART, with its own echo.
    uart_init(uart0, 115200);
    gpio_set_function(PICO_DEFAULT_UART_TX_PIN, GPIO_FUNC_UART);
    gpio_set_function(PICO_DEFAULT_UART_RX_PIN, GPIO_FUNC_UART);

    // I2C0 with no internal pull-ups: the 10k pull-ups on the board must hold the bus high.
    i2c_init(i2c0, 100 * 1000);
    gpio_set_function(PICO_DEFAULT_I2C_SDA_PIN, GPIO_FUNC_I2C);
    gpio_set_function(PICO_DEFAULT_I2C_SCL_PIN, GPIO_FUNC_I2C);

    radioErr = cyw43_arch_init();
    bool led = false;

    uint32_t lastTick = to_ms_since_boot(get_absolute_time());
    int seconds = 0;
    applyMode();

    while (true) {
        int c = getchar_timeout_us(0);
        if (c != PICO_ERROR_TIMEOUT) handleKey(c);
        while (uart_is_readable(uart0)) {
            uart_putc_raw(uart0, uart_getc(uart0));
            uartBytes++;
        }

        uint32_t now = to_ms_since_boot(get_absolute_time());
        if (now - lastTick < 1000) {
            sleep_ms(1);
            continue;
        }
        lastTick += 1000;
        seconds++;

        led = !led;
        if (radioErr == 0) {
            int e = cyw43_gpio_set(&cyw43_state, CYW43_WL_GPIO_LED_PIN, led);
            radioOk = (e == 0);
            if (e != 0) radioErr = e;
        }
        if (mode == Mode::WALK && !paused) stepWalk();

        int usb = radioOk ? cyw43_arch_gpio_get(CYW43_WL_GPIO_VBUS_PIN) : -1;
        printf("%4d s  %.1f C  USB power %s  SDA=%d SCL=%d (1 = pulled up)\n", seconds, dieTemperatureC(),
               usb < 0 ? "?" : (usb ? "yes" : "no"), gpio_get(PICO_DEFAULT_I2C_SDA_PIN),
               gpio_get(PICO_DEFAULT_I2C_SCL_PIN));
        uart_puts(uart0, "led-budget-board bringup, uptime ");
        char buf[16];
        snprintf(buf, sizeof buf, "%d s\r\n", seconds);
        uart_puts(uart0, buf);
        if (seconds % 10 == 1) fullReport();
    }
}
