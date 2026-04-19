import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import re
import math

# --- חוק יסוד: פרוטוקול דרוויש 2026 ---
# סטטוס: גרסה 5.2 - תיקון שגיאות תחביר וייעול רענון
# שפה: עברית טכנית (שימוש במילים מילימטר וסנטימטר בלבד)

st.set_page_config(page_title="Darwish CNC Pro - V5.2", layout="wide")

# הגדרות מכונה קשיחות (אבי - ELKUM ELP1330DU)
MACHINE_WIDTH_X = 1300.0  # מילימטר
MACHINE_LENGTH_Y = 3050.0 # מילימטר

# --- 1. מסד כלים (היררכיית אמת - מציאות בשטח) ---
TOOL_DATABASE = {
    "142": {"NC_Tool": "T2", "Diameter": 6.0, "Desc": "כרסום יהלום (חיתוך סופי)", "Order": 99},
    "158": {"NC_Tool": "T3", "Diameter": 8.0, "Desc": "כרסום 8 מילימטר", "Order": 1},
    "128": {"NC_Tool": "T4", "Diameter": 12.0, "Desc": "כרסום 12 מילימטר", "Order": 1},
    "35":  {"NC_Tool": "T6", "Diameter": 35.0, "Desc": "מקדח צירים", "Order": 1},
    "130": {"NC_Tool": "T13", "Diameter": 0.2, "Desc": "כרסום גירונג 90/45", "Order": 1},
    "5.0": {"NC_Tool": "T44", "Diameter": 5.0, "Desc": "מקדח 5 מילימטר (מדפים/קבינאו)", "Order": 1},
    "8.0": {"NC_Tool": "T47", "Diameter": 8.0, "Desc": "מקדח 8 מילימטר (דיבלים)", "Order": 1},
    "15.0": {"NC_Tool": "T49", "Diameter": 15.0, "Desc": "מקדח 15 מילימטר", "Order": 1},
    "40.0": {"NC_Tool": "T1", "Diameter": 40.0, "Desc": "כרסום ניקוי פוקט", "Order": 1}
}

# --- 2. מנוע טרנספורמציה וחישובי Z ---
def transform_coords(x, y, board_w, board_l):
    # סיבוב 90 מעלות CCW: X_NC = Board_Width - Y_MPR; Y_NC = X_MPR
    return (board_w - y), x

def calculate_z_final(op_type, val, thickness, global_offset):
    # נוסחה: Z_final = ZA + GlobalOffset
    if op_type == 'TI': # עומק יחסי מהפנים
        base_z = thickness - val
    else: # ZA עומק מוחלט מהשולחן
        base_z = val
    return round(base_z + global_offset, 3)

# --- 3. מנוע ה-Parser (זיהוי בלוקים וסדרות קבינאו) ---
class MPRParser:
    def __init__(self, content, g_offset):
        self.lines = content.splitlines()
        self.header = {'L': 0, 'W': 0, 'T': 0}
        self.ops = []
        self.g_offset = g_offset
        self._parse()

    def _extract(self, line):
        return dict(re.findall(r'(\w+)="?([^"\s]+)"?', line))

    def _parse(self):
        # חילוץ מידות פלטה
        for line in self.lines:
            if "L=" in line or "W=" in line:
                p = self._extract(line)
                self.header['L'] = float(p.get('L', self.header['L']))
                self.header['W'] = float(p.get('W', self.header['W']))
                self.header['T'] = float(p.get('T', self.header['T']))

        # סריקת פעולות
        for line in self.lines:
            if line.startswith("<102"): # קידוחים וסדרות
                p = self._extract(line)
                num = int(p.get('AN', 1))
                dist = float(p.get('AB', 0))
                ang = math.radians(float(p.get('WI', 0)))
                tid = p.get('DU', '5.0')
                for i in range(num):
                    raw_x = float(p['XA']) + (i * dist * math.cos(ang))
                    raw_y = float(p['YA']) + (i * dist * math.sin(ang))
                    nx, ny = transform_coords(raw_x, raw_y, self.header['W'], self.header['L'])
                    z = calculate_z_final('TI', float(p['TI']), self.header['T'], self.g_offset)
                    tool_info = TOOL_DATABASE.get(tid, {"NC_Tool": f"T{tid}", "Diameter": 5.0, "Order": 1, "Desc": "כלי לא מזוהה"})
                    self.ops.append({'type': 'Drill', 'x': nx, 'y': ny, 'z': [z], 'tool': tool_info['NC_Tool'], 'order': tool_info['Order'], 'diam': tool_info['Diameter'], 'desc': tool_info['Desc']})

            if line.startswith("<105"): # כרסומים
                p = self._extract(line)
                tid = p.get('TNO', '142')
                nx, ny = transform_coords(self.header['L']/2, self.header['W']/2, self.header['W'], self.header['L'])
                z = calculate_z_final('ZA', float(p.get('ZA', 0)), self.header['T'], self.g_offset)
                tool_info = TOOL_DATABASE.get(tid, {"NC_Tool": "T2", "Diameter": 6.0, "Order": 99, "Desc": "כרסום יהלום"})
                self.ops.append({'type': 'Milling', 'x': nx, 'y': ny, 'z': [z], 'tool': tool_info['NC_Tool'], 'order': tool_info['Order'], 'diam': tool_info['Diameter'], 'desc': tool_info['Desc']})

