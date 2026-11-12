#!/usr/bin/env python3
"""Make the JLCPCB upload set in production/ for FULL assembly (SMD and through-hole):

    production/led-budget-board-gerbers.zip   gerbers + drill
    production/jlcpcb-bom.csv                 one line per LCSC part
    production/jlcpcb-cpl.csv                 where each part goes
    production/bom-full.csv                   every part, for people

Run from the repo root with KiCad's Python (needs pcbnew and kicad-cli):

    kicad-cli sch export netlist --format kicadxml -o /tmp/net.xml led-budget-board.kicad_sch
    python3 tools/jlc.py /tmp/net.xml

A1 is the Pico 2 W itself, which JLC does not fit. In its place the BOM and placement file carry two
1x20 sockets, A1A (the GP0-15 pin column) and A1B (the other column). The Pico plugs in afterwards.
"""
import csv, glob, os, subprocess, sys, tempfile, zipfile
import xml.etree.ElementTree as ET
import pcbnew

NAME = 'led-budget-board'
BOARD = NAME + '.kicad_pcb'
OUT = 'production'
SOCKET = ('2.54-1*20P female header', 'C2905423', 'Kinghelm KH-2.54FH-1X20P-H8.5')   # two of these carry the Pico
NOT_FITTED = {'A1': 'Raspberry Pi Pico 2 W (SC1633): yours, plugs into sockets A1A and A1B',
              'H1': 'M3 mounting hole', 'H2': 'M3 mounting hole', 'H3': 'M3 mounting hole', 'H4': 'M3 mounting hole'}
# JLC's models for the shrouds, sockets and pin headers lie a quarter turn anticlockwise of KiCad's
# footprints (seen in JLC's placement preview, 2026-11-12): this is added to KiCad's angle.
# Add ref: degrees here if the preview shows another part turned.
ROT_FIX = {'J2': -90, 'J3': -90, 'J4': -90, 'J5': -90, 'J6': -90, 'A1A': -90, 'A1B': -90}
LAYERS = 'F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts'
MM = pcbnew.ToMM


def cli(*a):
    subprocess.run(['kicad-cli', 'pcb', 'export', *a], check=True, stdout=subprocess.DEVNULL)


def key(d):
    h = d.rstrip('0123456789AB') or d
    n = ''.join(c for c in d[len(h):] if c.isdigit())
    return (h, int(n or 0), d)


os.makedirs(OUT, exist_ok=True)
b = pcbnew.LoadBoard(BOARD)
fps = {f.GetReference(): f for f in b.GetFootprints()}

# ---- parts, from the schematic's netlist
parts = {}
for c in ET.parse(sys.argv[1]).getroot().find('components'):
    pr = {p.get('name'): p.get('value') for p in c.findall('property')}
    parts[c.get('ref')] = dict(value=c.findtext('value'), fp=(c.findtext('footprint') or '').split(':')[-1],
                               lcsc=pr.get('LCSC', ''), mpn=pr.get('manufacturer_pn', ''))
missing = [r for r, p in parts.items() if not p['lcsc'] and r not in NOT_FITTED]
assert not missing, 'no LCSC number: %s' % missing
assert set(parts) <= set(fps), 'in the schematic but not on the board: %s' % (set(parts) - set(fps))


def centre(f, pads=None):
    """Middle of the part: its pads' bounding box. THT footprints have their origin on pin 1."""
    ps = [p.GetPosition() for p in f.Pads() if pads is None or p.GetNumber() in pads]
    xs = [p.x for p in ps]; ys = [p.y for p in ps]
    return MM((min(xs) + max(xs)) // 2), MM((min(ys) + max(ys)) // 2)


place = {}       # designator -> (x, y, rotation), KiCad board coordinates
lines = {}       # LCSC -> [comment, designators, footprint]
for r, p in parts.items():
    if r in NOT_FITTED:
        continue
    f = fps[r]
    smd = bool(f.GetAttributes() & pcbnew.FP_SMD)
    x, y = (MM(f.GetPosition().x), MM(f.GetPosition().y)) if smd else centre(f)
    place[r] = (x, y, f.GetOrientationDegrees())
    lines.setdefault(p['lcsc'], [p['mpn'] or p['value'], [], p['fp']])[1].append(r)
a1 = fps['A1']
for d, pins in (('A1A', {str(i) for i in range(1, 21)}), ('A1B', {str(i) for i in range(21, 41)})):
    x, y = centre(a1, pins)
    place[d] = (x, y, a1.GetOrientationDegrees())
    lines.setdefault(SOCKET[1], [SOCKET[0], [], 'PinSocket_1x20_P2.54mm_Vertical'])[1].append(d)

with open(os.path.join(OUT, 'jlcpcb-bom.csv'), 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #'])
    for lcsc, (c, refs, fp) in sorted(lines.items(), key=lambda kv: key(sorted(kv[1][1], key=key)[0])):
        w.writerow([c, ','.join(sorted(refs, key=key)), fp, lcsc])

# JLC's placement file: millimetres, Y up, the same origin as the gerbers (KiCad's page origin)
with open(os.path.join(OUT, 'jlcpcb-cpl.csv'), 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
    for d in sorted(place, key=key):
        x, y, rot = place[d]
        w.writerow([d, '%.4fmm' % x, '%.4fmm' % -y, 'Top', '%.1f' % ((rot + ROT_FIX.get(d, 0)) % 360)])

with open(os.path.join(OUT, 'bom-full.csv'), 'w', newline='') as fh:
    w = csv.writer(fh)
    w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC', 'Manufacturer PN', 'Qty', 'Note'])
    for lcsc, (c, refs, fp) in sorted(lines.items(), key=lambda kv: key(sorted(kv[1][1], key=key)[0])):
        refs = sorted(refs, key=key)
        tht = not all(r in fps and fps[r].GetAttributes() & pcbnew.FP_SMD for r in refs)
        mpn = SOCKET[2] if lcsc == SOCKET[1] else parts[refs[0]]['mpn']
        val = SOCKET[0] if lcsc == SOCKET[1] else parts[refs[0]]['value']
        w.writerow([val, ','.join(refs), fp, lcsc, mpn, len(refs), 'Through-hole' if tht else ''])
    for r in sorted(NOT_FITTED, key=key):
        w.writerow([parts[r]['value'], r, parts[r]['fp'], '', parts[r]['mpn'], 1, 'Not fitted by JLC: ' + NOT_FITTED[r]])

with tempfile.TemporaryDirectory() as t:
    g = os.path.join(t, 'gerbers')
    cli('gerbers', '--layers', LAYERS, '--check-zones', '-o', g + '/', BOARD)
    cli('drill', '--excellon-separate-th', '-o', g + '/', BOARD)
    with zipfile.ZipFile(os.path.join(OUT, NAME + '-gerbers.zip'), 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(glob.glob(g + '/*')):
            zf.write(f, os.path.basename(f))

n_smd = sum(1 for d in place if d in fps and fps[d].GetAttributes() & pcbnew.FP_SMD)
print('BOM lines: %d, parts placed: %d (%d SMD, %d through-hole)' % (len(lines), len(place), n_smd, len(place) - n_smd))
