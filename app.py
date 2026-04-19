import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import re
import math
import numpy as np

# --- חוק יסוד: פרוטוקול דרוויש 2026 ---
# סטטוס: גרסה 5.9 - הרמטית (תיקון צידוד וקטורי מלא למידות Net Size)
# שפה: עברית טכנית (שימוש במילים מילימטר וסנטימטר בלבד)

st.set_page_config(page_title="Darwish CNC Pro - V5.9", layout="wide")

# הגדרות מכונה (אבי - ELKUM ELP1330DU)
MACHINE_WIDTH_X = 1300.0  # מילימטר
MACHINE_LENGTH_Y = 3050.0 # מילימטר

# --- 1. ניהול מסד כלים (Industrial Tool Database) ---
if 'tool_df' not in st.session_state:
    initial_tools = {
        "ID_MPR": ["142", "158", "128", "35", "130", "5.0", "8.0", "15.0", "40.0", "19.0", "6.0", "20.0", "7.0", "16.0", "42.0"],
        "NC_Tool": ["T2", "T3", "T4", "T6", "T13", "T44", "T47", "T49", "T1", "T8", "T10", "T28", "T7", "T16", "T42"],
        "Diameter": [12.0, 8.0, 12.0, 35.0, 0.2, 5.0, 8.0, 15.0, 40.0, 19.0, 6.0, 20.0, 10.0, 10.0, 10.0],
        "RPM": [18000, 18000, 16000, 3000, 18000, 4500, 4500, 3000, 12000, 16000, 18000, 3000, 18000, 18000, 18000],
        "Feed": [3000, 2500, 3500, 1000, 2000, 1500, 1500, 800, 4000, 3000, 2000, 1000, 2000, 2000, 2000],
        "Desc": ["כרסום יהלום (קונטור)", "כרסום 8 מילימטר", "כרסום 12 מילימטר", "מקדח צירים", "גירונג 90/45", "מקדח 5 מילימטר", "מקדח 8 מילימטר", "מקדח 15 מילימטר", "כרסום ניקוי", "כרסום 19 מילימטר", "כרסום/מקדח 6", "מקדח 20 מילימטר", "מקל סבא 1", "מקל סבא 2", "כלי פינה/מגרעת"]
    }
    st.session_state.tool_df = pd.DataFrame(initial_tools)

with st.sidebar:
    st.header("🛠️ הגדרות ייצור")
    with st.expander("עריכת מסד כלים (T1-T49)", expanded=False):
        st.session_state.tool_df = st.data_editor(st.session_state.tool_df, num_rows="dynamic", key="tool_editor_v59")
    st.markdown("---")
    off_x = st.number_input("הזזת פלטה ציר X (מילימטר)", value=0.0, step=1.0)
    off_y = st.number_input("הזזת פלטה ציר Y (מילימטר)", value=0.0, step=1.0)
    gz = st.number_input("תיקון Z גלובלי (מילימטר)", value=0.0, step=0.1)
    if st.button("🔄 רענון עמוק (Cache Clear)"):
        st.cache_data.clear()
        st.rerun()

# --- 2. מנועי ליבה (מתמטיקה וצידוד וקטורי) ---
def _safe_float(val):
    try:
        clean = re.sub(r'[^0-9.\-]', '', str(val))
        return float(clean) if clean else 0.0
    except: return 0.0

def rotate_90_ccw(x, y, board_w, board_l):
    return (board_w - y), x

