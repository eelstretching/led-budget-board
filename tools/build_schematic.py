"""Build the LED budget board schematic (one A3 sheet).

A carrier for a Raspberry Pi Pico 2 W: two 16-pin ribbon shrouds (16 strands, GP0-15),
the 12 V -> 5 V buck from led-processor-board, a debug UART header on GP16/17, an I2C
header on GP20/21, a spare GPIO header and a RUN button. No RTC, no USB, no radio: those
come with the Pico (time comes from the show leader's PicoComm beacons). The I2C bus also
goes to a STEMMA QT socket.

    KICAD_SYMBOL_DIR=/usr/share/kicad/symbols python3 tools/build_schematic.py [outdir]

This writes the first version of the schematic. Once it has been edited in KiCad, edit it
there; re-running this overwrites the files.
"""
import sys, os, copy, math, uuid as _uuid, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sx, libs
from sx import Sym, S

OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else '.'
PROJECT = 'led-budget-board'
_seed = [0]


def uid():
    # deterministic UUIDs so re-running the generator gives the same files
    _seed[0] += 1
    return str(_uuid.uuid5(_uuid.NAMESPACE_URL, PROJECT + '/%d' % _seed[0]))


ROOT = uid()


def effects(justify=None, size=1.27):
    e = S('effects', S('font', S('size', size, size)))
    if justify:
        e.append(S('justify', *[Sym(j) for j in justify.split()]))
    return e


def prop(name, value, x, y, ang=0.0, hide=False, justify=None, size=1.27):
    p = S('property', name, value, S('at', x, y, ang))
    if hide:
        p.append(S('hide', Sym('yes')))
    p += [S('show_name', Sym('no')), S('do_not_autoplace', Sym('no')), effects(justify, size=size)]
    return p


def r4(v):
    return round(v + 0.0, 4)


class Sheet:
    def __init__(self, path):
        self.path = path
        self.items = []
        self.lib = {}

    def wire(self, *pts):
        for a, b in zip(pts, pts[1:]):
            self.items.append(S('wire', S('pts', S('xy', r4(a[0]), r4(a[1])), S('xy', r4(b[0]), r4(b[1]))),
                                S('stroke', S('width', 0.0), S('type', Sym('default'))), S('uuid', uid())))

    def junction(self, p):
        self.items.append(S('junction', S('at', r4(p[0]), r4(p[1])), S('diameter', 0.0),
                            S('color', 0.0, 0.0, 0.0, 0.0), S('uuid', uid())))

    def nc(self, p):
        self.items.append(S('no_connect', S('at', r4(p[0]), r4(p[1])), S('uuid', uid())))

    def label(self, name, p, ang=0.0):
        just = {0: 'left bottom', 90: 'left bottom', 180: 'right bottom', 270: 'right bottom'}[int(ang)]
        self.items.append(S('label', name, S('at', r4(p[0]), r4(p[1]), float(ang)),
                            effects(just), S('uuid', uid())))

    def text(self, s, p, size=1.27):
        self.items.append(S('text', s, S('exclude_from_sim', Sym('no')), S('at', r4(p[0]), r4(p[1]), 0.0),
                            effects('left bottom', size=size), S('uuid', uid())))

    def symbol(self, full, libsym, ref, value, at, rot=0, mirror=None, fields=None, ref_at=None,
               val_at=None, power=False, in_bom=True, hide_value=False, val_ang=None, val_just=None):
        self.lib.setdefault(full, libsym)
        pins = libs.pins(libsym)
        x, y = at
        e = S('symbol', S('lib_id', full), S('at', r4(x), r4(y), float(rot)))
        if mirror:
            e.append(S('mirror', Sym(mirror)))
        e += [S('unit', 1.0), S('body_style', 1.0), S('exclude_from_sim', Sym('no')),
              S('in_bom', Sym('yes' if in_bom else 'no')), S('on_board', Sym('yes')),
              S('in_pos_files', Sym('yes' if in_bom else 'no')), S('dnp', Sym('no')), S('uuid', uid())]
        rx, ry = ref_at if ref_at else (x + 2.54, y - 1.27)
        vx, vy = val_at if val_at else (x + 2.54, y + 1.27)
        fa = 0.0 if power else float(rot % 180)
        jf = None if (power or rot % 180) else 'left'
        e.append(prop('Reference', ref, r4(rx), r4(ry), fa, hide=power, justify=jf))
        e.append(prop('Value', value, r4(vx), r4(vy), fa if val_ang is None else float(val_ang), hide=hide_value,
                      justify=val_just or jf))
        fields = dict(fields or {})
        for k in ('Footprint', 'Datasheet', 'Description'):
            if k not in fields:
                lp = sx.prop(libsym, k)
                fields[k] = lp[2] if lp else ''
        order = ['Footprint', 'Datasheet', 'Description'] + [k for k in fields if k not in
                                                              ('Footprint', 'Datasheet', 'Description')]
        for k in order:
            e.append(prop(k, fields[k], r4(x), r4(y), 0.0, hide=True))
        for n in sorted(pins, key=lambda s: (len(s), s)):
            e.append(S('pin', n, S('uuid', uid())))
        e.append(S('instances', S('project', PROJECT, S('path', self.path, S('reference', ref), S('unit', 1.0)))))
        self.items.append(e)
        return Placed(pins, x, y, rot, mirror)


