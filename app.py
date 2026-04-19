import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import re
import math

# --- חוק יסוד: פרוטוקול דרוויש 2026 ---
# סטטוס: גרסה 5.4 - הרמטית (תיקון KeyError, מסד כלים מורחב ופיצוי קוטר)
# שפה: עברית טכנית (שימוש במילים מילימטר וסנטימטר בלבד)

st.set_page_config(page_title="Darwish CNC Pro - V5.4", layout="wide")

# הגדרות מכונה (אבי - ELKUM ELP1330DU)
MACHINE_WIDTH_X = 1300.0  # מילימטר
MACHINE_LENGTH_Y = 3050.0 # מילימטר

# --- 1. ניהול מסד כלים (Industrial Tool Database) ---
if 'tool_df' not in st.session_state:
    # רשימת כלים מאוחדת (תמונת עץ הכלים + מסמכי דרוויש)
    initial_tools = {
        "ID_MPR": ["142", "158", "128", "35", "130", "5.0", "8.0", "15.0", "40.0", "19.0", "6.0", "20.0", "7.0", "16.0", "42.0"],
        "NC_Tool": ["T2", "T3", "T4", "T6", "T13", "T44", "T47", "T49", "T1", "T8", "T10", "T28", "T7", "T16", "T42"],
        "Diameter": [6.0, 8.0, 12.0, 35.0, 0.2, 5.0, 8.0, 15.0, 40.0, 19.0, 6.0, 20.0, 10.0, 10.0, 10.0],
        "RPM": [18000, 18000, 16000, 3000, 18000, 4500, 4500, 3000, 12000, 16000, 18000, 3000, 18000, 18000, 18000],
        "Feed": [3000, 2500, 3500, 1000, 2000, 1500, 1500, 800, 4000, 3000, 2000, 1000, 2000, 2000, 2000],
        "Desc": ["כרסום יהלום (קונטור)", "כרסום 8 מילימטר", "כרסום 12 מילימטר", "מקדח צירים", "גירונג 90/45", "מקדח 5 מילימטר", "מקדח 8 מילימטר", "מקדח 15 מילימטר", "כרסום ניקוי", "כרסום 19 מילימטר", "כרסום/מקדח 6", "מקדח 20 מילימטר", "מקל סבא 1", "מקל סבא 2", "כלי פינה/מגרעת"]
    }
    st.session_state.tool_df = pd.DataFrame(initial_tools)

with st.sidebar:
    st.header("🛠️ הגדרות ייצור")
    
    with st.expander("עריכת מסד כלים (T1-T49)", expanded=False):
        st.write("עדכן קוטר/מהירות (מילימטר)")
        edited_tools = st.data_editor(st.session_state.tool_df, num_rows="dynamic", key="tool_editor_v54")
        st.session_state.tool_df = edited_tools

    st.markdown("---")
    offset_x = st.number_input("הזזת פלטה על ציר X (מילימטר)", value=0.0, step=1.0)
    offset_y = st.number_input("הזזת פלטה על ציר Y (מילימטר)", value=0.0, step=1.0)
    global_z_offset = st.number_input("תיקון Z גלובלי (מילימטר)", value=0.0, step=0.1, help="ערך שלילי מעמיק לתוך השולחן")
    
    if st.button("🔄 רענון עמוק (Cache Clear)"):
        st.cache_data.clear()
        st.rerun()

# --- 2. מנועי ליבה (מתמטיקה וטרנספורמציה) ---
def _safe_float(val):
    try:
        clean_val = re.sub(r'[^0-9.\-]', '', str(val))
        return float(clean_val) if clean_val else 0.0
    except:
        return 0.0

def rotate_90_ccw(x, y, board_w, board_l):
    # נוסחת הפרוטוקול: X_NC = Board_Width - Y_MPR; Y_NC = X_MPR
    return (board_w - y), x

def calculate_z(z_type, val, thickness, global_z):
    # Z_final = ZA + GlobalOffset
    base_z = (thickness - val) if z_type == 'TI' else val
    return round(base_z + global_z, 3)

# --- 3. Parser הרמטי (מניעת KeyError) ---
class SecureMPRParser:
    def __init__(self, content):
        self.lines = content.splitlines()
        self.header = {'L': 0.0, 'W': 0.0, 'T': 0.0}
        self.ops = []
        self._parse()

    def _extract_params(self, line):
        return dict(re.findall(r'(\w+)="?([^"\s]+)"?', line))

    def _parse(self):
        # חילוץ מידות פלטה
        for line in self.lines:
            if any(key in line for key in ["L=", "W=", "T="]):
                p = self._extract_params(line)
                if 'L' in p: self.header['L'] = _safe_float(p['L'])
                if 'W' in p: self.header['W'] = _safe_float(p['W'])
                if 'T' in p: self.header['T'] = _safe_float(p['T'])

        # חילוץ פעולות בטוח (שימוש ב-.get למניעת קריסה)
        for line in self.lines:
            if line.startswith("<102"): # קידוחים
                p = self._extract_params(line)
                num = int(_safe_float(p.get('AN', 1)))
                dist = _safe_float(p.get('AB', 0))
                ang = math.radians(_safe_float(p.get('WI', 0)))
                tid = p.get('DU', '5.0')
                
                for i in range(num):
                    rx = _safe_float(p.get('XA', 0)) + (i * dist * math.cos(ang))
                    ry = _safe_float(p.get('YA', 0)) + (i * dist * math.sin(ang))
                    self.ops.append({
                        'type': 'Drill', 'raw_x': rx, 'raw_y': ry, 
                        'raw_z': _safe_float(p.get('TI', 0)), 'z_type': 'TI',
                        'mpr_id': tid
                    })

            if line.startswith("<105"): # כרסומים
                p = self._extract_params(line)
                self.ops.append({
                    'type': 'Milling', 
                    'raw_x': _safe_float(p.get('XA', 0)), 
                    'raw_y': _safe_float(p.get('YA', 0)),
                    'raw_z': _safe_float(p.get('ZA', 0)), 'z_type': 'ZA',
                    'mpr_id': p.get('TNO', '142')
                })

