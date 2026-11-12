#!/bin/sh
# render.sh board.kicad_pcb out.png [px-per-mm] [layers]
B=$1; O=$2; K=${3:-14}; L=${4:-B.Cu,F.Cu,F.Silkscreen,F.Fab,Edge.Cuts}
T=$(mktemp -d -p "$(dirname "$O")")
kicad-cli pcb export svg --mode-single -l "$L" --page-size-mode 2 --exclude-drawing-sheet -o "$T/b.svg" "$B" >/dev/null
python3 - "$T/b.svg" "$O" "$K" <<'PY'
import sys, cairosvg, re
svg, out, k = sys.argv[1:]
s = open(svg).read()
w = float(re.search(r'width="([\d.]+)', s).group(1))
cairosvg.svg2png(bytestring=s.encode(), write_to=out, output_width=int(w * float(k)), background_color='#101010')
PY
rm -rf "$T"
