import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import re
import math
import numpy as np

# --- חוק יסוד: פרוטוקול דרוויש 2026 ---
# סטטוס: גרסה 6.5 - הרמטית (EA Mapping & Intersection Restoration)
# שפה: עברית טכנית (שימוש במילים מילימטר וסנטימטר בלבד)

st.set_page_config(page_title="Darwish CNC Pro - V6.5", layout="wide")

# הגדרות מכונה (אבי)
MACHINE_WIDTH_X = 1300.0
MACHINE_LENGTH_Y = 3050.0

# --- 1. ניהול מסד כלים (Industrial Tool Database) ---
if 'tool_db' not in st.session_state:
    st.session_state.tool_db = pd.DataFrame([
        {"T_CNC": "T2", "MPR_Name": "142", "Desc": "כרסום יהלום 12 מילימטר", "Diameter": 12.0, "RPM": 18000, "Feed": 4000},
        {"T_CNC": "T3", "MPR_Name": "158", "Desc": "כרסום 8 מילימטר", "Diameter": 8.0, "RPM": 18000, "Feed": 3000},
        {"T_CNC": "T4", "MPR_Name": "128", "Desc": "כרסום 12 מילימטר", "Diameter": 12.0, "RPM": 18000, "Feed": 3500},
        {"T_CNC": "T44", "MPR_Name": "5.0", "Desc": "מקדח 5 מילימטר", "Diameter": 5.0, "RPM": 4500, "Feed": 1200},
        {"T_CNC": "T47", "MPR_Name": "8.0", "Desc": "מקדח 8 מילימטר", "Diameter": 8.0, "RPM": 4500, "Feed": 1200},
        {"T_CNC": "T49", "MPR_Name": "15.0", "Desc": "מקדח 15 מילימטר", "Diameter": 15.0, "RPM": 3000, "Feed": 800},
        {"T_CNC": "T6", "MPR_Name": "35", "Desc": "מקדח צירים 35 מילימטר", "Diameter": 35.0, "RPM": 3000, "Feed": 1000}
    ])

with st.sidebar:
    st.header("🛠️ הגדרות ייצור")
    with st.expander("עריכת מסד כלים (T1-T49)", expanded=False):
        st.session_state.tool_db = st.data_editor(st.session_state.tool_db, num_rows="dynamic", key="tools_v65")
    st.markdown("---")
    off_x = st.number_input("הזזת פלטה ציר X (מילימטר)", value=0.0, step=1.0)
    off_y = st.number_input("הזזת פלטה ציר Y (מילימטר)", value=0.0, step=1.0)
    gz = st.number_input("תיקון Z גלובלי (מילימטר)", value=0.0, step=0.1)

# --- 2. מנוע מתמטי (Intersection & Offset מגרסה 48.7) ---
def _safe_float(val):
    try: return float(re.sub(r'[^0-9.\-]', '', str(val)))
    except: return 0.0

def intersect(l1, l2):
    """חישוב חיתוך וקטורי מפוצה למניעת קריסה בפינות"""
    x1, y1 = l1[0]; x2, y2 = l1[1]
    x3, y3 = l2[0]; x4, y4 = l2[1]
    den = (y4-y3)*(x2-x1) - (x4-x3)*(y2-y1)
    if abs(den) < 1e-6: return l1[1]
    ua = ((x4-x3)*(y1-y3) - (y4-y3)*(x1-x3)) / den
    return np.array([x1 + ua*(x2-x1), y1 + ua*(y2-y1)])

def apply_intersection_offset(points, rk, radius):
    """יישום לוגיקת הצידוד מגרסה 48.7"""
    if rk == 0 or radius <= 0 or len(points) < 2: return points
    side = 1 if rk == 1 else -1
    
    shifted_lines = []
    pts_arr = np.array(points)
    for i in range(len(pts_arr)-1):
        p1, p2 = pts_arr[i], pts_arr[i+1]
        v = p2 - p1
        mag = np.linalg.norm(v)
        if mag == 0: continue
        normal = side * np.array([-v[1], v[0]]) / mag
        shifted_lines.append((p1 + normal * radius, p2 + normal * radius))
        
    if not shifted_lines: return points
    new_path = [tuple(shifted_lines[0][0])]
    for i in range(len(shifted_lines)-1):
        new_path.append(tuple(intersect(shifted_lines[i], shifted_lines[i+1])))
    new_path.append(tuple(shifted_lines[-1][1]))
    return new_path