class Placed:
    def __init__(self, pins, x, y, rot, mirror):
        self.pins, self.x, self.y, self.rot, self.mirror = pins, x, y, rot, mirror

    def __getitem__(self, n):
        px, py = self.pins[str(n)][:2]
        if self.mirror == 'y':
            px = -px
        elif self.mirror == 'x':
            py = -py
        a = math.radians(self.rot)
        vx = px * math.cos(a) - py * math.sin(a)
        vy = px * math.sin(a) + py * math.cos(a)
        return (r4(self.x + vx), r4(self.y - vy))


# --------------------------------------------------------------------------------------
# library symbols
# --------------------------------------------------------------------------------------
SYM = {}
for lib, name in [('Device', 'R'), ('Device', 'C'), ('Device', 'D_Schottky'), ('Device', 'LED'), ('Device', 'L'),
                  ('power', 'GND'), ('power', '+3V3'), ('power', '+5V'), ('power', '+12V'), ('power', 'PWR_FLAG'),
                  ('Connector_Generic', 'Conn_02x08_Odd_Even'), ('Connector_Generic', 'Conn_01x03'),
                  ('Connector_Generic', 'Conn_01x04'), ('Connector_Generic', 'Conn_01x08'),
                  ('Connector', 'Screw_Terminal_01x02'), ('Regulator_Switching', 'TPS54202DDC'),
                  ('Switch', 'SW_Push'), ('Mechanical', 'MountingHole'),
                  ('Connector_Generic_MountingPin', 'Conn_01x04_MountingPin')]:
    SYM[lib + ':' + name] = libs.get_symbol(lib, name)


def pico_symbol():
    """The stock Pico W symbol (same 40 pins as a Pico 2 W) as a project symbol.

    AGND becomes passive: on the Pico it is the same copper as GND, and two power outputs
    on one net is an ERC error. The footprint is the through-hole one, for a socketed Pico.
    """
    s = libs.get_symbol('MCU_Module', 'RaspberryPi_Pico_W')
    s[1] = PROJECT + ':Pico_2_W'
    for u in sx.findall(s, 'symbol'):
        u[1] = u[1].replace('RaspberryPi_Pico_W', 'Pico_2_W', 1)
        for p in sx.findall(u, 'pin'):
            if sx.find(p, 'number')[1] == '33':
                p[1] = Sym('passive')
    sx.prop(s, 'Value')[2] = 'Pico_2_W'
    sx.prop(s, 'Footprint')[2] = 'Module:RaspberryPi_Pico_Common_THT'
    sx.prop(s, 'Datasheet')[2] = 'https://datasheets.raspberrypi.com/picow/pico-2-w-datasheet.pdf'
    sx.prop(s, 'Description')[2] = ('Raspberry Pi Pico 2 W (RP2350A + CYW43439 WiFi/Bluetooth) in two 1x20 '
                                    'sockets')
    return s


PICO = pico_symbol()
SYM[PICO[1]] = PICO

pwr_n = [0]
flg_n = [0]