# --- 4. עיבוד וייצור (Production Logic) ---
def process_production(parser, tool_df, off_x, off_y, global_z):
    processed = []
    for op in parser.ops:
        # 1. סיבוב והזזה כמקשה אחת
        nx, ny = rotate_90_ccw(op['raw_x'], op['raw_y'], parser.header['W'], parser.header['L'])
        final_x = nx + off_x
        final_y = ny + off_y
        
        # 2. הצלבת כלי ונתוני עריכה
        t_info = tool_df[tool_df['ID_MPR'] == op['mpr_id']]
        if t_info.empty:
            t_info = tool_df[tool_df['NC_Tool'] == "T2"]
        t_row = t_info.iloc[0]
        
        fz = calculate_z(op['z_type'], op['raw_z'], parser.header['T'], global_z)
        
        processed.append({
            'x': final_x, 'y': final_y, 'z': [fz],
            'tool': t_row['NC_Tool'], 'diam': t_row['Diameter'],
            'rpm': t_row['RPM'], 'feed': t_row['Feed'],
            'type': op['type'], 'order': 99 if t_row['NC_Tool'] == "T2" else 1
        })
    
    # מיון ואופטימיזציית שכן קרוב
    optimized = []
    curr_pos = (0, 0)
    tools_in_job = sorted(list(set(o['tool'] for o in processed)), key=lambda t: next(o['order'] for o in processed if o['tool']==t))
    
    for t in tools_in_job:
        group = [o for o in processed if o['tool'] == t]
        while group:
            nxt = min(group, key=lambda o: math.sqrt((o['x']-curr_pos[0])**2 + (o['y']-curr_pos[1])**2))
            # חוק הניתוק הסופי (Two-Pass)
            if nxt['z'][0] < 0.1:
                nxt['z'] = [round(parser.header['T'] - 2.0, 3), nxt['z'][0]]
            optimized.append(nxt)
            curr_pos = (nxt['x'], nxt['y'])
            group.remove(nxt)
    return optimized

# --- 5. ממשק משתמש (UI) ---
st.title("🚀 Darwish CNC Pro - V5.4 (Industrial)")

uploaded = st.file_uploader("טען קובץ MPR לייצור", type=['mpr', 'txt'])

if uploaded:
    content = uploaded.read().decode('utf-8', errors='ignore')
    parser = SecureMPRParser(content)
    
    if parser.header['L'] == 0:
        st.error("שגיאה בקריאת מידות הפלטה.")
    else:
        final_list = process_production(parser, st.session_state.tool_df, offset_x, offset_y, global_z_offset)
        
        st.success(f"לוח נקלט: {parser.header['L']}x{parser.header['W']} מילימטר")

        fig = go.Figure()
        # שולחן ופלטה
        fig.add_shape(type="rect", x0=0, y0=0, x1=MACHINE_WIDTH_X, y1=MACHINE_LENGTH_Y, line_color="gray", fillcolor="gray", opacity=0.05)
        fig.add_shape(type="rect", x0=offset_x, y0=offset_y, x1=offset_x+parser.header['W'], y1=offset_y+parser.header['L'], line_color="brown", opacity=0.2)
        
        for idx, b in enumerate(final_list):
            r = b['diam'] / 2
            fig.add_shape(type="circle", x0=b['x']-r, y0=b['y']-r, x1=b['x']+r, y1=b['y']+r, fillcolor="blue" if b['type']=='Drill' else "red", opacity=0.8)
            fig.add_annotation(x=b['x'], y=b['y'], text=str(idx+1), showarrow=False, font=dict(size=9, color="white"))

        fig.update_layout(title="הדמיית ייצור 1:1", xaxis=dict(title="X מילימטר", range=[-50, 1400]), yaxis=dict(title="Y מילימטר", range=[-50, 3100]), width=600, height=800, dragmode='pan', yaxis_scaleanchor="x")
        st.plotly_chart(fig, config={'scrollZoom': True})

        if st.button("🛠️ הפק קוד NC"):
            nc = ["%", "(DARWISH V5.4)", f"(PLATE: {parser.header['L']}x{parser.header['W']})", "N10 G90 G54 G21 G17"]
            curr_t, l = None, 20
            for b in final_list:
                if b['tool'] != curr_t:
                    if curr_t: nc.append(f"N{l} M05"); l += 10
                    nc.append(f"N{l} {b['tool']} M06"); l += 10
                    nc.append(f"N{l} G43 H{b['tool'][1:]}"); l += 10
                    nc.append(f"N{l} S{int(b['rpm'])} M03"); l += 10
                    curr_t = b['tool']
                nc.append(f"N{l} G00 X{b['x']:.3f} Y{b['y']:.3f}")
                l += 10
                for z_step in b['z']:
                    nc.append(f"N{l} G01 Z{z_step:.3f} F{int(b['feed'])}")
                    l += 10
                    nc.append(f"N{l} G00 Z35.0")
                    l += 10
            nc.extend([f"N{l} M05", f"N{l+10} M30", f"N{l+20} M200", "%"])
            st.download_button("הורד קובץ NC", "\n".join(nc), file_name="avi_production.nc")
            st.code("\n".join(nc), language='gcode')
