import streamlit as st
import re, os, zipfile
import pandas as pd
import math
from collections import defaultdict
from io import BytesIO

# חובה: פקודה ראשונה
st.set_page_config(page_title="Darwish CNC Pro 31.0", layout="wide")

DEFAULT_TOOLS = [
    {"ID_MPR": "142", "קוטר": 6.0, "תיאור": "כרסום 6", "T_CNC": "T2", "S": 18000, "F": 6000},
    {"ID_MPR": "158", "קוטר": 8.0, "תיאור": "מקדח 8", "T_CNC": "T47", "S": 4000, "F": 2000},
    {"ID_MPR": "100", "קוטר": 10.0, "תיאור": "מקדח 10", "T_CNC": "T46", "S": 4000, "F": 2000},
    {"ID_MPR": "149", "קוטר": 15.0, "תיאור": "מקדח 15", "T_CNC": "T49", "S": 4000, "F": 2000},
    {"ID_MPR": "135", "קוטר": 35.0, "תיאור": "מקדח 35", "T_CNC": "T6", "S": 3000, "F": 1500},
    {"ID_MPR": "121", "קוטר": 5.0, "תיאור": "מקדח 5", "T_CNC": "T44", "S": 4000, "F": 2000}
]

def convert_logic(mpr_text, tool_df, num_passes, swap_axes, offset, zero_nesting, margin, z_offset):
    # יצירת מפות כלים
    tno_map = {str(row['ID_MPR']): row for _, row in tool_df.iterrows() if str(row['ID_MPR']) != ""}
    dia_map = {float(row['קוטר']): row for _, row in tool_df.iterrows() if row['קוטר'] > 0}
    
    t_m = re.search(r't="([\d.]+)"', mpr_text)
    thickness = float(t_m.group(1)) if t_m else 19.0
    
    geos = {}
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        bid, content = parts[i], parts[i+1]
        pts = []
        for elem in re.split(r'\$E\d+', content):
            x, y = re.search(r'X=([\d.-]+)', elem), re.search(r'Y=([\d.-]+)', elem)
            if x and y: pts.append([float(x.group(1)), float(y.group(1))])
        if pts: geos[bid] = pts

    raw_drills, raw_millings = [], []
    
    # חילוץ קידוחים - מנוע סריקה משופר
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        xa = float(re.search(r'XA="([\d.-]+)"', b).group(1))
        ya = float(re.search(r'YA="([\d.-]+)"', b).group(1))
        ti = float(re.search(r'TI="([\d.-]+)"', b).group(1))
        du = float(re.search(r'DU="([\d.-]+)"', b).group(1))
        an = int(re.search(r'AN="(\d+)"', b).group(1)) if 'AN="' in b else 1
        ab = float(re.search(r'AB="([\d.-]+)"', b).group(1)) if 'AB="' in b else 0
        wi = float(re.search(r'WI="([\d.-]+)"', b).group(1)) if 'WI="' in b else 0
        tno_m = re.search(r'TNO="(\d+)"', b)
        tno = tno_m.group(1) if tno_m else ""
        
        # חיפוש כלי לפי TNO ואז לפי קוטר
        conf = tno_map.get(tno, dia_map.get(du, {"T_CNC": "T44", "S": 4000, "F": 2000}))
        
        for i in range(an):
            nx = xa + i * ab * math.cos(math.radians(wi))
            ny = ya + i * ab * math.sin(math.radians(wi))
            raw_drills.append({'x': nx, 'y': ny, 'z': (thickness-ti)-z_offset, 
                               't': conf['T_CNC'], 's': conf.get('S', 4000), 
                               'f': conf.get('F', 2000), 'group': m.start()})

    # חילוץ כרסומים
    for m in re.finditer(r'<105(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        geo_m = re.search(r'EA="(\d+):', b)
        if geo_m:
            eid = geo_m.group(1)
            za = float(re.search(r'ZA="([\d.-]+)"', b).group(1))
            tno_m = re.search(r'TNO="(\d+)"', b)
            tno = tno_m.group(1) if tno_m else "142"
            conf = tno_map.get(tno, dia_map.get(6.0, {"T_CNC": "T2", "S": 18000, "F": 6000}))
            raw_millings.append({'geo_id': eid, 'z': za - z_offset, 
                                't': conf['T_CNC'], 's': conf.get('S', 18000), 
                                'f': conf.get('F', 6000)})

    # Nesting Logic
    active_x = [d['x'] for d in raw_drills] + [p[0] for bid, pts in geos.items() if bid != "1" for p in pts]
    active_y = [d['y'] for d in raw_drills] + [p[1] for bid, pts in geos.items() if bid != "1" for p in pts]
    
    if active_x and active_y:
        mx, my = min(active_x), min(active_y)
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
    
    # כתיבת קידוחים
    for t_name in sorted(list(set(d['t'] for d in raw_drills))):
        subset = sorted([dr for dr in raw_drills if dr['t']==t_name], key=lambda k: (k['group'], k['x']))
        for d in subset:
            if d['t'] != last_t:
                nc.extend([f"N{ln} {d['t']} M06", f"N{ln+5} G43 H{d['t'][1:]} S{int(d['s'])} M03"])
                ln, last_t = ln + 10, d['t']
            nc.extend([f"N{ln} G00 X{d['x']:.3f} Y{d['y']:.3f}", f"N{ln+5} G01 Z{d['z']:.3f} F{int(d['f'])}", f"N{ln+10} G00 Z{thickness+10:.3f}"])
            ln += 15

    # כתיבת כרסומים
    for m in raw_millings:
        if m['t'] != last_t:
            nc.extend([f"N{ln} {m['t']} M06", f"N{ln+5} G43 H{m['t'][1:]} S{int(m['s'])} M03"])
            ln, last_t = ln + 10, m['t']
        pts = geos.get(m['geo_id'])
        if pts:
            z_lvls = [m['z']] if num_passes != 2 else [3.0 - z_offset, -0.25 - z_offset]
            for zv in z_lvls:
                nc.append(f"N{ln} G00 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}")
                nc.append(f"N{ln+5} G01 Z{zv:.3f} F{int(m['f'])}")
                ln += 10
                for p in pts[1:]: nc.append(f"N{ln} G01 X{p[0]:.3f} Y{p[1]:.3f}"); ln += 5
                nc.append(f"N{ln} G00 Z{thickness+10:.3f}"); ln += 5
    nc.append(f"N{ln} M30")
    return "\n".join(nc)

# --- Streamlit UI ---
st.title("🪚 Darwish CNC Pro - גרסה 31.0")
st.sidebar.header("🛠️ טבלת כלים")
if 'tool_df' not in st.session_state: st.session_state.tool_df = pd.DataFrame(DEFAULT_TOOLS)
edited_df = st.sidebar.data_editor(st.session_state.tool_df, num_rows="dynamic")
z_off = st.sidebar.number_input("תוספת עומק (מ''מ)", value=2.0)
mar = st.sidebar.number_input("מרווח ביטחון (מ''מ)", value=7.0)
swap = st.sidebar.checkbox("החלף צירים (X ↔ Y)", value=True)
nest = st.sidebar.checkbox("צמד לפינה", value=True)
off = st.sidebar.selectbox("נקודת אפס", ["G54", "G55"])
mode = st.sidebar.radio("שיטה:", ('לפי MPR', '2 פסיעות'))
uploaded = st.file_uploader("בחר קבצי MPR", accept_multiple_files=True)

if uploaded:
    pv = 2 if '2 פסיעות' in mode else 0
    for f in uploaded:
        res = convert_logic(f.getvalue().decode('utf-8', errors='ignore'), edited_df, pv, swap, off, nest, mar, z_off)
        st.download_button(f"📂 הורד {f.name.replace('.mpr', '.nc')}", res, f.name.replace(".mpr", ".nc"))
        st.code(res, language='gcode')
