# First power-on test for the budget board: walks a high level over the 16 output pins, echoes the
# debug UART, reports over USB serial. See docs/bringup.md.
add_executable(bringup main.cpp)

target_link_libraries(bringup
    PRIVATE
        pico_stdlib
        pico_unique_id
        hardware_adc
        hardware_i2c
        hardware_uart
        pico_cyw43_arch_none
)

pico_enable_stdio_usb(bringup 1)
# USB only: the default UART is J4 (GP16/17), which this test uses for its own echo.
pico_enable_stdio_uart(bringup 0)

pico_set_program_name(bringup "led-budget-board bringup")
pico_add_extra_outputs(bringup)
