import streamlit as st
import re, os, zipfile
import pandas as pd
import math
from collections import defaultdict
from io import BytesIO

# חובה: פקודה ראשונה באפליקציה
st.set_page_config(page_title="Darwish CNC Pro 25.0", layout="wide")

DEFAULT_TOOLS = [
    {"ID_MPR": "142", "קוטר_ממ": 6.0, "תיאור": "כרסום 6", "T_CNC": "T2"},
    {"ID_MPR": "158", "קוטר_ממ": 8.0, "תיאור": "כרסום 8", "T_CNC": "T3"},
    {"ID_MPR": "128", "קוטר_ממ": 12.0, "תיאור": "כרסום 12", "T_CNC": "T4"},
    {"ID_MPR": "121", "קוטר_ממ": 5.0, "תיאור": "מקדח 5", "T_CNC": "T44"},
    {"ID_MPR": "149", "קוטר_ממ": 15.0, "תיאור": "מקדח 15", "T_CNC": "T49"},
    {"ID_MPR": "135", "קוטר_ממ": 35.0, "תיאור": "מקדח 35", "T_CNC": "T6"}
]

def safe_val(pattern, text, default=0.0, is_int=False):
    match = re.search(pattern, text)
    if not match: return 0 if is_int else default
    return int(match.group(1)) if is_int else float(match.group(1))

def convert_logic(mpr_text, tool_df, num_passes, swap_axes, offset, zero_nesting, margin, z_offset):
    id_map = {str(row['ID_MPR']): row['T_CNC'] for _, row in tool_df.iterrows()}
    dia_map = {float(row['קוטר_ממ']): row['T_CNC'] for _, row in tool_df.iterrows() if row['קוטר_ממ'] > 0}
    thickness = safe_val(r't="([\d.]+)"', mpr_text, 16.5)
    
    geometries = {}
    blocks = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(blocks), 2):
        bid, content = blocks[i], blocks[i+1]
        pts = []
        for elem in re.split(r'\$E\d+', content):
            x, y = re.search(r'X=([\d.-]+)', elem), re.search(r'Y=([\d.-]+)', elem)
            if x and y: pts.append([float(x.group(1)), float(y.group(1))])
        if pts: geometries[bid] = pts

    raw_drills, raw_millings = [], []
    sections = mpr_text.split('<')
    for idx, sec in enumerate(sections):
        if sec.startswith('102'): # קידוחים
            xa, ya = safe_val(r'XA="([\d.-]+)"', sec), safe_val(r'YA="([\d.-]+)"', sec)
            ti, du = safe_val(r'TI="([\d.-]+)"', sec), safe_val(r'DU="([\d.-]+)"', sec)
            an, ab = safe_val(r'AN="(\d+)"', sec, 1, True), safe_val(r'AB="([\d.-]+)"', sec)
            wi = safe_val(r'WI="([\d.-]+)"', sec)
            tno_m = re.search(r'TNO="(\d+)"', sec)
            t_final = id_map.get(tno_m.group(1) if tno_m else "", dia_map.get(du, "T44"))
            for i in range(an):
                nx = xa + i * ab * math.cos(math.radians(wi))
                ny = ya + i * ab * math.sin(math.radians(wi))
                # החלת תוספת עומק (z_offset)
                raw_drills.append({'x': nx, 'y': ny, 'z': (thickness - ti) - z_offset, 't': t_final, 'group': idx})
        
        elif sec.startswith('105'): # כרסומים
            geo_match = re.search(r'EA="(\d+):', sec)
            if geo_match:
                eid = geo_match.group(1)
                za = safe_val(r'ZA="([\d.-]+)"', sec)
                tno_m = re.search(r'TNO="(\d+)"', sec)
                raw_millings.append({'geo_id': eid, 'z': za - z_offset, 't': id_map.get(tno_m.group(1) if tno_m else "142", "T2")})

    # איפוס ומיקום
    parts_x = [d['x'] for d in raw_drills] + [p[0] for bid, pts in geometries.items() if bid != "1" for p in pts]
    parts_y = [d['y'] for d in raw_drills] + [p[1] for bid, pts in geometries.items() if bid != "1" for p in pts]
    if parts_x and parts_y:
        mx, my = min(parts_x), min(parts_y)
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
    # יצירת NC לקידוחים - מיון לפי כלי ואז לפי קבוצה (למניעת קפיצות בקבינאו)
    for tool in sorted(list(set(d['t'] for d in raw_drills))):
        drills_for_tool = sorted([dr for dr in raw_drills if dr['t']==tool], key=lambda k: (k['group'], k['x'], k['y']))
        for d in drills_for_tool:
            if d['t'] != last_t:
                nc.append(f"N{ln} {d['t']} M06")
                nc.append(f"N{ln+5} G43 H{d['t'][1:]} S4000 M03")
                ln, last_t = ln + 10, d['t']
            nc.append(f"N{ln} G00 X{d['x']:.3f} Y{d['y']:.3f}")
            nc.append(f"N{ln+5} G01 Z{d['z']:.3f} F2000")
            nc.append(f"N{ln+10} G00 Z{thickness+10:.3f}")
            ln += 15
    # כרסומים
    for m in sorted(raw_millings, key=lambda x: x['t']):
        if m['t'] != last_t:
            nc.append(f"N{ln} {m['t']} M06")
            nc.append(f"N{ln+5} G43 H{m['t'][1:]} S17000 M03")
            ln, last_t = ln + 10, m['t']
        pts = geometries.get(m['geo_id'])
        if pts:
            # החלת z_offset גם על פסיעות אוטומטיות
            z_levels = [m['z']] if num_passes != 2 else [2.0 - z_offset, -0.2 - z_offset]
            for zv in z_levels:
                nc.append(f"N{ln} G00 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}")
                nc.append(f"N{ln+5} G01 Z{zv:.3f} F3000")
                ln += 10
                for p in pts[1:]:
                    nc.append(f"N{ln} G01 X{p[0]:.3f} Y{p[1]:.3f}")
                    ln += 5
                nc.append(f"N{ln} G00 Z{thickness+10:.3f}")
                ln += 5
    nc.append(f"N{ln} M30")
    return "\n".join(nc)

