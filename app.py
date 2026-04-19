import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import re
import math
import numpy as np

# --- חוק יסוד: פרוטוקול דרוויש 2026 ---
# סטטוס: גרסה 6.4 - המייצב הפורנזי (Unicode Fix & Intersection Logic)
# שפה: עברית טכנית (שימוש במילים מילימטר וסנטימטר בלבד)

st.set_page_config(page_title="Darwish CNC Pro - V6.4", layout="wide")

# הגדרות מכונה (אבי)
MACHINE_WIDTH_X = 1300.0
MACHINE_LENGTH_Y = 3050.0

# --- 1. ניהול מסד כלים (Industrial Tool Database) ---
if 'tool_df' not in st.session_state:
    st.session_state.tool_df = pd.DataFrame({
        "ID_MPR": ["142", "158", "128", "35", "130", "5.0", "8.0", "15.0", "40.0", "19.0", "6.0", "20.0", "7.0", "16.0", "42.0"],
        "NC_Tool": ["T2", "T3", "T4", "T6", "T13", "T44", "T47", "T49", "T1", "T8", "T10", "T28", "T7", "T16", "T42"],
        "Diameter": [12.0, 8.0, 12.0, 35.0, 0.2, 5.0, 8.0, 15.0, 40.0, 19.0, 6.0, 20.0, 10.0, 10.0, 10.0]
    })

with st.sidebar:
    st.header("🛠️ הגדרות ייצור")
    st.session_state.tool_df = st.data_editor(st.session_state.tool_df, key="tools_v64")
    off_x = st.number_input("הזזת פלטה ציר X (מילימטר)", value=0.0)
    off_y = st.number_input("הזזת פלטה ציר Y (מילימטר)", value=0.0)

# --- 2. מנוע מתמטי מבוסס 48.7 (Intersection Logic) ---
def _safe_float(val):
    try: return float(re.sub(r'[^0-9.\-]', '', str(val)))
    except: return 0.0

def get_intersect(p1, p2, p3, p4):
    """חישוב חיתוך בין שני קווים מוסטים למניעת קריסת פינות """
    x1, y1 = p1; x2, y2 = p2
    x3, y3 = p3; x4, y4 = p4
    den = (y4-y3)*(x2-x1) - (x4-x3)*(y2-y1)
    if abs(den) < 1e-6: return p2 # קווים מקבילים
    ua = ((x4-x3)*(y1-y3) - (y4-y3)*(x1-x3)) / den
    return (x1 + ua*(x2-x1), y1 + ua*(y2-y1))

def apply_radius_offset(points, rk, radius):
    if rk == 0 or len(points) < 2: return points
    side = -1.0 if rk == 1 else 1.0 # 1=Left, 2=Right [cite: 33]
    
    # יצירת קווים מקבילים (Offset Lines) [cite: 59-60]
    lines = []
    for i in range(len(points)-1):
        p1, p2 = np.array(points[i]), np.array(points[i+1])
        v = p2 - p1
        mag = np.linalg.norm(v)
        if mag == 0: continue
        n = np.array([-v[1], v[0]]) / mag
        offset = n * radius * side
        lines.append((p1 + offset, p2 + offset))
    
    if not lines: return points
    
    # חישוב חיתוכים (Intersections) [cite: 61, 64]
    new_pts = [tuple(lines[0][0])]
    for i in range(len(lines)-1):
        new_pts.append(get_intersect(lines[i][0], lines[i][1], lines[i+1][0], lines[i+1][1]))
    new_pts.append(tuple(lines[-1][1]))
    return new_pts

