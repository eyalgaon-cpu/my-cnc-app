import streamlit as st
import re, os, zipfile
import pandas as pd
import math
from collections import defaultdict
from io import BytesIO

# חייב להיות פקודה ראשונה
st.set_page_config(page_title="Darwish CNC Pro 23.0", layout="wide")

# הגדרות כלים מקוריות של אבי
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
    
    geometries = {}
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        bid, content = parts[i], parts[i+1]
        pts = []
        for elem in re.split(r'\$E\d+', content):
            x_m = re.search(r'X=([\d.-]+)', elem)
            y_m = re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m: pts.append([float(x_m.group(1)), float(y_m.group(1))])
        if pts: geometries[bid] = pts

    raw_drills, raw_millings = [], []
    # סריקה יסודית של כל הקידוחים
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        try:
            xa = float(re.search(r'XA="([\d.-]+)"', b).group(1))
            ya = float(re.search(r'YA="([\d.-]+)"', b).group(1))
            ti = float(re.search(r'TI="([\d.-]+)"', b).group(1))
            du = float(re.search(r'DU="([\d.-]+)"', b).group(1))
            an = int(re.search(r'AN="(\d+)"', b).group(1)) if 'AN="' in b else 1
            ab = float(re.search(r'AB="([\d.-]+)"', b).group(1)) if 'AB="' in b else 0
            wi = float(re.search(r'WI="([\d.-]+)"', b).group(1)) if 'WI="' in b else 0
            tno = re.search(r'TNO="(\d+)"', b).group(1) if 'TNO="' in b else ""
            t_final = id_map.get(tno, dia_map.get(du, "T44"))
            for i in range(an):
                nx, ny = xa + i*ab*math.cos(math.radians(wi)), ya + i*ab*math.sin(math.radians(wi))
                raw_drills.append({'x': nx, 'y': ny, 'z': thickness-ti, 't': t_final})
        except: continue

    # סריקה יסודית של כל הכרסומים
    for m in re.finditer(r'<105(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        try:
            geo_match = re.search(r'EA="(\d+):', b)
            if geo_match:
                eid = geo_match.group(1)
                za = float(re.search(r'ZA="([\d.-]+)"', b).group(1))
                tno = re.search(r'TNO="(\d+)"', b).group(1) if 'TNO="' in b else "142"
                raw_millings.append({'geo_id': eid, 'z': za, 't': id_map.get(tno, "T2")})
        except: continue

    # חישוב איפוס - רק לפי חלקים פעילים (מתעלם מבלוק 1)
    active_x = [d['x'] for d in raw_drills] + [p[0] for bid, pts in geometries.items() if bid != "1" for p in pts]
    active_y = [d['y'] for d in raw_drills] + [p[1] for bid, pts in geometries.items() if bid != "1" for p in pts]
    
    if active_x and active_y:
        mx, my = min(active_x), min(active_y)
        for d in raw_drills:
            if zero_nesting: d['x'] -= mx; d['y'] -= my
            d['x'] += margin; d['y'] += margin
            if swap_axes: d['x'], d['y'] = d['y'], d['x']
        for bid, pts in geometries.items():
            for p in pts:
                if zero_nesting and bid != "1": p[0] -= mx; p[1] -= my
                p[0] += margin; p[1] += margin
                if swap_axes: p[0], p[1] = p[1], p[0]

    nc, ln, last_t = [f"G90 {offset}"], 10, ""
    # קידוחים
    for tool in sorted(list(set(d['t'] for d in raw_drills))):
        for d in sorted([dr for dr in raw_drills if dr['t']==tool], key=lambda x: (x['x'], x['y'])):
            if d['t'] != last_t:
                nc.extend([f"N{ln} {d['t']} M06", f"N{ln+5} G43 H{d['t'][1:]} S4000 M03"]); ln, last_t = ln+10, d['t']
            nc.extend([f"N{ln} G00 X{d['x']:.3f} Y{d['y']:.3f}", f"N{ln+5} G01 Z{d['z']:.3f} F2000", f"N{ln+10} G00 Z{thickness+10:.3f}"]); ln+=15
    # כרסומים
    for m in sorted(raw_millings, key=lambda x: x['t']):
        if m['t'] != last_t:
            nc.extend([f"N{ln} {m['t']} M06", f"N{ln+5} G43 H{m['t'][1:]} S17000 M03"]); ln, last_t = ln+10, m['t']
        pts = geometries.get(m['geo_id'])
        if pts:
            for zv in ([m['z']] if num_passes!=2 else [2.0, -0.2]):
                nc.append(f"N{ln} G00 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}"); ln+=5
                nc.append(f"N{ln} G01 Z{zv:.3f} F3000"); ln+=5
                for p in pts[1:]: nc.append(f"N{ln} G01 X{p[0]:.3f} Y{p[1]:.3f}"); ln+=5
                nc.append(f"N{ln} G00 Z{thickness+10:.3f}"); ln+=5
    nc.append(
