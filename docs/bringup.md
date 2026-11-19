# Bring-up checklist

For a freshly assembled led-budget-board, about 20 minutes. Do the steps in order and stop at the first one that
fails: each one protects the next. You need a meter, a bench supply (or the 12 V supply with something current
limited ahead of it if you have one), the Pico 2 W, and a USB cable. The firmware is `firmware/examples/bringup`.

Pico pin numbers: left column 1-20 from the USB end (GP0 is pin 1), right column 21-40 from the bottom up, so the
top right is pin 40 (VBUS), 39 (VSYS), 38 (GND), 37 (3V3_EN), 36 (3V3 OUT). Shroud pins: pin 1 (triangle) is GND,
all odd pins are GND, pin 13 = 3.3 V, pin 15 = 5 V, strand n is on pin 2n.

## 1. Bare board, no power, no Pico (meter)

- [ ] Look it over: J1 sits flat with the wire openings at the left edge, shrouds and sockets seated, no bridges.
- [ ] Ohms from GND (shroud pin 1) to each of these. None should be a dead short (under 1 ohm). The caps make a
      reading climb for a second; the final value should be kilohms or open.
  - shroud pin 15 (+5 V), shroud pin 13 (+3.3 V), Pico socket pin 39 (VSYS), J1 +12 V screw.
- [ ] Diode check on D1: meter on diode mode, red on the J1 +12 V screw, black on the board's +12 V side
      (D1 pin next to the buck): about 0.3 V. Reversed it should read open.
- [ ] A data line: shroud pin 2 to Pico socket pin 1 (GP0) reads about 33 ohms. Try one more on OUT2, for example
      shroud J3 pin 2 to socket pin 9 (GP8).

## 2. 12 V only, no Pico (bench supply at 12 V, current limit 100 mA if you can)

- [ ] The PWR LED lights, and the supply shows only a few mA. More than 20 mA means stop.
- [ ] Shroud pin 15 to pin 1: 5.0 to 5.2 V (the buck).
- [ ] Pico socket pin 39 to pin 38: about 4.7 V (5 V less the B5819W's drop).
- [ ] Shroud pin 13 reads 0 V: the 3.3 V comes from the Pico, which is not fitted yet.
- [ ] Reverse-lead check, if you want one: swap the 12 V leads. Nothing should light and nothing should get warm
      (D1 blocks it). Then put them back.

Power off.

## 3. Flash and boot the Pico

Seat the Pico 2 W in the two sockets with its USB connector at the top edge. With 12 V still off, hold the Pico's
BOOTSEL button, plug in USB, release. Then, from the repo's build (or `builds/budget_bringup/` in the project files):

```sh
picotool load -f -x bringup.uf2
tio /dev/cu.usbmodem*        # Linux: tio /dev/ttyACM0
```

`-f` forces the board into BOOTSEL if the firmware is already running, so this works every time after the first.
Leave USB as the only power for these checks:

- [ ] The Pico's own LED blinks once a second: the radio answers. The report says `Radio: answers`.
- [ ] A status line per second: uptime, die temperature (room temperature, give or take 10 C), `USB power yes`.
- [ ] Shroud pin 13 now reads 3.3 V. Shroud pin 15 reads 0 V: with USB alone the 5 V rail stays off.
- [ ] `SDA=1 SCL=1`: both I2C pull-ups (R21, R22) hold the bus up. A 0 means that pull-up or the line is broken.

Now plug in the 12 V as well.

- [ ] Both power sources at once is fine: the Pico keeps running, shroud pin 15 now reads 5 V.
- [ ] Unplug USB. The Pico's LED keeps blinking: the Pico runs from 12 V through D2 into VSYS. Plug USB back in.

## 4. The outputs

The firmware walks a high level over GP0-15, one pin per second, and prints which shroud pin to look at. Run
this with no strands plugged in (the walking pin would send them garbage). Keys on the serial: `p` pause, `n`
step (when paused), `a` all outputs high, `z` all low, `s` walk the spare pins of J6, `o` back to the outputs.

- [ ] Press `p`, then `n` to step. For each of the 16 pins the line says which shroud pin is high: meter from
      that shroud pin to a GND pin (shroud pin 1) reads about 3.3 V, and no other even pin does.
- [ ] `a`: all 16 even pins read 3.3 V. `z`: all 0 V.
- [ ] OUT1 is GP0-7 on J2, OUT2 is GP8-15 on J3. If a strand number is on the wrong pin, that is a wiring fault:
      write down which.
- [ ] `s` walks J6: GP18, 19, 22, 26, 27, 28 on J6 pins 2 to 7 (pin 1 is GND, pin 8 is 3V3).
- [ ] Later, with an output board on a ribbon: its LEDs and its level shifter answer the same walk.

## 5. The debug UART and I2C

- [ ] A 3.3 V USB-serial adapter on J4 (GND, TX, RX; the Pico's TX goes to the adapter's RX):
      `tio -b 115200 /dev/cu.usbserial*`. A line a second appears, and anything you type is echoed back. The USB
      report counts the bytes.
- [ ] With a STEMMA QT cable or a display on J5/J7, the full report (every 10 s) lists its I2C address. An
      SSD1306 OLED shows as 0x3c.

## If something fails

| What you see | Look at |
|---|---|
| No PWR LED, 5 V missing | J1 wiring and D1 direction; U1 and L1 solder; the divider R2, R3 |
| 5 V right, VSYS 0 | D2 direction and solder |
| Pico LED never blinks on 12 V alone | VSYS path, the sockets, a bent Pico pin |
| Radio does not answer | try another Pico; the radio is the Pico's own |
| One output pin never goes high | the 33 ohm resistor for it, the socket pin, the shroud pin |
| Two outputs go high together | a solder bridge between those two tracks |
| SDA or SCL reads 0 | R21 or R22, a solder bridge on J5 or J7 |
