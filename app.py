import streamlit as st
import re, os, zipfile
import pandas as pd
import math
from collections import defaultdict
from io import BytesIO

st.set_page_config(page_title="Darwish CNC Pro 22.0", layout="wide")

DEFAULT_TOOLS = [
    {"ID_MPR": "142", "קוטר_ממ": 6.0, "תיאור": "כרסום 6", "T_CNC": "T2"},
    {"ID_MPR": "158", "קוטר_ממ": 8.0, "תיאור": "כרסום 8", "T_CNC": "T3"},
    {"ID_MPR": "128", "קוטר_ממ": 12.0, "תיאור": "כרסום 12", "T_CNC": "T4"},
    {"ID_MPR": "121", "קוטר_ממ": 5.0, "תיאור": "מקדח 5", "T_CNC": "T44"},
    {"ID_MPR": "149", "קוטר_ממ": 15.0, "תיאור": "מקדח 15", "T_CNC": "T49"},
    {"ID_MPR": "135", "קוטר_ממ": 35.0, "תיאור": "מקדח 35", "T_CNC": "T6"}
]

def convert_logic(mpr_text, tool_df, num_passes, swap_axes, offset, zero_nesting, margin):
    id_map = {str(row['ID_MPR']): row['T_CNC'] for _, row in tool_df.iterrows()}
    dia_map = {float(row['קוטר_ממ']): row['T_CNC'] for _, row in tool_df.iterrows() if row['קוטר_ממ'] > 0}
    t_m = re.search(r't="([\d.]+)"', mpr_text)
    thickness = float(t_m.group(1)) if t_m else 16.5
    
    geos = {}
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        bid, content = parts[i], parts[i+1]
        pts = []
        for e in re.split(r'\$E\d+', content):
            x, y = re.search(r'X=([\d.-]+)', e), re.search(r'Y=([\d.-]+)', e)
            if x and y: pts.append([float(x.group(1)), float(y.group(1))])
        if pts: geos[bid] = pts

    raw_drills, raw_millings = [], []
    for m in re.finditer(r'<102(.*?)\!', mpr_text, re.DOTALL):
        b = m.group(1)
        xa, ya = float(re.search(r'XA="([\d.-]+)"', b).group(1)), float(re.search(r'YA="([\d.-]+)"', b).group(1))
        ti, du = float(re.search(r'TI="([\d.-]+)"', b).group(1)), float(re.search(r'DU="([\d.-]+)"', b).group(1))
        an = int(re.search(r'AN="(\d+)"', b).group(1)) if 'AN="' in b else 1
        ab = float(re.search(r'AB="([\d.-]+)"', b).group(1)) if 'AB="' in b else 0
        wi = float(re.search(r'WI="([\d.-]+)"', b).group(1)) if 'WI="' in b else 0
        tno = re.search(r'TNO="(\d+)"', b).group(1) if 'TNO="' in b else ""
        t_final = id_map.get(tno, dia_map.get(du, "T44"))
        for i in range(an):
            raw_drills.append({'x': xa + i*ab*math.cos(math.radians(wi)), 'y': ya + i*ab*math.sin(math.radians(wi)), 'z': thickness-ti, 't': t_final})

    for m in re.finditer(r'<105(.*?)\!', mpr_text, re.DOTALL):
        b = m.group(1)
        gid = re.search(r'EA="(\d+):', b).group(1)
        za = float(re.search(r'ZA="([\d.-]+)"', b).group(1))
        tno = re.search(r'TNO="(\d+)"', b).group(1) if 'TNO="' in b else "142"
        raw_millings.append({'geo_id': gid, 'z': za, 't': id_map.get(tno, "T2")})

    other_geos = [p for bid, pts in geos.items() if bid != "1" for p in pts]
    all_x = [d['x'] for d in raw_drills] + [p[0] for p in other_geos]
    all_y = [d['y'] for d in raw_drills] + [p[1] for p in other_geos]
    if all_x and all_y:
        mx, my = min(all_x), min(all_y)
        for d in raw_drills:
            if zero_nesting: d['x'] -= mx; d['y'] -= my
            d['x'] += margin; d['y'] += margin
            if swap_axes: d['x'], d['y'] = d['y'], d['x']
        for bid, pts in geos.items():
            for p in pts:
                if zero_nesting and bid != "1": p[0] -= mx; p[1] -= my
                p[0] += margin; p[1] += margin
                if swap_axes: p[0], p[1] = p[1], p[0]

    nc, ln, last_t = [f"G90 {offset}"], 10, ""
    for tool in sorted(list(set(d['t'] for d in raw_drills))):
        for d in sorted([dr for dr in raw_drills if dr['t']==tool], key=lambda x: (x['x'], x['y'])):
            if d['t'] != last_t:
                nc.extend([f"N{ln} {d['t']} M06", f"N{ln+5} G43 H{d['t'][1:]} S4000 M03"]); ln, last_t = ln+10, d['t']
            nc.extend([f"N{ln} G00 X{d['x']:.3f} Y{d['y']:.3f}", f"N{ln+5} G01 Z{d['z']:.3f} F2000", f"N{ln+10} G00 Z{thickness+10:.3f}"]); ln+=15
    for m in sorted(raw_millings, key=lambda x: x['t']):
        if m['t'] != last_t:
            nc.extend([f"N{ln} {m['t']} M06", f"N{ln+5} G43 H{m['t'][1:]} S17000 M03"]); ln, last_t = ln+10, m['t']
        pts = geos.get(m['geo_id'])
        if pts:
            z_lvls = [m['z']] if num_passes != 2 else [2.0, -0.2]
            for zv in z_lvls:
                nc.append(f"N{ln} G00 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}"); ln+=5
                nc.append(f"N{ln} G01 Z{zv:.3f} F3000"); ln+=5
                for p in pts[1:]: nc.append(f"N{ln} G01 X{p[0]:.3f} Y{p[1]:.3f}"); ln+=5
                nc.append(f"N{ln} G00 Z{thickness+10:.3f}"); ln+=5
    nc.append(f"N{ln} M30")
    return "\n".join(nc)

# ... (Streamlit UI remains same)
