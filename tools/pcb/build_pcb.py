#!/usr/bin/env python3
"""Build led-budget-board.kicad_pcb: placement, board outline, and the hand-planned copper.

    python3 tools/pcb/build_pcb.py NETLIST.xml OUT.kicad_pcb PROCESSOR_BOARD.kicad_pcb

Needs KiCad's pcbnew Python module. NETLIST.xml is `kicad-cli sch export netlist --format kicadxml`.

What is where (see the Layout section of README.md):
- Pico 2 W upright, USB at the top edge. GP0-15 are all on its left pin column.
- Both shrouds on the right edge, key notch facing into the board, pin 1 at the top: the same way
  round as an output board sitting to the right with its shroud edge towards this board, so the
  ribbons run straight with no twist.
- The 16 data lines: Pico pin -> 33R (left of the Pico) -> via -> straight across under the Pico on
  the bottom layer, between the pin rows -> fan down -> between the shroud's GND pins to the even pin.
- The 5 V buck is the processor board's layout, copied part for part and track for track.

Everything else is routed by hand further down, track by track.
"""
import sys, os, math
import xml.etree.ElementTree as ET
import pcbnew

NETXML, OUT, V1 = sys.argv[1:4]
STOCK = os.environ.get('KICAD_FOOTPRINT_DIR', '/usr/share/kicad/footprints')
mm = pcbnew.FromMM
MM = pcbnew.ToMM


def V(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


b = pcbnew.BOARD()

# ---------------------------------------------------------------- netlist
root = ET.parse(NETXML).getroot()
comps = {}
for c in root.find('components'):
    fp = c.findtext('footprint')
    if not fp:
        continue
    props = {p.get('name'): p.get('value') for p in c.findall('property')}
    props.setdefault('Datasheet', c.findtext('datasheet') or '')
    props.setdefault('Description', c.findtext('description') or '')
    comps[c.get('ref')] = dict(value=c.findtext('value'), fp=fp, props=props,
                               path=c.find('sheetpath').get('tstamps') + c.findtext('tstamps'))
pinnet = {}
netpins = {}
for n in root.find('nets'):
    for nd in n.findall('node'):
        pinnet[(nd.get('ref'), nd.get('pin'))] = n.get('name')
        netpins.setdefault(n.get('name'), []).append((nd.get('ref'), nd.get('pin')))


def net(name):
    n = b.FindNet(name)
    if n is None:
        n = pcbnew.NETINFO_ITEM(b, name)
        b.Add(n)
    return n


FP = {}
for ref, c in comps.items():
    lib, name = c['fp'].split(':')
    f = pcbnew.FootprintLoad(os.path.join(STOCK, lib + '.pretty'), name)
    f.SetFPID(pcbnew.LIB_ID(lib, name))
    f.SetReference(ref)
    f.SetValue(c['value'])
    f.SetPath(pcbnew.KIID_PATH(c['path']))
    for k in ('Datasheet', 'Description', 'LCSC', 'manufacturer', 'manufacturer_pn'):
        if k in c['props'] and c['props'][k] != '~':
            f.SetField(k, c['props'][k])
            for fld in f.GetFields():
                if fld.GetName() == k:
                    fld.SetVisible(False)
    b.Add(f)
    for p in f.Pads():
        nm = pinnet.get((ref, p.GetNumber()))
        if nm:
            p.SetNet(net(nm))
    FP[ref] = f


def place(ref, x, y, rot=0):
    f = FP[ref]
    f.SetOrientationDegrees(0)
    f.SetPosition(V(x, y))
    f.SetOrientationDegrees(rot)
    return f


def pad(ref, num):
    p = [p for p in FP[ref].Pads() if p.GetNumber() == str(num)][0].GetPosition()
    return (MM(p.x), MM(p.y))


def seg(netname, layer, w, *pts):
    for a, c in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(V(*a)); t.SetEnd(V(*c)); t.SetWidth(mm(w)); t.SetLayer(layer)
        t.SetNet(net(netname))
        b.Add(t)


def via(netname, x, y, dia=0.6, drill=0.3):
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(V(x, y)); v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetDrill(mm(drill)); v.SetWidth(pcbnew.F_Cu, mm(dia))
    v.SetNet(net(netname))
    b.Add(v)


# ---------------------------------------------------------------- outline and holes
X0, Y0, X1, Y1 = 100.0, 60.0, 161.5, 133.0
RAD = 3.0


def edge_line(x0, y0, x1, y1):
    s = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT)
    s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(mm(0.1))
    s.SetStart(V(x0, y0)); s.SetEnd(V(x1, y1)); b.Add(s)