def gnd(sh, p, rot=0):
    pwr_n[0] += 1
    sh.symbol('power:GND', SYM['power:GND'], '#PWR%02d' % pwr_n[0], 'GND', p, rot=rot, power=True,
              in_bom=False, val_at=(p[0], p[1] + 5.08), hide_value=rot != 0)


def pwr(sh, name, p, rot=0):
    pwr_n[0] += 1
    kw = dict(val_at=(p[0], p[1] - 5.08))
    if rot == 90:       # symbol points left: put the name to its left, reading left to right
        kw = dict(val_at=(p[0] - 3.81, p[1]), val_ang=90, val_just='right')
    sh.symbol('power:' + name, SYM['power:' + name], '#PWR%02d' % pwr_n[0], name, p, rot=rot, power=True,
              in_bom=False, **kw)


def flag(sh, p):
    flg_n[0] += 1
    sh.symbol('power:PWR_FLAG', SYM['power:PWR_FLAG'], '#FLG%02d' % flg_n[0], 'PWR_FLAG', p, power=True,
              in_bom=False, val_at=(p[0], p[1] - 5.08), hide_value=True)


def part(mpn, lcsc, mfr, desc, fp):
    f = {'Footprint': fp, 'Datasheet': '', 'Description': desc, 'manufacturer': mfr, 'manufacturer_pn': mpn}
    if lcsc:
        f['LCSC'] = lcsc
    return f


R0402 = 'Resistor_SMD:R_0402_1005Metric'
C0402 = 'Capacitor_SMD:C_0402_1005Metric'
C0603 = 'Capacitor_SMD:C_0603_1608Metric'
C0805 = 'Capacitor_SMD:C_0805_2012Metric'
# The same parts as led-processor-board, which JLCPCB has already assembled for us.
P = {
    '33': part('0402WGF330JTCE', 'C25105', 'UNI-ROYAL', 'Resistor, 33, 5%, 0402', R0402),
    '10k': part('0402WGF1002TCE', 'C25744', 'UNI-ROYAL', 'Resistor, 10k, 1%, 0402', R0402),
    '1k': part('0402WGF1001TCE', 'C11702', 'UNI-ROYAL', 'Resistor, 1k, 1%, 0402', R0402),
    '100k': part('0402WGF1003TCE', 'C25741', 'UNI-ROYAL', 'Resistor, 100k, 1%, 0402', R0402),
    '13.3k': part('0402WGF1332TCE', 'C122547', 'UNI-ROYAL', 'Resistor, 13.3k, 1%, 0402', R0402),
    '510k': part('0402WGF5103TCE', 'C11616', 'UNI-ROYAL', 'Resistor, 510k, 1%, 0402', R0402),
    '100n': part('CL05B104KO5NNNC', 'C1525', 'Samsung', 'Capacitor, 100n, 16V, X7R, 0402', C0402),
    '100n50': part('CC0603KRX7R9BB104', 'C14663', 'YAGEO', 'Capacitor, 100n, 50V, X7R, 0603', C0603),
    '75p': part('0402CG750J500NT', 'C37809', 'FH', 'Capacitor, 75p, 50V, C0G, 0402', C0402),
    '10u50': part('CL21A106KBYNNNE', 'C440198', 'Samsung', 'Capacitor, 10u, 50V, X5R, 0805', C0805),
    '22u25': part('CL21A226MAQNNNE', 'C45783', 'Samsung', 'Capacitor, 22u, 25V, X5R, 0805', C0805),
}
rn = [0]
cn = [0]


def R(sh, val, at, rot=0, **kw):
    rn[0] += 1
    return sh.symbol('Device:R', SYM['Device:R'], 'R%d' % rn[0], val, at, rot=rot, fields=P[val], **kw)


def C(sh, val, at, rot=0, show=None, **kw):
    cn[0] += 1
    return sh.symbol('Device:C', SYM['Device:C'], 'C%d' % cn[0], show or val, at, rot=rot, fields=P[val], **kw)


sh = Sheet('/' + ROOT)

