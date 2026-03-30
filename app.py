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
    
    # חילוץ גיאומטריה
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
    
    # חילוץ קידוחים משופר - ללא איבוד נתונים
    drill_blocks = re.findall(r'<102(.*?)\!', mpr_text, re.DOTALL)
    for idx, block in enumerate(drill_blocks):
        xa = float(re.search(r'XA="([\d.-]+)"', block).group(1))
        ya = float(re.search(r'YA="([\d.-]+)"', block).group(1))
        ti = float(re.search(r'TI="([\d.-]+)"', block).group(1))
        du = float(re.search(r'DU="([\d.-]+)"', block).group(1))
        an = int(re.search(r'AN="(\d+)"', block).group(1)) if re.search(r'AN="(\d+)"', block) else 1
        ab = float(re.search(r'AB="([\d.-]+)"', block).group(1)) if re.search(r'AB="([\d.-]+)"', block) else 0.0
        wi = float(re.search(r'WI="([\d.-]+)"', block).group(1)) if re.search(r'WI="([\d.-]+)"', block) else 0.0
        tno_m = re.search(r'TNO="(\d+)"', block)
        tno = tno_m.group(1) if tno_m else ""
        
        final_t = id_map.get(tno, dia_map.get(du, "T44"))
        
        for i in range(an):
            nx = xa + i * ab * math.cos(math.radians(wi))
            ny = ya + i * ab * math.sin(math.radians(wi))
            raw_drills.append({'x': nx, 'y': ny, 'z': thickness - ti, 't': final_t, 'group': idx})

    # חילוץ כרסומים
    mill_blocks = re.findall(r'<105(.*?)\!', mpr_text, re.DOTALL)
    for block in mill_blocks:
        geo_id = re.search(r'EA="(\d+):', block).group(1)
        za = float(re.search(r'ZA="([\d.-]+)"', block).group(1))
        tno_m = re.search(r'TNO="(\d+)"', block)
        tno = tno_m.group(1) if tno_m else "142"
        raw_millings.append({'geo_id': geo_id, 'z': za, 't': id_map.get(tno, "T2")})

    # איפוס ומיקום (Zero Nesting)
    all_pts_x = [d['x'] for d in raw_drills] + [p[0] for g in geometries.values() for p in g]
    all_pts_y = [d['y'] for d in raw_drills] + [p[1] for g in geometries.values() for p in g]
    min_x, min_y = min(all_pts_x), min(all_pts_y)

    for d in raw_drills:
        if zero_nesting: d['x'] -= min_x; d['y'] -= min_y
        d['x'] += margin; d['y'] += margin
        if swap_axes: d['x'], d['y'] = d['y'], d['x']

    for g in geometries.values():
        for p in g:
            if zero_nesting: p[0] -= min_x; p[1] -= min_y
            p[0] += margin; p[1] += margin
            if swap_axes: p[0], p[1] = p[1], p[0]

    nc_out, l_num, last_t = [f"G90 {offset}"], 10, ""
    
    # כתיבת קוד NC
    for tool_group in sorted(list(set(d['t'] for d in raw_drills))):
        for d in sorted([dr for dr in raw_drills if dr['t'] == tool_group], key=lambda x: (x['group'], x['x'])):
            if d['t'] != last_t:
                nc_out.extend([f"N{l_num} {d['t']} M06", f"N{l_num+5} G43 H{d['t'][1:]} S4000 M03"])
                l_num, last_t = l_num + 10, d['t']
            nc_out.extend([f"N{l_num} G00 X{d['x']:.3f} Y{d['y']:.3f}", f"N{l_num+5} G01 Z{d['z']:.3f} F2000.0", f"N{l_num+10} G00 Z{thickness + 10:.3f}"])
            l_num += 15

    for m in sorted(raw_millings, key=lambda x: x['t']):
        if m['t'] != last_t:
            nc_out.extend([f"N{l_num} {m['t']} M06", f"N{l_num+5} G43 H{m['t'][1:]} S17000 M03"])
            l_num, last_t = l_num + 10, m['t']
        pts = geometries.get(m['geo_id'])
        if pts:
            z_list = [m['z']] if num_passes != 2 else [2.0, -0.2]
            for zv in z_list:
                nc_out.append(f"N{l_num} G00 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}")
                nc_out.append(f"N{l_num+5} G01 Z{zv:.3f} F3000.0")
                l_num += 10
                for px, py in pts[1:]:
                    nc_out.append(f"N{l_num} G01 X{px:.3f} Y{py:.3f}"); l_num += 5
                nc_out.append(f"N{l_num} G00 Z{thickness + 10:.3f}"); l_num += 10

    nc_out.append(f"N{l_num} M30")
    return "\n".join(nc_out)

# ... (Streamlit UI code remains same)