def edge_arc(cx, cy, sx, sy, ang):
    s = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_ARC)
    s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(mm(0.1))
    s.SetCenter(V(cx, cy)); s.SetStart(V(sx, sy)); s.SetArcAngleAndEnd(pcbnew.EDA_ANGLE(ang, pcbnew.DEGREES_T), True)
    b.Add(s)


edge_line(X0 + RAD, Y0, X1 - RAD, Y0); edge_line(X1, Y0 + RAD, X1, Y1 - RAD)
edge_line(X1 - RAD, Y1, X0 + RAD, Y1); edge_line(X0, Y1 - RAD, X0, Y0 + RAD)
edge_arc(X1 - RAD, Y0 + RAD, X1 - RAD, Y0, 90); edge_arc(X1 - RAD, Y1 - RAD, X1, Y1 - RAD, 90)
edge_arc(X0 + RAD, Y1 - RAD, X0 + RAD, Y1, 90); edge_arc(X0 + RAD, Y0 + RAD, X0, Y0 + RAD, 90)

HOLE = 3.5
place('H1', X0 + HOLE, Y0 + HOLE); place('H2', X1 - HOLE, Y0 + HOLE)
place('H3', X0 + HOLE, Y1 - HOLE); place('H4', X1 - HOLE, Y1 - HOLE)

# ---------------------------------------------------------------- Pico, shrouds, data lines
PX, PY = 122.0, 63.5                 # Pico pin 1: USB end at the top edge
place('A1', PX, PY, 0)
XO = 153.6                            # shroud odd (GND) pin column; even column is 2.54 to the right
J_Y = {'J2': 72.7, 'J3': 101.9}       # pin 1 of each shroud
for j, y in J_Y.items():
    place(j, XO, y, 0)

W = 0.25
RX = PX - 3.8                         # resistor column
VX = PX - 5.6                         # via column
XEND = XO - 1.6                       # where the fan-out diagonals end
for g in range(16):
    npin = '/GP%d' % g
    a1 = [p for r, p in netpins[npin] if r == 'A1'][0]
    r = [r for r, p in netpins[npin] if r.startswith('R')][0]
    py = pad('A1', a1)[1]
    place(r, RX, py, 0)                                    # pad 2 (right) faces the Pico pin
    seg(npin, pcbnew.F_Cu, W, pad(r, 2), pad('A1', a1))
    out = pinnet[(r, '1')]                                 # resistor to shroud pin
    j, jpin = [(rr, p) for rr, p in netpins[out] if rr.startswith('J')][0]
    lane = py + 1.27                                       # between this pin row and the next
    p1 = pad(r, 1)
    seg(out, pcbnew.F_Cu, W, p1, (VX + 1.27, py), (VX, lane))
    via(out, VX, lane)
    tx, ty = pad(j, jpin)                                  # even pin; its lane is just above its row
    s = ty - 1.27
    d = s - lane
    assert d > 0, (g, d)
    tail = [(XO + 0.95, s), (XO + 2.22, ty), (tx, ty)]      # between two GND pins, then onto the even pin
    if g == 13:      # these three lanes would cross the Pico W antenna keep-out: go round below it
        mid = [(VX + 1.3, lane), (VX + 2.5, lane + 1.2), (VX + 2.5, 113.3), (VX + 3.7, 114.5),
               (XO - 4.0, 114.5), (XO - 4.0 + (114.5 - s), s)]
    elif g == 14:
        mid = [(VX + 1.2, lane + 1.2), (VX + 1.2, s - 1.2), (VX + 2.4, s)]
    elif g == 15:
        mid = [(VX, s - 1.21), (VX + 1.21, s)]
    else:
        mid = [(XEND - d, lane), (XEND, s)]
    seg(out, pcbnew.B_Cu, W, (VX, lane), *mid, *tail)

