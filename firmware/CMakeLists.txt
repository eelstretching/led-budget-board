cmake_minimum_required(VERSION 3.13)

# Builds for the budget board by default: a Pico 2 W with the default UART on GP16/17 and I2C on GP20/21
# (boards/led_budget_board.h). Configure with
#   cmake -S firmware -B build -G Ninja -DPICO_SDK_PATH=<pico-sdk 2.3.x>
set(PICO_BOARD_HEADER_DIRS ${CMAKE_CURRENT_LIST_DIR}/boards)
set(PICO_BOARD led_budget_board CACHE STRING "Board type")

include(pico_sdk_import.cmake)

project(led_budget_board_firmware C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_subdirectory(examples/bringup)
