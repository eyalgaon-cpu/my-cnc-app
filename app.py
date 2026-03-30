import streamlit as st
import re, os, zipfile
import pandas as pd
import math
from collections import defaultdict
from io import BytesIO

# חובה: פקודה ראשונה
st.set_page_config(page_title="Darwish CNC Pro 29.0", layout="wide")

DEFAULT_TOOLS = [
    {"ID_MPR": "142", "תיאור": "כרסום 6", "T_CNC": "T2", "S_סלד": 18000, "F_התקדמות": 6000},
    {"ID_MPR": "158", "תיאור": "כרסום 8", "T_CNC": "T3", "S_סלד": 16000, "F_התקדמות": 8000},
    {"ID_MPR": "140", "תיאור": "כרסום 3", "T_CNC": "T11", "S_סלד": 18000, "F_התקדמות": 3000},
    {"ID_MPR": "121", "תיאור": "מקדח 5", "T_CNC": "T44", "S_סלד": 4000, "F_התקדמות": 2000},
    {"ID_MPR": "149", "תיאור": "מקדח 15", "T_CNC": "T49", "S_סלד": 4000, "F_התקדמות": 2000},
    {"ID_MPR": "135", "תיאור": "מקדח 35", "T_CNC": "T6", "S_סלד": 3000, "F_התקדמות": 1500}
]

def convert_logic(mpr_text, tool_df, num_passes, swap_axes, offset, zero_nesting, margin, z_offset):
    # יצירת מילון קונפיגורציה מהטבלה
    tool_config = tool_df.set_index('ID_MPR').to_dict('index')
    
    t_m = re.search(r't="([\d.]+)"', mpr_text)
    thickness = float(t_m.group(1)) if t_m else 16.5
    
    geos = {}
    # פיצול גיאומטריה
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        bid, content = parts[i], parts[i+1]
        pts = []
        for elem in re.split(r'\$E\d+', content):
            x, y = re.search(r'X=([\d.-]+)', elem), re.search(r'Y=([\d.-]+)', elem)
            if x and y: pts.append([float(x.group(1)), float(y.group(1))])
        if pts: geos[bid] = pts

    raw_drills, raw_millings = [], []
    # סריקת פקודות לפי ה-<
    sections = mpr_text.split('<')
    for idx, sec in enumerate(sections):
        if sec.startswith('102'): # קידוחים
            try:
                xa = float(re.search(r'XA="([\d.-]+)"', sec).group(1))
                ya = float(re.search(r'YA="([\d.-]+)"', sec).group(1))
                ti = float(re.search(r'TI="([\d.-]+)"', sec).group(1))
                du = float(re.search(r'DU="([\d.-]+)"', sec).group(1))
                an = int(re.search(r'AN="(\d+)"', sec).group(1)) if 'AN="' in sec else 1
                ab = float(re.search(r'AB="([\d.-]+)"', sec).group(1)) if 'AB="' in sec else 0
                wi = float(re.search(r'WI="([\d.-]+)"', sec).group(1)) if 'WI="' in sec else 0
                tno = re.search(r'TNO="(\d+)"', sec).group(1) if 'TNO="' in sec else ""
                
                conf = tool_config.get(tno, {"T_CNC": "T44", "S_סלד": 4000, "F_התקדמות": 2000})
                for i in range(an):
                    nx = xa + i * ab * math.cos(math.radians(wi))
                    ny = ya + i * ab * math.sin(math.radians(wi))
                    raw_drills.append({'x': nx, 'y': ny, 'z': (thickness-ti)-z_offset, 
                                     't': conf['T_CNC'], 's': conf.get('S_סלד', 4000), 
                                     'f': conf.get('F_התקדמות', 2000), 'group': idx})
            except: continue

        elif sec.startswith('105'): # כרסומים
            try:
                geo_match = re.search(r'EA="(\d+):', sec)
                if geo_match:
                    gid = geo_match.group(1)
                    za = float(re.search(r'ZA="([\d.-]+)"', sec).group(1))
                    tno = re.search(r'TNO="(\d+)"', sec).group(1) if 'TNO="' in sec else "142"
                    conf = tool_config.get(tno, {"T_CNC": "T2", "S_סלד": 18000, "F_התקדמות": 6000})
                    raw_millings.append({'geo_id': gid, 'z': za - z_offset, 
                                        't': conf['T_CNC'], 's': conf.get('S_סלד', 18000), 
                                        'f': conf.get('F_התקדמות', 6000)})
            except: continue

    # Nesting - Fixed NameError (using 'geos' everywhere)
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
    
    # כתיבת קוד NC לקידוחים
    for t_name in sorted(list(set(d['t'] for d in raw_drills))):
        subset = sorted([dr for dr in raw_drills if dr['t']==t_name], key=lambda k: (k['group'], k['x']))
        for d in subset:
            if d['t'] != last_t:
                nc.extend([f"N{ln} {d['t']} M06", f"N{ln+5} G43 H{d['t'][1:]} S{int(d['s'])} M03"])
                ln, last_t = ln + 10, d['t']
            nc.extend([f"N{ln} G00 X{d['x']:.3f} Y{d['y']:.3f}", f"N{ln+5} G01 Z{d['z']:.3f} F{int(d['f'])}", f"N{ln+10} G00 Z{thickness+10:.3f}"])
            ln += 15

    # כתיבת קוד NC לכרסומים
    for m in sorted(raw_millings, key=lambda x: x['t']):
        if m['t'] != last_t:
            nc.extend([f"N{ln} {m['t']} M06", f"N{ln+5} G43 H{m['t'][1:]} S{int(m['s'])} M03"])
            ln, last_t = ln + 10, m['t']
        pts = geos.get(m['geo_id'])
        if pts:
            z_lvls = [m['z']] if num_passes != 2 else [2.0 - z_offset, -0.2 - z_offset]
            for zv in z_lvls:
                nc.append(f"N{ln} G00 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}")
                nc.append(f"N{ln+5} G01 Z{zv:.3f} F{int(m['f'])}")
                ln += 10
                for p in pts[1:]:
                    nc.append(f"N{ln} G01 X{p[0]:.3f} Y{p[1]:.3f}")
                    ln += 5
                nc.append(f"N{ln} G00 Z{thickness+10:.3f}")
                ln += 5
    nc.append(f"N{ln} M30")
    return "\n".join(nc)

