#!/usr/bin/env python3
"""Build led-budget-board.kicad_pcb: placement, board outline, and the hand-planned copper.

    python3 tools/pcb/build_pcb.py NETLIST.xml OUT.kicad_pcb PROCESSOR_BOARD.kicad_pcb

Needs KiCad's pcbnew Python module. NETLIST.xml is `kicad-cli sch export netlist --format kicadxml`.

What is fixed here (see docs/layout.md):
- Pico 2 W upright, USB at the top edge. GP0-15 are all on its left pin column.
- Both shrouds on the right edge, key notch facing into the board, pin 1 at the top: the same way
  round as an output board sitting to the right with its shroud edge towards this board, so the
  ribbons run straight with no twist.
- The 16 data lines: Pico pin -> 33R (left of the Pico) -> via -> straight across under the Pico on
  the bottom layer, between the pin rows -> fan down -> between the shroud's GND pins to the even pin.
- The 5 V buck is the processor board's layout, copied part for part and track for track.

Everything else is left for the autorouter (tools/pcb/route.sh).
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
        place(c, XO - 4.9, y, 180)                         # pad 1 (the rail) next to the shroud pin

# ---------------------------------------------------------------- power: terminal, D1, buck block
place('J1', 106.0, 71.0, -90)        # wire entry faces the left edge, housing fully on the board
place('D1', 111.6, 72.6, 90)         # anode up, next to J1 pin 1
place('D2', 145.3, 63.6, 0)          # +5V -> VSYS, next to the Pico's VSYS pin

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


# Drop the stubs that led out of the block on the processor board (the autorouter reconnects them).
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
    via(name, x, y, dia, drill)
ncopy = len(segs) + len(vias)
print('buck: copied', ncopy, 'tracks and vias')

# ---------------------------------------------------------------- bottom strip: headers, button, QT
HY = 128.5
place('J6', 109.5, HY, 90)           # SPARE, pin 1 on the left
place('J5', 131.5, HY, 90)           # I2C
place('J4', 143.4, HY, 90)           # UART
place('R21', 133.3, 124.4, 90)
place('R22', 135.9, 124.4, 90)
place('SW1', 143.0, 121.0, 0)        # RUN
place('J7', 103.3, 121.3, -90)       # STEMMA QT, opening at the left edge

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