def apply_vector_offset(points, rk, radius):
    """מנוע צידוד: מחשב אופסט וקטורי לכל מסלול הגיאומטריה"""
    if rk == 0 or len(points) < 2: return points
    
    offset_points = []
    side = -1.0 if rk == 1 else 1.0 # 1=Left, 2=Right
    
    for i in range(len(points)):
        p = points[i]
        # מציאת וקטור כיוון (ממוצע בין מקטע קודם למקטע הבא לריכוך פינות)
        v_sum = np.array([0.0, 0.0])
        count = 0
        
        if i > 0: # וקטור ממקודם
            v_prev = np.array([p[0]-points[i-1][0], p[1]-points[i-1][1]])
            mag = np.linalg.norm(v_prev)
            if mag > 0: v_sum += v_prev / mag; count += 1
            
        if i < len(points)-1: # וקטור להבא
            v_next = np.array([points[i+1][0]-p[0], points[i+1][1]-p[1]])
            mag = np.linalg.norm(v_next)
            if mag > 0: v_sum += v_next / mag; count += 1
            
        if count == 0:
            offset_points.append(p); continue
            
        v_dir = v_sum / count
        # נורמל לוקטור הכיוון
        normal = np.array([-v_dir[1], v_dir[0]])
        mag_n = np.linalg.norm(normal)
        if mag_n > 0: normal = normal / mag_n
        
        new_p = np.array(p) + normal * radius * side
        offset_points.append(tuple(new_p))
        
    return offset_points

# --- 3. Block-Parser מורחב ---
class BlockMPRParser:
    def __init__(self, content):
        self.raw_content = content
        self.header = {'L': 0.0, 'W': 0.0, 'T': 0.0}
        self.ops = [] # רשימת פעולות מורכבות
        self._parse()

    def _parse(self):
        for key, field in [('L','l'), ('W','w'), ('T','t')]:
            match = re.search(rf'{field}\s*=\s*"?([0-9.]+)"?', self.raw_content, re.IGNORECASE)
            if match: self.header[key] = _safe_float(match.group(1))

        # פיצול לבלוקים
        blocks = re.split(r'(?=<[0-9]{3}|\])', self.raw_content)
        current_milling_chain = []
        
        for block in blocks:
            params = dict(re.findall(r'(\w+)="?([^"\s]+)"?', block))
            
            if block.startswith("<102"): # קידוחים
                num = int(_safe_float(params.get('AN', 1)))
                dist = _safe_float(params.get('AB', 0))
                ang = math.radians(_safe_float(params.get('WI', 0)))
                for i in range(num):
                    rx = _safe_float(params.get('XA', 0)) + (i * dist * math.cos(ang))
                    ry = _safe_float(params.get('YA', 0)) + (i * dist * math.sin(ang))
                    self.ops.append({
                        'type': 'Drill', 'points': [(rx, ry)], 
                        'raw_z': _safe_float(params.get('TI', 0)), 'z_type': 'TI', 
                        'mpr_id': params.get('DU', '5.0'), 'rk': 0
                    })

            if block.startswith("<105"): # תחילת כרסום
                current_milling_chain = [( _safe_float(params.get('XA', 0)), _safe_float(params.get('YA', 0)) )]
                self.ops.append({
                    'type': 'Milling', 'points': current_milling_chain,
                    'raw_z': _safe_float(params.get('ZA', 0)), 'z_type': 'ZA',
                    'mpr_id': params.get('TNO', '142'), 'rk': int(_safe_float(params.get('RK', 0)))
                })

            if block.startswith("]2") or block.startswith("]3"): # המשכיות מסלול
                if self.ops and self.ops[-1]['type'] == 'Milling':
                    px = _safe_float(params.get('X', params.get('XA', 0)))
                    py = _safe_float(params.get('Y', params.get('YA', 0)))
                    self.ops[-1]['points'].append((px, py))

# --- 4. עיבוד ייצור ---
def process_production(parser, tool_df, ox, oy, global_z):
    processed = []
    temp_df = tool_df.copy()
    temp_df['ID_NUM'] = temp_df['ID_MPR'].apply(_safe_float)

    for op in parser.ops:
        mpr_id_num = _safe_float(op['mpr_id'])
        t_info = temp_df[temp_df['ID_NUM'] == mpr_id_num]
        t_row = t_info.iloc[0] if not t_info.empty else tool_df[tool_df['NC_Tool'] == "T2"].iloc[0]
        
        # החלת צידוד וקטורי (במערכת ה-MPR)
        compensated_points = apply_vector_offset(op['points'], op['rk'], t_row['Diameter']/2)
        
        for p_idx, p in enumerate(compensated_points):
            nx, ny = rotate_90_ccw(p[0], p[1], parser.header['W'], parser.header['L'])
            fz = (parser.header['T'] - op['raw_z']) if op['z_type'] == 'TI' else op['raw_z']
            final_z = round(fz + global_z, 3)
            
            # לוגיקת פסיעות
            z_steps = [final_z]
            if op['type'] == 'Milling' and t_row['NC_Tool'] == "T2" and final_z < 0.1 and p_idx == 0:
                z_steps = [round(parser.header['T'] - 2.0, 3), final_z]

            processed.append({
                'x': nx + ox, 'y': ny + oy, 'z': z_steps,
                'tool': t_row['NC_Tool'], 'diam': t_row['Diameter'],
                'rpm': t_row['RPM'], 'feed': t_row['Feed'],
                'desc': t_row['Desc'], 'type': op['type'],
                'is_start': (p_idx == 0)
            })
    
    return sorted(processed, key=lambda x: 99 if x['tool'] == "T2" else 1)