# ======================================================================================
# Power: 12 V in, 5 V buck (the led-processor-board circuit, same parts and values)
# ======================================================================================
sh.text('12 V in, 5 V buck', (25.4, 50.8), size=2.54)
J1 = sh.symbol('Connector:Screw_Terminal_01x02', SYM['Connector:Screw_Terminal_01x02'], 'J1', '12V IN',
               (25.4, 76.2), mirror='y',
               fields=part('DBT50G-9.5-2P', 'C395958', 'DORABO',
                           '12 V input from the LED supply: 9.5 mm barrier terminal, the output boards\' input '
                           'terminal, takes 14 AWG with a ferrule',
                           'led-budget-board:CONN-TH_2P-P9.50_DBT50G-9.5-2P'),
               ref_at=(17.78, 72.39), val_at=(17.78, 74.93))
sh.wire(J1[2], (33.02, J1[2][1]), (33.02, 83.82)); gnd(sh, (33.02, 83.82))
D1 = sh.symbol('Device:D_Schottky', SYM['Device:D_Schottky'], 'D1', 'SS34', (44.45, 76.2), rot=180,
               fields=part('SS34', 'C8678', 'MDD', 'Schottky 40 V 3 A, reverse-polarity protection', 'Diode_SMD:D_SMA'),
               ref_at=(41.91, 69.85), val_at=(41.91, 72.39))
sh.wire(J1[1], D1[2]); sh.label('VIN_RAW', (33.02, 76.2), 0)
taps12 = [D1[1][0], 50.8, 55.88, 63.5, 73.66, 83.82, 93.98, 101.6]
for a, b in zip(taps12, taps12[1:]):
    sh.wire((a, 76.2), (b, 76.2))
for x in taps12[1:-1]:
    sh.junction((x, 76.2))
flag(sh, (50.8, 76.2)); pwr(sh, '+12V', (55.88, 76.2))
for val, x in [('10u50', 63.5), ('10u50', 73.66), ('100n50', 83.82)]:
    cc = C(sh, val, (x, 80.01), show='10u' if val == '10u50' else '100n',
           ref_at=(x + 2.54, 78.74), val_at=(x + 2.54, 81.28))
    gnd(sh, cc[2])
U1 = sh.symbol('Regulator_Switching:TPS54202DDC', SYM['Regulator_Switching:TPS54202DDC'], 'U1', 'TPS54202H',
               (116.84, 86.36),
               fields=part('TPS54202HDDCR', 'C527684', 'Texas Instruments',
                           '4.5-28 V in, 2 A sync buck, 500 kHz, SOT-23-6 (EN has an internal pull-down: H version)',
                           'Package_TO_SOT_SMD:SOT-23-6'),
               ref_at=(111.76, 77.47), val_at=(111.76, 80.01))
sh.wire((101.6, 76.2), (101.6, U1[3][1]), U1[3])
Ren = R(sh, '510k', (93.98, 80.01), ref_at=(95.25, 78.74), val_at=(95.25, 81.28))
sh.wire(Ren[2], (93.98, U1[5][1]), U1[5])
gnd(sh, U1[1])
Cb = C(sh, '100n50', (137.16, 82.55), show='100n', ref_at=(139.7, 81.28), val_at=(139.7, 83.82))
sh.wire(U1[6], (129.54, U1[6][1]), (129.54, Cb[1][1]), Cb[1])
L1 = sh.symbol('Device:L', SYM['Device:L'], 'L1', '15u', (146.05, 86.36), rot=90,
               fields=part('SWPA8040S150MT', 'C16853', 'Sunlord', 'Inductor, 15 uH, 2.6 A, shielded, 8 x 8 mm',
                           'Inductor_SMD:L_Sunlord_SWPA8040S'),
               ref_at=(146.05, 82.55), val_at=(149.86, 82.55))
sh.wire(U1[2], Cb[2]); sh.wire(Cb[2], L1[1]); sh.junction(Cb[2])
sh.label('SW', (129.54, 86.36), 0)
taps5 = [L1[2][0], 154.94, 165.1, 175.26, 185.42, 195.58, 203.2, 208.28, 215.9, 223.52]
for a, b in zip(taps5, taps5[1:]):
    sh.wire((a, 86.36), (b, 86.36))
for x in taps5[1:-1]:
    sh.junction((x, 86.36))