# decoupling at each shroud's 3V3 (pin 13) and 5V (pin 15)
for j in ('J2', 'J3'):
    for jpin in (13, 15):
        rail = pinnet[(j, str(jpin))]
        y = pad(j, jpin)[1]
        cands = sorted((r for r, p in netpins[rail] if r.startswith('C') and comps[r]['value'] == '100n'
                       and comps[r]['fp'].endswith('C_0402_1005Metric') and p == '1'), key=lambda r: int(r[1:]))
        c = cands[0 if j == 'J2' else 1]
        place(c, XO - 4.9, y, 0 if jpin == 13 else 180)    # 3V3 cap: pad 1 towards the 3V3 trunk on its left

# ---------------------------------------------------------------- power: terminal, D1, buck block
place('J1', 106.0, 71.0, -90)        # wire entry faces the left edge, housing fully on the board
place('D1', 111.6, 72.6, 90)         # anode up, next to J1 pin 1
place('D2', 151.3, 65.6, 0)          # +5V -> VSYS, between the Pico's VSYS pin and OUT1

# the processor board's buck, moved as a block
v1 = pcbnew.LoadBoard(V1)
BMAP = {'C27': 'C1', 'C28': 'C2', 'C29': 'C3', 'R20': 'R1', 'U7': 'U1', 'C30': 'C4', 'L2': 'L1',
        'R21': 'R2', 'R22': 'R3', 'C31': 'C5', 'C32': 'C6', 'C33': 'C7', 'C34': 'C8', 'R23': 'R4', 'D5': 'D3'}
NMAP = {'+12V': '+12V', '+5V': '+5V', 'GND': 'GND', '/Power/SW': '/SW', '/Power/FB': '/FB',
        'Net-(U7-EN)': 'Net-(U1-EN)', 'Net-(U7-BOOT)': 'Net-(U1-BOOT)', 'Net-(D5-A)': 'Net-(D3-A)'}
BOX = (123.4, 84.3, 137.0, 104.6)
DX, DY = -22.7, -7.0
for old, new in BMAP.items():
    f = v1.FindFootprintByReference(old)
    assert comps[new]['value'] == f.GetValue(), (old, new, comps[new]['value'], f.GetValue())
    for p in f.Pads():                                     # the two boards must agree pin for pin
        assert NMAP[p.GetNetname()] == pinnet[(new, p.GetNumber())], (old, new, p.GetNumber())
    place(new, MM(f.GetPosition().x) + DX, MM(f.GetPosition().y) + DY, f.GetOrientationDegrees())


def inbox(p):
    return BOX[0] <= MM(p.x) <= BOX[2] and BOX[1] <= MM(p.y) <= BOX[3]


tr = v1.Tracks()
segs, vias = [], []
for i in range(len(tr)):
    t = tr[i]
    if t.GetNetname() not in NMAP:
        continue
    name = NMAP[t.GetNetname()]
    if t.GetClass() == 'PCB_VIA':
        if inbox(t.GetPosition()):
            t = pcbnew.Cast_to_PCB_VIA(t)
            vias.append((name, round(MM(t.GetPosition().x) + DX, 4), round(MM(t.GetPosition().y) + DY, 4),
                         MM(t.GetWidth(pcbnew.F_Cu)), MM(t.GetDrill())))
    elif t.GetClass() == 'PCB_TRACK' and inbox(t.GetStart()) and inbox(t.GetEnd()):
        segs.append((name, t.GetLayer(), MM(t.GetWidth()),
                     (round(MM(t.GetStart().x) + DX, 4), round(MM(t.GetStart().y) + DY, 4)),
                     (round(MM(t.GetEnd().x) + DX, 4), round(MM(t.GetEnd().y) + DY, 4))))