# --- 3. Master Parser (EA Restoration) ---
class MasterParser:
    def __init__(self, raw_bytes):
        # פתרון שגיאת Unicode מ-CMD
        self.raw = raw_bytes.decode('utf-8', errors='ignore')
        self.header = {'L': 0.0, 'W': 0.0, 'T': 0.0}
        self.geos = {}
        self.ops = []
        self._parse()

    def _parse(self):
        # 1. Header
        for k, f in [('L','l'), ('W','w'), ('T','t')]:
            m = re.search(rf'{f}\s*=\s*"?([0-9.]+)"?', self.raw, re.I)
            if m: self.header[k] = _safe_float(m.group(1))

        # 2. מיפוי גיאומטריה גלובלי (בלוקי ]) - מפתח מגרסה 48.7
        geo_parts = re.split(r'(?=\])', self.raw)
        for part in geo_parts:
            if not part.startswith(']'): continue
            p = dict(re.findall(r'(\w+)="?([^"\s]+)"?', part))
            idx = p.get('ID', '0')
            if idx not in self.geos: self.geos[idx] = []
            self.geos[idx].append((_safe_float(p.get('X', p.get('XA', 0))), _safe_float(p.get('Y', p.get('YA', 0)))))

        # 3. קישור פקודות (<) וקישור EA
        cmd_parts = re.split(r'(?=<[0-9]{3})', self.raw)
        for part in cmd_parts:
            p = dict(re.findall(r'(\w+)="?([^"\s]+)"?', part))
            if part.startswith("<102"): # Drill
                self.ops.append({'type': 'Drill', 'pts': [(_safe_float(p.get('XA', 0)), _safe_float(p.get('YA', 0)))], 'z_raw': _safe_float(p.get('TI', 0)), 'z_type': 'TI', 'id': p.get('DU', '5.0'), 'rk': 0})
            elif part.startswith("<105"): # Milling
                ea_id = p.get('EA', '0').split(':')[0]
                path = [(_safe_float(p.get('XA', 0)), _safe_float(p.get('YA', 0)))]
                if ea_id in self.geos: path.extend(self.geos[ea_id])
                self.ops.append({'type': 'Milling', 'pts': path, 'z_raw': _safe_float(p.get('ZA', 0)), 'z_type': 'ZA', 'id': p.get('TNO', '142'), 'rk': int(_safe_float(p.get('RK', 0)))})

# --- 4. ממשק הפקה והדמיה ---
st.title("🏭 Darwish CNC Pro - V6.5 (The Master Restoration)")
upl = st.file_uploader("טען קובץ MPR", type=['mpr'])

if upl:
    parser = MasterParser(upl.read())
    if parser.header['L'] > 0:
        final_list = []
        tools = st.session_state.tool_db.copy()
        
        for op in parser.ops:
            t_info = tools[tools['MPR_Name'] == op['id'].replace("BV","")]
            if t_info.empty: t_info = tools[tools['T_CNC'] == "T2"]
            t = t_info.iloc[0]
            
            # החלת מנוע הצידוד מגרסה 48.7
            comp_pts = apply_intersection_offset(op['pts'], op['rk'], t['Diameter']/2)
            
            for i, pt in enumerate(comp_pts):
                nx, ny = (parser.header['W'] - pt[1]), pt[0] # סיבוב 90 CCW
                bz = (parser.header['T'] - op['z_raw']) if op['z_type'] == 'TI' else op['z_raw']
                fz = round(bz + gz, 3)
                steps = [fz]
                if op['type'] == 'Milling' and t['T_CNC'] == "T2" and i == 0: steps = [round(fz+2.0, 3), fz]
                final_list.append({'x': nx+off_x, 'y': ny+off_y, 'z': steps, 'tool': t['T_CNC'], 'rpm': t['RPM'], 'feed': t['Feed'], 'is_start': (i==0), 'type': op['type'], 'diam': t['Diameter']})

        # הדמיה
        fig = go.Figure()
        fig.add_shape(type="rect", x0=off_x, y0=off_y, x1=off_x+parser.header['W'], y1=off_y+parser.header['L'], fillcolor="brown", opacity=0.1)
        for d in final_list:
            color = "blue" if d['type'] == 'Drill' else "red"
            fig.add_trace(go.Scatter(x=[d['x']], y=[d['y']], mode='markers+lines' if d['type']=='Milling' else 'markers', marker=dict(size=d['diam'], color=color), line=dict(color=color, width=2)))
        fig.update_layout(yaxis_scaleanchor="x", width=600, height=800, dragmode='pan')
        st.plotly_chart(fig, config={'scrollZoom': True})

        if st.button("🛠️ הפק NC"):
            nc = ["%", f"(DARWISH V6.5 - {parser.header['L']}x{parser.header['W']} mm)", "N10 G90 G54 G21 G17"]
            curr_t, n_c = None, 20
            for d in final_list:
                if d['tool'] != curr_t:
                    if curr_t: nc.append(f"N{n_c} M05"); n_c += 10
                    nc.append(f"N{n_c} {d['tool']} M06"); n_c += 10
                    nc.append(f"N{n_c} G43 H{d['tool'][1:]}"); n_c += 10
                    nc.append(f"N{n_c} S{int(d['rpm'])} M03"); n_c += 10
                    curr_t = d['tool']
                if d['is_start']:
                    nc.append(f"N{n_c} G00 X{d['x']:.3f} Y{d['y']:.3f}"); n_c += 10
                    for z_s in d['z']:
                        nc.append(f"N{n_c} G01 Z{z_s:.3f} F{int(d['feed'])}"); n_c += 10
                else:
                    nc.append(f"N{n_c} G01 X{d['x']:.3f} Y{d['y']:.3f} F{int(d['feed'])}"); n_c += 10
            nc.extend([f"N{n_c} G00 Z35.0", f"N{n_c+10} M05", f"N{n_c+20} M30", f"N{n_c+30} M200", "%"])
            st.download_button("הורד קובץ NC", "\n".join(nc), file_name="production.nc")
            st.code("\n".join(nc), language='gcode')