Rt = R(sh, '100k', (154.94, 90.17), ref_at=(156.21, 88.9), val_at=(156.21, 91.44))
Rb = R(sh, '13.3k', (154.94, 97.79), ref_at=(156.21, 96.52), val_at=(156.21, 99.06))
Cf = C(sh, '75p', (165.1, 90.17), ref_at=(167.64, 88.9), val_at=(167.64, 91.44))
sh.wire(U1[4], (129.54, U1[4][1]), (129.54, 93.98), Rt[2])
sh.wire(Rt[2], Cf[2]); sh.junction(Rt[2]); sh.label('FB', (132.08, 93.98), 0)
gnd(sh, Rb[2])
for x in (175.26, 185.42, 195.58):
    cc = C(sh, '22u25', (x, 90.17), show='22u', ref_at=(x + 2.54, 88.9), val_at=(x + 2.54, 91.44))
    gnd(sh, cc[2])
pwr(sh, '+5V', (203.2, 86.36)); flag(sh, (208.28, 86.36))
Rl = R(sh, '1k', (215.9, 90.17), ref_at=(217.17, 88.9), val_at=(217.17, 91.44))
D3 = sh.symbol('Device:LED', SYM['Device:LED'], 'D3', 'Green', (215.9, 97.79), rot=90,
               fields=part('KT-0603YG', 'C2289', 'Hubei KENTO', '+5V present (green LED, 0603)',
                           'LED_SMD:LED_0603_1608Metric'),
               ref_at=(220.345, 96.52), val_at=(222.25, 99.06))
assert Rl[2] == D3[2], (Rl[2], D3[2])
gnd(sh, D3[1])
D2 = sh.symbol('Device:D_Schottky', SYM['Device:D_Schottky'], 'D2', 'B5819W', (227.33, 86.36), rot=180,
               fields=part('B5819W SL', 'C8598', 'Changjiang', 'Schottky 40 V 1 A: +5V to the Pico\'s VSYS',
                           'Diode_SMD:D_SOD-123'),
               ref_at=(224.79, 81.28), val_at=(224.79, 83.82))
sh.wire(D2[1], (236.22, 86.36), (241.3, 86.36)); sh.label('VSYS', (241.3, 86.36), 0)
flag(sh, (236.22, 86.36)); sh.junction((236.22, 86.36))
sh.text('U1 and its parts are the led-processor-board buck (TI\'s TPS54202HEVM-716 5 V design): 100k / 13.3k with\n'
        '75 pF across the top resistor, 0.596 V x (1 + 100/13.3) = 5.08 V; 15 uH; 500 kHz. The 510k enables U1 from\n'
        'the 12 V side. D1 blocks a reversed 12 V lead.\n'
        '+5V feeds ribbon pin 15 directly. The Pico gets it on VSYS through D2 (about 4.7 V), so USB and 12 V can\n'
        'both be plugged in: the Pico\'s own diode keeps VSYS off the USB port and D2 keeps USB out of the buck.\n'
        'On USB alone the Pico runs but the ribbons have no +5V, as on the processor board.\n'
        'The load is small: the Pico and two output boards\' level shifters, well under 0.5 A.', (25.4, 127.0))

# ======================================================================================
# Pico 2 W
# ======================================================================================
sh.text('Pico 2 W in two 1x20 sockets', (60.96, 152.4), size=2.54)
A1 = sh.symbol(PICO[1], PICO, 'A1', 'Pico 2 W', (119.38, 203.2),
               fields={'manufacturer': 'Raspberry Pi', 'manufacturer_pn': 'SC1633'},
               ref_at=(132.08, 163.83), val_at=(132.08, 166.37))
# GP0-15: left side, pins 1-20
LEFT = {0: 1, 1: 2, 2: 4, 3: 5, 4: 6, 5: 7, 6: 9, 7: 10, 8: 11, 9: 12, 10: 14, 11: 15, 12: 16, 13: 17,
        14: 19, 15: 20}
for g, pin in LEFT.items():
    p = A1[pin]
    sh.wire(p, (88.9, p[1])); sh.label('GP%d' % g, (88.9, p[1]), 180)
RIGHT = {16: 21, 17: 22, 18: 24, 19: 25, 20: 26, 21: 27, 22: 29, 26: 31, 27: 32, 28: 34}
for g, pin in RIGHT.items():
    p = A1[pin]
    sh.wire(p, (149.86, p[1])); sh.label('GP%d' % g, (149.86, p[1]), 0)