def on_pad(name, pt):
    for ref in BMAP.values():
        for p in FP[ref].Pads():
            if p.GetNetname() == name and p.HitTest(V(*pt)):
                return True
    return False


# Drop the stubs that led out of the block on the processor board; they are reconnected below.
while True:
    ends = {}
    for s_ in segs:
        for pt in s_[3:5]:
            ends[pt] = ends.get(pt, 0) + 1
    for v_ in vias:
        ends[(v_[1], v_[2])] = ends.get((v_[1], v_[2]), 0) + 1
    bad = [s_ for s_ in segs if any(ends[pt] < 2 and not on_pad(s_[0], pt) for pt in s_[3:5])]
    badv = [v_ for v_ in vias if v_[0] != 'GND' and ends[(v_[1], v_[2])] < 2]
    if not bad and not badv:
        break
    segs = [s_ for s_ in segs if s_ not in bad]
    vias = [v_ for v_ in vias if v_ not in badv]
for name, layer, w, a, c in segs:
    seg(name, layer, w, a, c)
for name, x, y, dia, drill in vias:
    if name == '+5V':
        continue                     # the 5 V output leaves on the top layer here
    via(name, x, y, dia, drill)
ncopy = len(segs) + len(vias)
print('buck: copied', ncopy, 'tracks and vias')

# ---------------------------------------------------------------- bottom strip: headers, button, QT
HY = 128.5
place('J4', 112.1, HY, 90)           # UART, pin 1 (GND) on the left
place('J6', 121.0, HY, 90)           # SPARE, pin 1 (GND) on the left
place('J5', 150.52, HY, -90)         # I2C, pin 1 (GND) on the right
place('R21', 110.2, 121.8, 180)      # I2C pull-ups next to the QT socket, pad 2 (the bus) on the left
place('R22', 110.2, 123.3, 180)
place('SW1', 145.6, 63.4, 180)       # RUN, top edge next to the USB socket
place('J7', 103.3, 121.3, -90)       # STEMMA QT, opening at the left edge


# ---------------------------------------------------------------- the rest of the copper
F, B = pcbnew.F_Cu, pcbnew.B_Cu


def path(netname, layer, w, *pts, c=0.4):
    """A track through pts with every right-angle corner cut at 45 degrees."""
    out = [pts[0]]
    for a, m, z in zip(pts, pts[1:], pts[2:]):
        d1 = (m[0] - a[0], m[1] - a[1]); d2 = (z[0] - m[0], z[1] - m[1])
        l1 = math.hypot(*d1); l2 = math.hypot(*d2)
        if abs(d1[0] * d2[0] + d1[1] * d2[1]) < 1e-9 and l1 > 2 * c and l2 > 2 * c:
            out.append((m[0] - d1[0] / l1 * c, m[1] - d1[1] / l1 * c))
            out.append((m[0] + d2[0] / l2 * c, m[1] + d2[1] / l2 * c))
        else:
            out.append(m)
    out.append(pts[-1])
    seg(netname, layer, w, *[(round(x, 4), round(y, 4)) for x, y in out])


def a1(name):
    """The Pico pad on a net."""
    return pad('A1', [p for r, p in netpins[name] if r == 'A1'][0])


# 12 V in: terminal -> D1 -> the buck's input caps
path('/VIN_RAW', F, 0.8, pad('J1', 1), (108.5, 71.0), (108.9, 70.6), pad('D1', 2))
path('+12V', F, 0.5, pad('D1', 1), (113.0, 74.6), (114.4, 76.0), (114.4, 82.15), (113.848, 82.703))

