import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import re
import math

# --- חוק יסוד: פרוטוקול דרוויש 2026 ---
# סטטוס: גרסה 5.0 - הרמטית (חסינת אלצהיימר)
# שפה: עברית טכנית (שימוש במילים מילימטר וסנטימטר בלבד)

st.set_page_config(page_title="Darwish CNC Pro - V5.0", layout="wide")

# הגדרות מכונה קשיחות (אבי - ELKUM ELP1330DU)
MACHINE_WIDTH_X = 1300.0  # מילימטר
MACHINE_LENGTH_Y = 3050.0 # מילימטר

# --- 1. מסד כלים (המציאות בשטח - לפי תמונת עץ הכלים) ---
TOOL_DATABASE = {
    "142": {"NC_Tool": "T2", "Diameter": 6.0, "Desc": "כרסום יהלום (חיתוך סופי)", "Order": 99}, # תמיד אחרון
    "158": {"NC_Tool": "T3", "Diameter": 8.0, "Desc": "כרסום 8 מילימטר", "Order": 1},
    "128": {"NC_Tool": "T4", "Diameter": 12.0, "Desc": "כרסום 12 מילימטר", "Order": 1},
    "35":  {"NC_Tool": "T6", "Diameter": 35.0, "Desc": "מקדח צירים", "Order": 1},
    "130": {"NC_Tool": "T13", "Diameter": 0.2, "Desc": "כרסום גירונג 90/45", "Order": 1},
    "5.0": {"NC_Tool": "T44", "Diameter": 5.0, "Desc": "מקדח 5 מילימטר", "Order": 1},
    "8.0": {"NC_Tool": "T47", "Diameter": 8.0, "Desc": "מקדח 8 מילימטר", "Order": 1},
    "15.0": {"NC_Tool": "T49", "Diameter": 15.0, "Desc": "מקדח 15 מילימטר", "Order": 1},
    "20.0": {"NC_Tool": "T28", "Diameter": 20.0, "Desc": "מקדח 20 מילימטר", "Order": 1}
}

# --- 2. מנוע טרנספורמציה וחישובי Z ---
def transform_coords(x, y, board_w, board_l):
    # סיבוב 90 מעלות CCW לפי הפרוטוקול
    new_x = board_w - y
    new_y = x
    return new_x, new_y

def calculate_z(op_type, val, thickness, global_offset, local_offset):
    # נוסחה תלת-שכבתית: Z_final = ZA + GlobalOffset + LocalOffset
    # בקידוח/פוקט (TI): Z = Thickness - TI
    if op_type == 'TI':
        base_z = thickness - val
    else: # ZA (מוחלט)
        base_z = val
    return base_z + global_offset + local_offset

# --- 3. מנוע ה-Parser (זיהוי בלוקים וסדרות) ---
class MPRParser:
    def __init__(self, content, g_offset, l_offsets):
        self.lines = content.splitlines()
        self.header = {'L': 0, 'W': 0, 'T': 0}
        self.ops = []
        self.g_offset = g_offset
        self.l_offsets = l_offsets
        self._parse()

    def _extract(self, line):
        return dict(re.findall(r'(\w+)="?([^"\s]+)"?', line))

    def _parse(self):
        for line in self.lines:
            if "L=" in line: self.header['L'] = float(self._extract(line).get('L', 0))
            if "W=" in line: self.header['W'] = float(self._extract(line).get('W', 0))
            if "T=" in line: self.header['T'] = float(self._extract(line).get('T', 0))

        for line in self.lines:
            # קידוחים (כולל Cabi-neo)
            if line.startswith("<102"):
                p = self._extract(line)
                num = int(p.get('AN', 1))
                dist = float(p.get('AB', 0))
                ang = math.radians(float(p.get('WI', 0)))
                tid = p.get('DU', '5.0')
                
                for i in range(num):
                    raw_x = float(p['XA']) + (i * dist * math.cos(ang))
                    raw_y = float(p['YA']) + (i * dist * math.sin(ang))
                    nx, ny = transform_coords(raw_x, raw_y, self.header['W'], self.header['L'])
                    
                    z = calculate_z('TI', float(p['TI']), self.header['T'], self.g_offset, self.l_offsets.get(tid, 0))
                    
                    self.ops.append({
                        'type': 'Drill', 'x': nx, 'y': ny, 'z': z, 
                        'tool': TOOL_DATABASE.get(tid, {"NC_Tool": "UNKNOWN"})['NC_Tool'],
                        'order': TOOL_DATABASE.get(tid, {"Order": 1})['Order'],
                        'diam': TOOL_DATABASE.get(tid, {"Diameter": 0})['Diameter']
                    })

# --- 4. ממשק משתמש (Streamlit) ---
st.title("🛠️ Darwish CNC Pro - V5.0 (Industrial)")

with st.sidebar:
    st.header("הגדרות עומק (מילימטר)")
    global_z = st.number_input("תיקון Z גלובלי (Global Offset)", value=0.0, step=0.1)
    st.info("ערך שלילי מעמיק לתוך השולחן")

uploaded = st.file_uploader("טען קובץ MPR", type=['mpr', 'txt'])

if uploaded:
    content = uploaded.read().decode('utf-8', errors='ignore')
    parser = MPRParser(content, global_z, {})
    
    # הצגת נתונים
    st.success(f"הקובץ נקלט. פלטה: {parser.header['L']}x{parser.header['W']} עובי {parser.header['T']} מילימטר")
    
    # הדמיה (Plotly)
    fig = go.Figure()
    # שולחן מכונה
    fig.add_shape(type="rect", x0=0, y0=0, x1=MACHINE_WIDTH_X, y1=MACHINE_LENGTH_Y, line_color="gray", opacity=0.3)
    
    for op in parser.ops:
        r = op['diam'] / 2
        fig.add_shape(type="circle", x0=op['x']-r, y0=op['y']-r, x1=op['x']+r, y1=op['y']+r, fillcolor="blue", opacity=0.7)

    fig.update_layout(
        title="הדמיית ייצור (1:1)",
        xaxis=dict(title="X (מילימטר)", range=[-50, 1400]),
        yaxis=dict(title="Y (מילימטר)", range=[-50, 3100]),
        dragmode='pan',
        width=800, height=1000
    )
    st.plotly_chart(fig, config={'scrollZoom': True})

    # הפקת NC (טיוטה ראשונית)
    if st.button("הפק קוד NC"):
        st.code("N10 G90 G54 G21 G17\n(NC Generation logic