sh.text('UART0 TX', (160.02, A1[21][1])); sh.text('UART0 RX', (160.02, A1[22][1]))
sh.text('I2C0 SDA', (160.02, A1[26][1])); sh.text('I2C0 SCL', (160.02, A1[27][1]))
# power pins
v = A1[39]
sh.wire(v, (v[0], 160.02), (104.14, 160.02)); sh.label('VSYS', (104.14, 160.02), 180)
sh.nc(A1[40])                      # VBUS: USB 5 V out, not used
t = A1[36]
sh.wire(t, (t[0], 157.48)); pwr(sh, '+3V3', (t[0], 157.48))
gnd(sh, A1[3])
ag = A1[33]
sh.wire(ag, (149.86, ag[1]), (149.86, 231.14)); gnd(sh, (149.86, 231.14))
sh.nc(A1[35])                      # ADC_VREF
sh.nc(A1[37])                      # 3V3_EN
# RUN button
SW1 = sh.symbol('Switch:SW_Push', SYM['Switch:SW_Push'], 'SW1', 'RUN', (68.58, A1[30][1]),
                fields=part('TS-1088R-02526', 'C455281', 'XKB Connection', 'Tactile switch, SMD, resets the Pico',
                            'Button_Switch_SMD:SW_SPST_TS-1088-xR025'),
                ref_at=(66.04, 172.72), val_at=(66.04, 175.26))
sh.wire(A1[30], SW1[2])
sh.wire(SW1[1], (58.42, SW1[1][1]), (58.42, 185.42)); gnd(sh, (58.42, 185.42))
sh.text('GP0-7 = OUT1, GP8-15 = OUT2: two runs of eight consecutive pins,\n'
        'one PIO state machine each in the PicoLEDs renderer.\n'
        'GP16/17 = debug UART (UART0), GP20/21 = I2C0.\n'
        'GP23-25 and GP29 are the Pico\'s own (radio, LED, VSYS sense).\n'
        'USB, BOOTSEL, SWD and the LED are on the Pico. SW1 pulls RUN low to reset it.',
        (25.4, 259.08))

# ======================================================================================
# Output shrouds
# ======================================================================================
sh.text('Output shrouds: 16-pin IDC to the output boards. Pin 1 is the triangle on the shroud.\n'
        'Odd pins 1-11 GND, 13 = +3V3 (shifter VCCA), 15 = +5V (shifter VCCB); data 1-8 on even pins 2-16\n'
        '(same as led-output-board J2 and led-processor-board). 33R series resistors at the Pico end.',
        (185.42, 139.7))
BOX = part('Box header 2x08 2.54 mm', '', '', 'Shrouded 16-pin IDC box header, same as the output boards',
           'Connector_IDC:IDC-Header_2x08_P2.54mm_Vertical')
for k in range(2):
    bx = [185.42, 297.18][k]
    by = 152.4
    g0 = 8 * k
    sh.text('OUT%d: GP%d-%d' % (k + 1, g0, g0 + 7), (bx, by - 2.54), size=2.032)
    J = sh.symbol('Connector_Generic:Conn_02x08_Odd_Even', SYM['Connector_Generic:Conn_02x08_Odd_Even'],
                  'J%d' % (2 + k), 'OUT%d' % (k + 1), (bx + 30.48, by + 20.32), fields=BOX,
                  ref_at=(bx + 29.21, by + 8.89), val_at=(bx + 29.21, by + 34.29))
    xb = bx + 22.86
    for n in (1, 3, 5, 7, 9, 11):
        sh.wire(J[n], (xb, J[n][1]))
    sh.wire((xb, J[1][1]), (xb, J[11][1]))
    for n in (3, 5, 7, 9):
        sh.junction((xb, J[n][1]))
    sh.wire((xb, J[1][1]), (bx + 15.24, J[1][1])); sh.junction((xb, J[1][1]))
    gnd(sh, (bx + 15.24, J[1][1]))
    sh.wire(J[13], (bx + 17.78, J[13][1])); pwr(sh, '+3V3', (bx + 17.78, J[13][1]))
    sh.wire(J[15], (bx + 10.16, J[15][1])); pwr(sh, '+5V', (bx + 10.16, J[15][1]))
    for i, net in enumerate(['+3V3', '+5V']):
        cx = bx + 10.16 + 10.16 * i
        cc = C(sh, '100n', (cx, by + 45.72), ref_at=(cx + 2.54, by + 44.45), val_at=(cx + 2.54, by + 46.99))
        pwr(sh, net, cc[1]); gnd(sh, cc[2])
    # data: each even pin straight through its 33R to the GPIO label. The resistors alternate
    # between two columns so their text has room at the 2.54 mm pin pitch.
    for n in range(1, 9):
        px, py = J[2 * n]
        if n % 2:
            cx, rx, vx = px + 12.7, px + 2.794, px + 6.35
        else:
            cx, rx, vx = px + 22.86, px + 29.21, px + 32.766
        rr = R(sh, '33', (cx, py), rot=90, ref_at=(rx, py - 1.27), val_at=(vx, py - 1.27))
        sh.wire((px, py), rr[1])
        sh.wire(rr[2], (px + 38.1, py)); sh.label('GP%d' % (g0 + n - 1), (px + 38.1, py), 0)