# 5 V: buck output -> up the left of the data vias -> along the top edge -> D2 -> VSYS
TX5 = 115.3
path('+5V', F, 0.6, (114.14, 97.285), (TX5, 96.125), (TX5, 61.8), (TX5 + 0.6, 61.2), (152.35, 61.2),
     (152.95, 61.8), pad('D2', 2))
path('+5V', F, 0.25, (109.731, 78.1121), (109.731, 76.8))          # feedback divider top
via('+5V', 109.731, 76.8); via('+5V', TX5, 76.8)
seg('+5V', B, 0.4, (109.731, 76.8), (TX5, 76.8))
vs = a1('/VSYS')
path('/VSYS', F, 0.6, vs, (149.0, vs[1]), pad('D2', 1))
# 5 V down to pin 15 of both shrouds, between the pin columns on the top layer
XM = XO + 1.27
p15a, p15b = pad('J2', 15), pad('J3', 15)
seg('+5V', F, 0.3, pad('D2', 2), (152.95, 67.0), (XM, 67.0 + XM - 152.95), (XM, p15a[1] - 1.27), p15a,
    (XO, p15a[1] + 2.0), (XM, p15a[1] + 3.27), (XM, p15b[1] - 1.27), p15b)

# RUN: up the inside of the Pico's right pin column, out between pins 40 and 39, to the button
rn = a1('Net-(A1-RUN)')
seg('Net-(A1-RUN)', F, W, rn, (138.3, rn[1]), (138.0, rn[1] - 0.3), (138.0, 65.07), (138.3, 64.77), (141.0, 64.77),
    (142.37, 63.4), pad('SW1', 2))
via('GND', 150.0, 63.0); seg('GND', F, 0.4, pad('SW1', 1), (150.0, 63.4), (150.0, 63.0))

# The Pico's right-hand pins: a bundle down the gap between the Pico and the shrouds, then left along
# the bottom strip to the headers. Lower pins take the inner tracks, so nothing crosses.
BX = 141.2                           # innermost vertical
PITCH = 0.5
order = ['/GP16', '/GP17', '/GP18', '/GP19', '/GP20', '/GP21', '/GP22', '/GP26', '/GP27', '/GP28']
vx = {n: BX + PITCH * i for i, n in enumerate(order)}
dest = {'/GP16': ('J4', 2, 114.2), '/GP17': ('J4', 3, 114.7), '/GP18': ('J6', 2, 115.2), '/GP19': ('J6', 3, 115.7),
        '/GP22': ('J6', 4, 122.0), '/GP26': ('J6', 5, 122.5), '/GP27': ('J6', 6, 123.0), '/GP28': ('J6', 7, 123.5)}
for n, (j, jp, hy_) in dest.items():
    s0 = a1(n); e = pad(j, jp)
    path(n, F, W, s0, (vx[n], s0[1]), (vx[n], hy_), (e[0], hy_), e)

# 3.3 V: the outermost track of the bundle
X33 = 146.55
s0 = a1('+3V3'); e = pad('J6', 8)
path('+3V3', F, 0.5, s0, (X33, s0[1]), (X33, 124.2), (e[0], 124.2), e)
e = pad('J5', 2)
seg('+3V3', F, 0.5, (X33, 124.2), (X33, 126.0), (e[0], e[1] - 0.72), e)
for j in ('J2', 'J3'):
    p13 = pad(j, 13)
    c = [r for r, p in netpins['+3V3'] if r.startswith('C') and abs(pad(r, 1)[1] - p13[1]) < 0.1][0]
    seg('+3V3', F, 0.3, (X33, p13[1]), pad(c, 1))
    # below the pin row, so GND pin 11 above keeps its thermal spokes
    seg('+3V3', F, 0.3, (X33, p13[1] + 1.27), (XO - 2.0, p13[1] + 1.27), (XO - 0.73, p13[1]), p13)
    p15 = pad(j, 15)
    c = [r for r, p in netpins['+5V'] if r.startswith('C') and abs(pad(r, 1)[1] - p15[1]) < 0.1][0]
    seg('+5V', F, 0.3, pad(c, 1), p15)