# --- UI ---
st.title("🪚 Darwish CNC Pro - גרסה 29.0")
st.sidebar.header("🛠️ טבלת כלים ומהירויות")
if 'tool_df' not in st.session_state: st.session_state.tool_df = pd.DataFrame(DEFAULT_TOOLS)
edited_df = st.sidebar.data_editor(st.session_state.tool_df, num_rows="dynamic")

st.sidebar.markdown("---")
st.sidebar.header("📏 כיול (המכונה של אבי)")
z_off_ui = st.sidebar.number_input("תוספת עומק (מילימטר)", value=2.0)
mar_ui = st.sidebar.number_input("מרווח ביטחון (מילימטר)", value=7.0)

col1, col2 = st.columns([1, 1])
with col1:
    st.subheader("⚙️ הגדרות")
    swap = st.checkbox("החלף צירים (X ↔ Y)", value=True)
    nest = st.checkbox("צמד לפינה", value=True)
    off = st.selectbox("נקודת אפס", ["G54", "G55"])
    mode = st.radio("שיטה:", ('לפי MPR', '2 פסיעות'))
    uploaded = st.file_uploader("בחר קבצי MPR", accept_multiple_files=True)

with col2:
    if uploaded:
        pv = 2 if '2 פסיעות' in mode else 0
        for f in uploaded:
            content = f.getvalue().decode('utf-8', errors='ignore')
            res = convert_logic(content, edited_df, pv, swap, off, nest, mar_ui, z_off_ui)
            st.download_button(f"📂 הורד {f.name.replace('.mpr', '.nc')}", res, f.name.replace(".mpr", ".nc"))
            st.code(res, language='gcode')