# --- Streamlit UI ---
st.title("🪚 Darwish CNC Pro - גרסה 25.0")
st.sidebar.header("🛠️ הגדרות")
if 'tool_df' not in st.session_state: st.session_state.tool_df = pd.DataFrame(DEFAULT_TOOLS)
edited_df = st.sidebar.data_editor(st.session_state.tool_df, num_rows="dynamic")

st.sidebar.markdown("---")
st.sidebar.header("📏 כיול עומק (אבי)")
z_offset_val = st.sidebar.number_input("תוספת עומק (מילימטר)", value=2.0, help="כמה להנמיך את הסכין מעבר למה שמוגדר ב-MPR")
margin_val = st.sidebar.number_input("מרווח ביטחון מהפינה (מילימטר)", value=7.0)

col1, col2 = st.columns([1, 1])
with col1:
    swap = st.checkbox("החלף צירים (X ↔ Y)", value=True)
    nest = st.checkbox("צמד לפינה (Zero Nesting)", value=True)
    off = st.selectbox("נקודת אפס", ["G54", "G55", "G56"])
    mode = st.radio("שיטה:", ('לפי MPR', '2 פסיעות'))
    uploaded = st.file_uploader("בחר קבצי MPR", accept_multiple_files=True)

with col2:
    if uploaded:
        pv = 2 if '2 פסיעות' in mode else 0
        for f in uploaded:
            res = convert_logic(f.getvalue().decode('utf-8', errors='ignore'), edited_df, pv, swap, off, nest, margin_val, z_offset_val)
            st.download_button(f"📂 הורד {f.name.replace('.mpr', '.nc')}", res, f.name.replace(".mpr", ".nc"))
            st.code(res, language='gcode')