# --- 4. אופטימיזציה ---
def optimize_production(ops):
    if not ops: return []
    sorted_ops = sorted(ops, key=lambda x: x['order'])
    optimized = []
    curr_pos = (0, 0)
    tools = sorted(list(set(o['tool'] for o in sorted_ops)))
    for t in tools:
        group = [o for o in sorted_ops if o['tool'] == t]
        while group:
            next_op = min(group, key=lambda o: math.sqrt((o['x']-curr_pos[0])**2 + (o['y']-curr_pos[1])**2))
            if next_op['z'][0] < 0.1: # חוק הניתוק הסופי
                next_op['z'] = [round(19.0 - 2.0, 3), next_op['z'][0]]
            optimized.append(next_op)
            curr_pos = (next_op['x'], next_op['y'])
            group.remove(next_op)
    return optimized

# --- 5. ממשק משתמש ---
st.title("🛠️ Darwish CNC Pro - V5.2 (Industrial)")

with st.sidebar:
    st.header("הגדרות ייצור")
    global_z = st.number_input("תיקון Z גלובלי (מילימטר)", value=0.0, step=0.1)
    if st.button("🔄 ניקוי זיכרון מטמון"):
        st.cache_data.clear()
        st.rerun()
    st.markdown("---")
    st.table(pd.DataFrame(TOOL_DATABASE).T[['NC_Tool', 'Diameter', 'Desc']])

uploaded = st.file_uploader("טען קובץ MPR", type=['mpr', 'txt'])

if uploaded:
    content = uploaded.read().decode('utf-8', errors='ignore')
    parser = MPRParser(content, global_z)
    final_ops = optimize_production(parser.ops)
    
    st.success(f"לוח זוהה: {parser.header['L']}x{parser.header['W']} עובי {parser.header['T']} מילימטר")

    fig = go.Figure()
    # שולחן מכונה
    fig.add_shape(type="rect", x0=0, y0=0, x1=MACHINE_WIDTH_X, y1=MACHINE_LENGTH_Y, line_color="gray", fillcolor="gray", opacity=0.1)
    # פלטה
    fig.add_shape(type="rect", x0=0, y0=0, x1=parser.header['W'], y1=parser.header['L'], line_color="brown", fillcolor="brown", opacity=0.2)
    
    for idx, op in enumerate(final_ops):
        r = op['diam'] / 2
        fig.add_shape(type="circle", x0=op['x']-r, y0=op['y']-r, x1=op['x']+r, y1=op['y']+r, fillcolor="blue" if op['type']=='Drill' else "red", opacity=0.8)
        fig.add_annotation(x=op['x'], y=op['y'], text=str(idx+1), showarrow=False, font=dict(size=10, color="white"))

    fig.update_layout(title="הדמיה 1:1", xaxis=dict(title="X מילימטר", range=[-50, 1400]), yaxis=dict(title="Y מילימטר", range=[-50, 3100]), dragmode='pan', width=700, height=900, yaxis_scaleanchor="x")
    st.plotly_chart(fig, config={'scrollZoom': True})

    if st.button("🛠️ הפק קוד NC"):
        nc = ["%", "(PRODUCED BY DARWISH V5.2)", "N10 G90 G54 G21 G17"]
        curr_t, l = None, 20
        for op in final_ops:
            if op['tool'] != curr_t:
                if curr_t: nc.append(f"N{l} M05")
                l += 10
                nc.append(f"N{l} {op['tool']} M06")
                l += 10
                nc.append(f"N{l} G43 H{op['tool'][1:]}")
                l += 10
                nc.append(f"N{l} S18000 M03")
                curr_t = op['tool']
                l += 10
            nc.append(f"N{l} G00 X{op['x']:.3f} Y{op['y']:.3f}")
            l += 10
            for z_val in op['z']:
                nc.append(f"N{l} G01 Z{z_val:.3f} F2000")
                l += 10
                nc.append(f"N{l} G00 Z35.0")
                l += 10
        nc.extend([f"N{l} M05", f"N{l+10} M30", f"N{l+20} M200", "%"])
        st.download_button("הורד קובץ NC", "\n".join(nc), file_name="output.nc")
        st.code("\n".join(nc), language='gcode')
