/*
 * Board definition for the LED budget board: a Raspberry Pi Pico 2 W in two 1x20 sockets, 16 LED
 * strands on two 8-strand shrouds, a 12 V -> 5 V buck, no RTC.
 *
 * It is the pico-sdk's boards/pico2_w.h with the default UART and I2C moved to where this board
 * brings them out, so GP0-15 can all be LED outputs.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */

// -----------------------------------------------------
// NOTE: THIS HEADER IS ALSO INCLUDED BY ASSEMBLER SO
//       SHOULD ONLY CONSIST OF PREPROCESSOR DIRECTIVES
// -----------------------------------------------------
// Use with:  set(PICO_BOARD led_budget_board)
//            set(PICO_BOARD_HEADER_DIRS <path to led-budget-board>/firmware/boards)
// (both before pico_sdk_init / project()).

#ifndef _BOARDS_LED_BUDGET_BOARD_H
#define _BOARDS_LED_BUDGET_BOARD_H

// For board detection. RASPBERRYPI_PICO2_W is defined too, by the header included below.
#define LED_BUDGET_BOARD

// --- LED OUTPUTS ---
// OUT1 (J2) = GP0-7 and OUT2 (J3) = GP8-15, strand n of an output on GP(first + n - 1). Each run of
// 8 consecutive pins is one PIO state machine in PicoLEDs' Renderer.
#define LED_BUDGET_BOARD_OUT1_FIRST_PIN 0
#define LED_BUDGET_BOARD_OUT2_FIRST_PIN 8
#define LED_BUDGET_BOARD_STRANDS_PER_OUT 8
#define LED_BUDGET_BOARD_OUT_COUNT 2

// --- UART ---
// UART0 on the J4 header: GND, TX, RX.
#ifndef PICO_DEFAULT_UART
#define PICO_DEFAULT_UART 0
#endif
#ifndef PICO_DEFAULT_UART_TX_PIN
#define PICO_DEFAULT_UART_TX_PIN 16
#endif
#ifndef PICO_DEFAULT_UART_RX_PIN
#define PICO_DEFAULT_UART_RX_PIN 17
#endif

// --- I2C ---
// I2C0 on the J5 header and the J7 STEMMA QT socket, with 10k pull-ups on the board.
#ifndef PICO_DEFAULT_I2C
#define PICO_DEFAULT_I2C 0
#endif
#ifndef PICO_DEFAULT_I2C_SDA_PIN
#define PICO_DEFAULT_I2C_SDA_PIN 20
#endif
#ifndef PICO_DEFAULT_I2C_SCL_PIN
#define PICO_DEFAULT_I2C_SCL_PIN 21
#endif

// --- SPARE I/O ---
// Header J6: GP18, GP19, GP22, GP26 (ADC0), GP27 (ADC1), GP28 (ADC2).

// Everything else (LED on the radio's WL_GPIO0, radio pins, flash, VSYS sensing) is the Pico 2 W's.
#include "boards/pico2_w.h"

#endif // _BOARDS_LED_BUDGET_BOARD_H