# The top pour between the two shrouds is boxed in by the 3.3 V and 5 V tracks: tie it to the bottom pour
via('GND', 149.5, 94.0); via('GND', 151.0, 95.5)

# I2C: down the bundle, through to the bottom layer, to J5; and across the bottom strip to the QT socket
sda, scl = a1('/GP20'), a1('/GP21')
SDV, SCV = (141.9, 119.6), (143.0, 121.0)        # vias, below the last data lane
path('/GP20', F, W, sda, (vx['/GP20'], sda[1]), (vx['/GP20'], 116.2), c=0.4)
seg('/GP20', F, W, (vx['/GP20'], 116.2), (SDV[0], 116.2 + vx['/GP20'] - SDV[0]), SDV)
path('/GP21', F, W, scl, (vx['/GP21'], scl[1]), (vx['/GP21'], 116.6), c=0.4)
seg('/GP21', F, W, (vx['/GP21'], 116.6), (SCV[0], 116.6 + vx['/GP21'] - SCV[0]), SCV)
via('/GP20', *SDV); via('/GP21', *SCV)
e = pad('J5', 4)
seg('/GP20', B, W, SDV, (SDV[0], e[1] - 2.0), (e[0], e[1] - 1.0), e)
QD, QC = (108.6, 121.8), (107.6, 122.8)          # vias next to the QT socket's SDA and SCL pads
seg('/GP20', B, W, SDV, (QD[0] + 1.0, SDV[1]), (QD[0], SDV[1] + 1.0), QD)
via('/GP20', *QD)
seg('/GP20', F, W, pad('J7', 3), QD, pad('R21', 2))
e = pad('J5', 3)
seg('/GP21', B, W, SCV, (e[0] - 1.04, SCV[1]), (e[0], SCV[1] + 1.04), e, (e[0], e[1] + 1.4), (e[0] - 0.6, e[1] + 2.0),
    (QC[0] + 0.6, e[1] + 2.0), (QC[0], e[1] + 1.4), QC)   # under the header row, so it never crosses SDA
via('/GP21', *QC)
seg('/GP21', F, W, pad('J7', 4), QC, (108.7, 122.8), (109.2, 123.3), pad('R22', 2))
# 3.3 V for the QT socket and the pull-ups, from J6 pin 8 along the bottom layer
r1, r2 = pad('R21', 1), pad('R22', 1); q2 = pad('J7', 2)
seg('+3V3', F, 0.3, q2, (r1[0], q2[1]), r1, r2)
seg('+3V3', F, 0.3, (r1[0], q2[1]), (111.5, q2[1]))
via('+3V3', 111.5, q2[1])
e = pad('J6', 8)
seg('+3V3', B, 0.4, (111.5, q2[1]), (111.5, 125.4), (112.3, 126.2), (e[0] - 0.8, 126.2), (e[0], 127.0), e)

# ---------------------------------------------------------------- silkscreen
def to_fab(*refs):
    """Keep the reference in KiCad but off the printed board."""
    for r in refs:
        FP[r].Reference().SetLayer(pcbnew.F_Fab)


def ref_at(r, x, y, rot=0):
    t = FP[r].Reference()
    t.SetPosition(V(x, y)); t.SetTextAngleDegrees(rot)
    t.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8))); t.SetTextThickness(mm(0.13))


def text(s_, x, y, rot=0, size=0.9):
    t = pcbnew.PCB_TEXT(b)
    t.SetText(s_); t.SetLayer(pcbnew.F_SilkS); t.SetPosition(V(x, y)); t.SetTextAngleDegrees(rot)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size))); t.SetTextThickness(mm(size / 6))
    b.Add(t)