# --- 5. ממשק משתמש ---
st.title("🚀 Darwish CNC Pro - V5.9 (Vector-Offset Master)")
uploaded = st.file_uploader("טען קובץ MPR", type=['mpr', 'txt'])

if uploaded:
    parser = BlockMPRParser(uploaded.read().decode('utf-8', errors='ignore'))
    if parser.header['L'] == 0: st.error("שגיאה בקריאת מידות הפלטה.")
    else:
        final_list = process_production(parser, st.session_state.tool_df, off_x, off_y, gz)
        st.success(f"לוח נקלט: {parser.header['L']}x{parser.header['W']} מילימטר (צידוד RK פעיל)")

        fig = go.Figure()
        fig.add_shape(type="rect", x0=0, y0=0, x1=MACHINE_WIDTH_X, y1=MACHINE_LENGTH_Y, fillcolor="gray", opacity=0.05)
        fig.add_shape(type="rect", x0=off_x, y0=off_y, x1=off_x+parser.header['W'], y1=off_y+parser.header['L'], line_color="brown", fillcolor="brown", opacity=0.15)
        
        for idx, b in enumerate(final_list):
            color = "blue" if b['type'] == 'Drill' else "red"
            fig.add_trace(go.Scatter(
                x=[b['x']], y=[b['y']], mode='markers+lines' if b['type']=='Milling' else 'markers',
                marker=dict(size=b['diam'], sizemode='diameter', color=color, opacity=0.7),
                hovertemplate=f"<b>{b['type']}: {b['desc']} ({b['tool']})</b><br>קוטר: {b['diam']} מילימטר<br>עומק Z: {b['z'][-1]}<extra></extra>"
            ))

        fig.update_layout(title="הדמיית ייצור 1:1 (Net Size)", xaxis=dict(range=[-50, 1400]), yaxis=dict(range=[-50, 3100]), width=600, height=800, dragmode='pan', yaxis_scaleanchor="x", showlegend=False)
        st.plotly_chart(fig, config={'scrollZoom': True})

        if st.button("🛠️ הפק קוד NC"):
            nc = ["%", "(DARWISH V5.9 - VECTOR RK)", "N10 G90 G54 G21 G17"]
            curr_t, l = None, 20
            for b in final_list:
                if b['tool'] != curr_t:
                    if curr_t: nc.append(f"N{l} M05"); l += 10
                    nc.append(f"N{l} {b['tool']} M06"); l += 10
                    nc.append(f"N{l} G43 H{b['tool'][1:]}"); l += 10
                    nc.append(f"N{l} S{int(b['rpm'])} M03"); l += 10
                    curr_t = b['tool']
                
                if b['is_start']:
                    nc.append(f"N{l} G00 X{b['x']:.3f} Y{b['y']:.3f}"); l += 10
                    for z_step in b['z']:
                        nc.append(f"N{l} G01 Z{z_step:.3f} F{int(b['feed'])}"); l += 10
                else:
                    nc.append(f"N{l} G01 X{b['x']:.3f} Y{b['y']:.3f} F{int(b['feed'])}"); l += 10
            
            nc.extend([f"N{l} G00 Z35.0", f"N{l+10} M05", f"N{l+20} M30", f"N{l+30} M200", "%"])
            st.download_button("הורד קובץ NC", "\n".join(nc), file_name="production.nc")
            st.code("\n".join(nc), language='gcode')
