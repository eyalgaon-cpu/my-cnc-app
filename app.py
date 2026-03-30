import streamlit as st
import re, os, zipfile
import pandas as pd
import math
from collections import defaultdict
from io import BytesIO

st.set_page_config(page_title="Darwish CNC Pro 21.0", layout="wide")

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
    t_match = re.search(r't="([\d.]+)"', mpr_text)
    thickness = float(t_match.group(1)) if t_match else 16.5
    
    geometries = {}
    # פיצול לפי בלוקים של גיאומטריה
    geo_sections = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(geo_sections), 2):
        bid, content = geo_sections[i], geo_sections[i+1]
        pts = []
        for elem in re.split(r'\$E\d+', content):
            x_m, y_m = re.search(r'X=([\d.-]+)', elem), re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m: pts.append([float(x_m.group(1)), float(y_m.group(1))])
        if pts: geometries[bid] = pts

    raw_drills, raw_millings = [], []
    
    # סריקת קידוחים (Regex גמיש יותר)
    for m in re.finditer(r'<102(.*?)(?=<|\!)', mpr_text, re.DOTALL):
        block = m.group(1)
        xa = float(re.search(r'XA="([\d.-]+)"', block).group(1))
        ya = float(re.search(r'YA="([\d.-]+)"', block).group(1))
        ti = float(re.search(r'TI="([\d.-]+)"', block).group(1))
        du = float(re.search(r'DU="([\d.-]+)"', block).group(1))
        an = int(re.search(r'AN="(\d+)"', block).group(1)) if 'AN="' in block else 1
        ab = float(re.search(r'AB="([\d.-]+)"', block).group(1)) if 'AB="' in block else 0
        wi = float(re.search(r'WI="([\d.-]+)"', block).group(1)) if 'WI="' in block else 0
        tno = re.search(r'TNO="(\d+)"', block).group(1) if 'TNO="' in block else ""
        t_final = id_map.get(tno, dia_map.get(du, "T44"))
        for i in range(an):
            nx, ny = xa + i*ab*math.cos(math.radians(wi)), ya + i*ab*math.sin(math.radians(wi))
            raw_drills.append({'x': nx, 'y': ny, 'z': thickness-ti, 't': t_final})

    # סריקת כרסומים (Regex גמיש יותר)
    for m in re.finditer(r'<105(.*?)(?=<|\!)', mpr_text, re.DOTALL):
        block = m.group(1)
        geo_match = re.search(r'EA="(\d+):', block)
        if geo_match:
            eid = geo_match.group(1)
            za = float(re.search(r'ZA="([\d.-]+)"', block).group(1))
            tno = re.search(r'TNO="(\d+)"', block).group(1) if 'TNO="' in block else "142"
            raw_millings.append({'geo_id': eid, 'z': za, 't': id_map.get(tno, "T2")})

    # איפוס ומיקום (Zero Nesting)
    other_geos = [p for bid, pts in geometries.items() if bid != "1" for p in pts]
    all_x = [d['x'] for d in raw_drills] + [p[0] for p in other_geos]
    all_y = [d['y'] for d in raw_drills] + [p[1] for p in other_geos]
    
    if all_x and all_y:
        mx, my = min(all_x), min(all_y)
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
    
    # מיון וכתיבה (קידוחים קודם)
    for tool in sorted(list(set(d['t'] for d in raw_drills))):
        for d in sorted([dr for dr in raw_drills if dr['t']==tool], key=lambda x: (x['x'], x['y'])):
            if d['t'] != last_t:
                nc.extend([f"N{ln} {d['t']} M06", f"N{ln+5} G43 H{d['t'][1:]} S4000 M03"]); ln, last_t = ln+10, d['t']
            nc.extend([f"N{ln} G00 X{d['x']:.3f} Y{d['y']:.3f}", f"N{ln+5} G01 Z{d['z']:.3f} F2000", f"N{ln+10} G00 Z{thickness+10:.3f}"]); ln+=15

    # כרסומים בסוף
    for m in sorted(raw_millings, key=lambda x: x['t']):
        if m['t'] != last_t:
            nc.extend([f"N{ln} {m['t']} M06", f"N{ln+5} G43 H{m['t'][1:]} S17000 M03"]); ln, last_t = ln+10, m['t']
        pts = geometries.get(m['geo_id'])
        if pts:
            # אם נבחר "2 פסיעות" - הקוד יתעלם מה-ZA של ה-MPR וייצר 2.0 ומינוס 0.2
            z_levels = [m['z']] if num_passes != 2 else [2.0, -0.2]
            for zv in z_levels:
                nc.append(f"N{ln} G00 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}"); ln+=5
                nc.append(f"N{ln} G01 Z{zv:.3f} F3000"); ln+=5
                for p in pts[1:]: nc.append(f"N{ln} G01 X{p[0]:.3f} Y{p[1]:.3f}"); ln+=5
                nc.append(f"N{ln} G00 Z{thickness+10:.3f}"); ln+=5
    nc.append(f"N{ln} M30")
    return "\n".join(nc)

# ... (Streamlit UI code remains same)