# ======================================================================================
# Headers
# ======================================================================================
hy = 215.9
sh.text('Headers', (185.42, hy - 2.54), size=2.54)


def header(n, ref, value, x, desc, nets):
    full = 'Connector_Generic:Conn_01x%02d' % n
    J = sh.symbol(full, SYM[full], ref, value, (x, hy + 12.7 + 2.54 * ((n - 1) // 2)),
                  fields=part('1x%d 2.54 mm pin header' % n, '', '', desc,
                              'Connector_PinHeader_2.54mm:PinHeader_1x%02d_P2.54mm_Vertical' % n),
                  ref_at=(x - 1.27, hy + 5.08), val_at=(x + 3.81, hy + 5.08))
    for i, net in enumerate(nets):
        p = J[i + 1]
        if net == 'GND':
            sh.wire(p, (p[0] - 5.08, p[1])); gnd(sh, (p[0] - 5.08, p[1]), rot=270)
        elif net == '+3V3':
            # left past the GND symbol on the pin above, then up to an upright +3V3
            top = J[1][1] - 2.54
            off = 12.7 if i < 2 else 17.78                 # further out when it has to pass net labels
            sh.wire(p, (p[0] - off, p[1]), (p[0] - off, top)); pwr(sh, '+3V3', (p[0] - off, top))
        else:
            sh.wire(p, (p[0] - 7.62, p[1])); sh.label(net, (p[0] - 7.62, p[1]), 180)
    return J


header(3, 'J4', 'UART', 200.66, 'Debug UART0: GND, TX (GP16), RX (GP17)', ['GND', 'GP16', 'GP17'])
sh.text('1 GND\n2 TX (GP16)\n3 RX (GP17)', (205.74, hy + 13.97))
header(4, 'J5', 'I2C', 241.3, 'I2C0: GND, 3V3, SCL (GP21), SDA (GP20)', ['GND', '+3V3', 'GP21', 'GP20'])
sh.text('1 GND\n2 3V3\n3 SCL (GP21)\n4 SDA (GP20)', (246.38, hy + 16.51))
for i, net in enumerate(['GP20', 'GP21']):
    x = 269.24 + 7.62 * i
    rr = R(sh, '10k', (x, hy + 12.7), ref_at=(x + 1.905, hy + 11.43), val_at=(x + 1.905, hy + 13.97))
    pwr(sh, '+3V3', rr[1])
    sh.wire(rr[2], (x, hy + 21.59)); sh.label(net, (x, hy + 21.59), 270)
# STEMMA QT / Qwiic socket on the same I2C bus (its own pin order: GND, 3V3, SDA, SCL)
QT = 'Connector_Generic_MountingPin:Conn_01x04_MountingPin'
J7 = sh.symbol(QT, SYM[QT], 'J7', 'STEMMA QT', (304.8, hy + 15.24),
               fields=part('SM04B-SRSS-TB(LF)(SN)', 'C160404', 'JST',
                           'STEMMA QT / Qwiic I2C socket: JST SH 4-pin 1.0 mm, side entry, SMD',
                           'Connector_JST:JST_SH_SM04B-SRSS-TB_1x04-1MP_P1.00mm_Horizontal'),
               ref_at=(295.91, hy + 5.08), val_at=(300.99, hy + 5.08))
p = J7[1]; sh.wire(p, (p[0] - 5.08, p[1])); gnd(sh, (p[0] - 5.08, p[1]), rot=270)
p = J7[2]; top = J7[1][1] - 2.54
sh.wire(p, (p[0] - 12.7, p[1]), (p[0] - 12.7, top)); pwr(sh, '+3V3', (p[0] - 12.7, top))
for n, net in [(3, 'GP20'), (4, 'GP21')]:
    p = J7[n]; sh.wire(p, (p[0] - 7.62, p[1])); sh.label(net, (p[0] - 7.62, p[1]), 180)
gnd(sh, J7['MP'])
sh.text('1 GND\n2 3V3\n3 SDA (GP20)\n4 SCL (GP21)', (309.88, hy + 16.51))
header(8, 'J6', 'SPARE', 350.52, 'Spare GPIO: GND, GP18, GP19, GP22, GP26-28 (ADC0-2), 3V3',
       ['GND', 'GP18', 'GP19', 'GP22', 'GP26', 'GP27', 'GP28', '+3V3'])
sh.text('1 GND\n2 GP18\n3 GP19\n4 GP22\n5 GP26 / ADC0\n6 GP27 / ADC1\n7 GP28 / ADC2\n8 3V3', (355.6, hy + 26.67))
sh.text('J4: debug UART, moved off GP0/1 so the outputs get GP0-15.\n'
        'J5 and J7: I2C0 with 10k pull-ups, for a small display or a sensor. J5 is a pin header in the\n'
        'order of the common 4-pin OLED modules; J7 is a STEMMA QT / Qwiic socket for ready-made cables.\n'
        'Mind the order: SCL and SDA swap places between the two.', (185.42, hy + 43.18))

# mounting holes
for i in range(4):
    x = 378.46 + 7.62 * i
    sh.symbol('Mechanical:MountingHole', SYM['Mechanical:MountingHole'], 'H%d' % (i + 1), 'M3', (x, hy + 12.7),
              fields={'Footprint': 'MountingHole:MountingHole_3.2mm_M3'}, in_bom=False,
              ref_at=(x - 1.27, hy + 8.89), val_at=(x - 1.27, hy + 17.78))
sh.text('Mounting holes', (375.92, hy + 5.08))

# ======================================================================================
# write files
# ======================================================================================
ls = S('lib_symbols')
for full in sorted(sh.lib):
    ls.append(sh.lib[full])
tree = S('kicad_sch', S('version', 20260306.0), S('generator', 'eeschema'), S('generator_version', '10.0'),
         S('uuid', ROOT), S('paper', 'A3'),
         S('title_block', S('title', 'LED budget board (Pico 2 W carrier, 16 strands)'), S('date', '2026-11-11'),
           S('rev', 'A'), S('comment', 1.0, 'Power and outputs follow led-processor-board')),
         ls)
tree += sh.items
tree.append(S('sheet_instances', S('path', '/', S('page', '1'))))
tree.append(S('embedded_fonts', Sym('no')))

os.makedirs(OUT_DIR, exist_ok=True)
with open(os.path.join(OUT_DIR, PROJECT + '.kicad_sch'), 'w') as f:
    f.write(sx.dump(tree) + '\n')

# project symbol library with the Pico 2 W symbol
lib_sym = copy.deepcopy(PICO)
lib_sym[1] = 'Pico_2_W'
lib = S('kicad_symbol_lib', S('version', 20251024.0), S('generator', 'kicad_symbol_editor'),
        S('generator_version', '10.0'), lib_sym)
with open(os.path.join(OUT_DIR, PROJECT + '.kicad_sym'), 'w') as f:
    f.write(sx.dump(lib) + '\n')
with open(os.path.join(OUT_DIR, 'sym-lib-table'), 'w') as f:
    f.write('(sym_lib_table\n  (version 7)\n  (lib (name "%s")(type "KiCad")(uri "${KIPRJMOD}/%s.kicad_sym")'
            '(options "")(descr "Pico 2 W carrier symbol"))\n)\n' % (PROJECT, PROJECT))
print('ok: R%d C%d' % (rn[0], cn[0]))