# --- 3. Forensic Parser (Unicode Fix & EA Link) ---
class ForensicParser:
    def __init__(self, raw_bytes):
        # תיקון שגיאת Unicode באמצעות התעלמות מתווים בינאריים 
        self.raw = raw_bytes.decode('utf-8', errors='ignore')
        self.header = {'L': 0.0, 'W': 0.0, 'T': 0.0}
        self.geos = {} # מפת גיאומטריה EA 
        self.ops = []
        self._parse()

    def _parse(self):
        # 1. Header
        for k, f in [('L','l'), ('W','w'), ('T','t')]:
            m = re.search(rf'{f}\s*=\s*"?([0-9.]+)"?', self.raw, re.I)
            if m: self.header[k] = _safe_float(m.group(1))

        # 2. מיפוי גיאומטריה גלובלי (בלוקי ]) [cite: 67]
        geo_parts = re.split(r'(?=\])', self.raw)
        for part in geo_parts:
            if not part.startswith(']'): continue
            p = dict(re.findall(r'(\w+)="?([^"\s]+)"?', part))
            idx = p.get('ID', '0')
            if idx not in self.geos: self.geos[idx] = []
            self.geos[idx].append((_safe_float(p.get('X', p.get('XA', 0))), _safe_float(p.get('Y', p.get('YA', 0)))))

        # 3. עיבוד פקודות וקישור EA 
        cmd_parts = re.split(r'(?=<[0-9]{3})', self.raw)
        for part in cmd_parts:
            p = dict(re.findall(r'(\w+)="?([^"\s]+)"?', part))
            if part.startswith("<102"): # Drill
                self.ops.append({'type': 'Drill', 'pts': [(_safe_float(p.get('XA', 0)), _safe_float(p.get('YA', 0)))], 'z': _safe_float(p.get('TI', 0)), 'z_type': 'TI', 'id': p.get('DU', '5.0'), 'rk': 0})
            elif part.startswith("<105"): # Milling
                ea_id = p.get('EA', '0').split(':')[0]
                path = [(_safe_float(p.get('XA', 0)), _safe_float(p.get('YA', 0)))]
                if ea_id in self.geos: path.extend(self.geos[ea_id])
                self.ops.append({'type': 'Milling', 'pts': path, 'z': _safe_float(p.get('ZA', 0)), 'z_type': 'ZA', 'id': p.get('TNO', '142'), 'rk': int(_safe_float(p.get('RK', 0)))})

# --- 4. תצוגה ועיבוד ---
st.title("🚀 Darwish CNC Pro - V6.4 (Forensic Stabilizer)")
upl = st.file_uploader("טען קובץ MPR", type=['mpr'])

if upl:
    parser = ForensicParser(upl.read())
    if parser.header['L'] > 0:
        final_list = []
        temp_df = st.session_state.tool_df.copy()
        temp_df['ID_NUM'] = temp_df['ID_MPR'].apply(_safe_float)
        
        for op in parser.ops:
            t_info = temp_df[temp_df['ID_NUM'] == _safe_float(op['id'])]
            t = t_info.iloc[0] if not t_info.empty else st.session_state.tool_df.iloc[0]
            # החלת הצידוד (Intersection Logic) [cite: 58, 64]
            pts = apply_radius_offset(op['pts'], op['rk'], t['Diameter']/2)
            for i, pt in enumerate(pts):
                nx, ny = (parser.header['W'] - pt[1]), pt[0] # סיבוב 90 CCW [cite: 68]
                bz = (parser.header['T'] - op['z']) if op['z_type'] == 'TI' else op['z'] [cite: 69]
                final_list.append({'x': nx+off_x, 'y': ny+off_y, 'z': round(bz,3), 'tool': op['id'], 'is_start': (i==0), 'type': op['type'], 'diam': t['Diameter']})

        # הדמיה (Visual Restoration) [cite: 83]
        fig = go.Figure()
        fig.add_shape(type="rect", x0=off_x, y0=off_y, x1=off_x+parser.header['W'], y1=off_y+parser.header['L'], fillcolor="brown", opacity=0.1)
        for d in final_list:
            color = "blue" if d['type'] == 'Drill' else "red"
            fig.add_trace(go.Scatter(x=[d['x']], y=[d['y']], mode='markers+lines' if d['type']=='Milling' else 'markers', marker=dict(size=d['diam'], color=color)))
        fig.update_layout(yaxis_scaleanchor="x", width=600, height=800)
        st.plotly_chart(fig)
