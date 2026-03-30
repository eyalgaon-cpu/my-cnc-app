import streamlit as st
import re, os, zipfile
import pandas as pd
import math
from collections import defaultdict
from io import BytesIO

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
    blocks = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(blocks), 2):
        block_id, content = blocks[i], blocks[i+1]
        pts = []
        for elem in re.split(r'\$E\d+', content):
            x_m, y_m = re.search(r'X=([\d.-]+)', elem), re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m: pts.append([float(x_m.group(1)), float(y_m.group(1))])
        if pts: geometries[block_id] = pts

    raw_drills, raw_millings = [], []
    # חילוץ קדחים עם טיפול מלא במערכים (AN/AB)
    drills = re.findall(r'<102.*?XA="([\d.]+)".*?YA="([\d.]+)".*?TI="([\d.]+)".*?DU="([\d.]+)".*?AN="(\d+)".*?AB="([\d.]+)".*?WI="([\d.]+)".*?(?:TNO="(\d+)")?.*?', mpr_text, re.DOTALL)
    for idx, (xa, ya, ti, du, an, ab, wi, tno) in enumerate(drills):
        xa, ya, ti, du, an, ab, wi = map(float, [xa, ya, ti, du, an, ab, wi])
        final_t = id_map.get(tno if tno else "", dia_map.get(du, "T44"))
        # שמירת חורי המערך תחת מזהה קבוצה אחד כדי למנוע קפיצות
        for i in range(int(an)):
            nx = xa + i * ab * math.cos(math.radians(wi))
            ny = ya + i * ab * math.sin(math.radians(wi))
            raw_drills.append({'x': nx, 'y': ny, 'z': thickness - ti, 't': final_t, 'group': idx})

    millings = re.findall(r'<105.*?EA="(\d+):.*?ZA="([\d.-]+)".*?TNO="(\d+)".*?', mpr_text, re.DOTALL)
    for geo_id, za, tno in millings:
        raw_millings.append({'geo_id': geo_id, 'z': float(za), 't': id_map.get(tno, "T2")})

    # איפוס קואורדינטות (Zero Nesting)
    if zero_nesting:
        all_x = [d['x'] for d in raw_drills] + [p[0] for g in geometries.values() for p in g]
        all_y = [d['y'] for d in raw_drills] + [p[1] for g in geometries.values() for p in g]
        if all_x and all_y:
            min_x, min_y = min(all_x), min(all_y)
            for d in raw_drills: d['x'] -= min_x; d['y'] -= min_y
            for g in geometries.values():
                for p in g: p[0] -= min_x; p[1] -= min_y

    # הוספת מרווח ביטחון (Margin) והחלפת צירים
    for d in raw_drills:
        d['x'] += margin; d['y'] += margin
        if swap_axes: d['x'], d['y'] = d['y'], d['x']
    for g in geometries.values():
        for p in g:
            p[0] += margin; p[1] += margin
            if swap_axes: p[0], p[1] = p[1], p[0]

    nc_out, l_num, last_t = [f"G90 {offset}"], 10, ""
    # מיון קידוחים: קודם לפי כלי, אחר כך לפי קבוצה (קבינאו נשאר יחד), אחר כך מיקום
    drills_sorted = sorted(raw_drills, key=lambda d: (d['t'], d['group'], d['x'], d['y']))
    
    for d in drills_sorted:
        if d['t'] != last_t:
            nc_out.extend([f"N{l_num} {d['t']} M06", f"N{l_num+5} G43 H{d['t'][1:]} S4000 M03"])
            l_num, last_t = l_num + 10, d['t']
        nc_out.extend([f"N{l_num} G00 X{d['x']:.3f} Y{d['y']:.3f}", f"N{l_num+5} G01 Z{d['z']:.3f} F2000.0", f"N{l_num+10} G00 Z{thickness + 10:.3f}"])
        l_num += 15

    millings_sorted = sorted(raw_millings, key=lambda m: m['t'])
    for m in millings_sorted:
        if m['t'] != last_t:
            nc_out.extend([f"N{l_num} {m['t']} M06", f"N{l_num+5} G43 H{m['t'][1:]} S17000 M03"])
            l_num, last_t = l_num + 10, m['t']
        pts = geometries.get(m['geo_id'])
        if pts:
            z_levels = [m['z']] if num_passes != 2 else [2.0, -0.2]
            for zv in z_levels:
                nc_out.append(f"N{l_num} G00 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}")
                nc_out.append(f"N{l_num+5} G01 Z{zv:.3f} F3000.0")
                l_num += 10
                for px, py in pts[1:]: nc_out.append(f"N{l_num} G01 X{px:.3f} Y{py:.3f}"); l_num += 5
                nc_out.append(f"N{l_num} G00 Z{thickness + 10:.3f}"); l_num += 10
    nc_out.append(f"N{l_num} M30")
    return "\n".join(nc_out)

st.set_page_config(page_title="Darwish CNC Pro 18.0", layout="wide")
st.sidebar.header("🛠️ הגדרות")
if 'tool_df' not in st.session_state: st.session_state.tool_df = pd.DataFrame(DEFAULT_TOOLS)
edited_df = st.sidebar.data_editor(st.session_state.tool_df, num_rows="dynamic")
margin_val = st.sidebar.number_input("מרווח ביטחון (מ''מ)", value=7.0)

st.title("🪚 Darwish CNC Pro - גרסה 18.0")
col1, col2 = st.columns([1, 1])
with col1:
    swap = st.checkbox("החלף צירים (X ↔ Y)", value=True)
    nest = st.checkbox("צמד לפינה", value=True)
    off = st.selectbox("נקודת אפס", ["G54", "G55", "G56"])
    mode = st.radio("שיטה:", ('לפי MPR', '2 פסיעות'))
    uploaded = st.file_uploader("בחר קבצי MPR", accept_multiple_files=True)

with col2:
    if uploaded:
        pv = 2 if '2 פסיעות' in mode else 0
        for f in uploaded:
            res = convert_logic(f.getvalue().decode('utf-8', errors='ignore'), edited_df, pv, swap, off, nest, margin_val)
            st.download_button(f"📂 הורד {f.name.replace('.mpr', '.nc')}", res, f.name.replace(".mpr", ".nc"))
            st.code(res, language='gcode')