to_fab('H1', 'H2', 'H3', 'H4', 'J1', 'J2', 'J3', 'J4', 'J5', 'J6', 'J7', 'SW1',
       *[r for r in BMAP.values() if r != 'L1'])
ref_at('D1', 111.6, 68.2)
ref_at('R21', 110.2, 119.7); ref_at('R22', 113.3, 122.6)
text('J1 +12V', 105.2, 67.6); text('GND', 103.5, 77.5)
text('PWR', 113.4, 94.0, 90)
text('RUN', 145.6, 66.0)
text('OUT1 GP0-7', XO - 4.7, J_Y['J2'] + 6.5, 90); text('OUT2 GP8-15', XO - 4.7, J_Y['J3'] + 6.5, 90)
text('J7 QT I2C', 104.6, 116.4)
for j, name, labels in (('J4', 'J4 UART', ['GND', 'TX', 'RX']),
                        ('J6', 'J6 SPARE', ['GND', '18', '19', '22', '26', '27', '28', '3V3']),
                        ('J5', 'J5 I2C', ['GND', '3V3', 'SCL', 'SDA'])):
    xs = [pad(j, i + 1)[0] for i in range(len(labels))]
    for x, l in zip(xs, labels):
        if j == 'J5' and l == 'GND':                       # no room above it, under OUT2
            text(l, x + 3.3, HY)
        else:
            text(l, x, HY - 3.4, 90)
    text(name, sum(xs) / len(xs), HY + 3.0)
text('led-budget-board', 108.2, 98.7, size=0.8)
text('v1.0, Pico 2 W', 108.2, 100.2, size=0.8)
# the logo: the processor board's footprint scaled to 14 mm tall (logos.pretty)
g = pcbnew.FootprintLoad(os.path.join(os.path.dirname(os.path.abspath(OUT)), 'logos.pretty'), 'SJG_BigBrother')
g.SetFPID(pcbnew.LIB_ID('logos', 'SJG_BigBrother')); g.SetReference('G1'); g.SetPosition(V(108.2, 108.3))
b.Add(g)

# No bottom-layer pour among the shroud pins: the data lanes there would cut it into slivers that
# hang off the GND pins by one spoke. Those pins get their ground from the top pour.
for j in ('J2', 'J3'):
    y0 = pad(j, 1)[1]
    k = pcbnew.ZONE(b)
    k.SetIsRuleArea(True)
    k.SetLayer(pcbnew.B_Cu)
    k.SetZoneName(j + ' pins: no bottom pour')
    k.SetDoNotAllowZoneFills(True); k.SetDoNotAllowTracks(False); k.SetDoNotAllowVias(False)
    k.SetDoNotAllowPads(False); k.SetDoNotAllowFootprints(False)
    o = k.Outline(); o.NewOutline()
    for x, y in ((XO - 1.5, y0 - 2.8), (XO + 4.0, y0 - 2.8), (XO + 4.0, y0 + 19.2), (XO - 1.5, y0 + 19.2)):
        o.Append(mm(x), mm(y))
    b.Add(k)

# ---------------------------------------------------------------- GND pours
for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
    z = pcbnew.ZONE(b)
    z.SetLayer(layer)
    z.SetNet(net('GND'))
    z.SetZoneName('GND ' + b.GetLayerName(layer))
    o = z.Outline()
    o.NewOutline()
    for x, y in ((X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)):
        o.Append(mm(x), mm(y))
    z.SetLocalClearance(mm(0.25))
    z.SetMinThickness(mm(0.2))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(mm(0.3))
    z.SetThermalReliefSpokeWidth(mm(0.4))
    b.Add(z)

b.BuildConnectivity()
zs = b.Zones()
if os.environ.get('FILL', '1') == '1':
    pcbnew.ZONE_FILLER(b).Fill(zs)
pcbnew.SaveBoard(OUT, b, True)
print('saved', OUT)
