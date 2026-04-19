import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import re
import math

# --- חוק יסוד: פרוטוקול דרוויש 2026 ---
# סטטוס: גרסה 5.1 - הרמטית סופית (תיקון SyntaxError)
# שפה: עברית טכנית (מילימטר/סנטימטר במלואן)

st.set_page_config(page_title="Darwish CNC Pro - V5.1", layout="wide")

# הגדרות מכונה (אבי - ELKUM ELP1330DU)
MACHINE_WIDTH_X = 1300.0  # מילימטר
MACHINE_LENGTH_Y = 3050.0 # מילימטר

# --- 1. מסד כלים (המציאות בשטח - היררכיית אמת) ---
TOOL_DATABASE = {
    "142": {"NC_Tool": "T2", "Diameter": 6.0, "Desc": "כרסום יהלום (קונטור)", "Order": 99}, # תמיד אחרון
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
    new_x = board_w - y
    new_y = x
    return new_x, new_y

def calculate_z_final(op_type, val, thickness, global_offset, local_offset):
    # Z_final = ZA + GlobalOffset + LocalOffset
    if op_type == 'TI': # יחסי מהפנים
        base_z = thickness - val
    else: # ZA מוחלט מהשולחן
        base_z = val
    return round(base_z + global_offset + local_offset, 3)

# --- 3. מנוע ה-Parser (זיהוי בלוקים וסדרות) ---
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
        # שלב א: חילוץ מידות פלטה [001]
        for line in self.lines:
            if "L=" in line or "W=" in line:
                p = self._extract(line)
                self.header['L'] = float(p.get('L', self.header['L']))
                self.header['W'] = float(p.get('W', self.header['W']))
                self.header['T'] = float(p.get('T', self.header['T']))

        # שלב ב: סריקת פעולות
        for line in self.lines:
            # קידוחים וסדרות (Cabi-neo)
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
                    
                    z = calculate_z_final('TI', float(p['TI']), self.header['T'], self.g_offset, 0)
                    
                    tool_info = TOOL_DATABASE.get(tid, {"NC_Tool": f"T{tid}", "Diameter": 5.0, "Order": 1})
                    self.ops.append({
                        'type': 'Drill', 'x': nx, 'y': ny, 'z': [z], 
                        'tool': tool_info['NC_Tool'], 'order': tool_info['Order'],
                        'diam': tool_info['Diameter'], 'desc': tool_info['Desc']
                    })

            # כרסומים (Konturfraesen)
            if line.startswith("<105"):
                p = self._extract(line)
                tid = p.get('TNO', '142')
                # מיקום זמני (מרכז) - יורחב בסריקת וקטורים
                nx, ny = transform_coords(self.header['L']/2, self.header['W']/2, self.header['W'], self.header['L'])
                z = calculate_z_final('ZA', float(p.get('ZA', 0)), self.header['T'], self.g_offset, 0)
                
                tool_info = TOOL_DATABASE.get(tid, {"NC_Tool": "T2", "Diameter": 6.0, "Order": 99})
                self.ops.append({
                    'type': 'Milling', 'x': nx, 'y': ny, 'z': [z],
                    'tool': tool_info['NC_Tool'], 'order': tool_info['Order'],
                    'diam': tool_info['Diameter'], 'desc': tool_info['Desc']
                })

# --- 4. אופטימיזציה (השכן הקרוב ומיון כלים) ---
def optimize_production(ops):
    if not ops: return []
    # מיון לפי סדר כלי (T2 בסוף)
    sorted_ops = sorted(ops, key=lambda x: x['order'])
    
    optimized = []
    curr_pos = (0, 0)
    
    # קיבוץ לפי כלי למניעת החלפות מיותרות
    tools = sorted(list(set(o['tool'] for o in sorted_ops)))
    for t in tools:
        tool_group = [o for o in sorted_ops if o['tool'] == t]
        while tool_group:
            # השכן הקרוב
            next_op = min(tool_group, key=lambda o: math.sqrt((o['x']-curr_pos[0])**2 + (o['y']-curr_pos[1])**2))
            
            # חוק הניתוק הסופי (Two-Pass)
            if next_op['z'][0] < 0.1: # חדירה לשולחן
                thickness = 19.0 # ברירת מחדל אם לא זוהה
                next_op['z'] = [round(thickness - 2.0, 3), next_op['z'][0]] # Scoring + Cut
            
            optimized.append(next_op)
            curr_pos = (next_op['x'], next_op['y'])
            tool_group.remove(next_op)
            
    return optimized

# --- 5. ממשק משתמש (UI/UX) ---
st.title("🚀 Darwish CNC Pro - V5.1 (Industrial)")

with st.sidebar:
    st.header("הגדרות עומק (מילימטר)")
    global_z = st.number_input("תיקון Z גלובלי (Global Offset)", value=0.0, step=0.1, help="ערך שלילי מעמיק לתוך השולחן")
    st.markdown("---")
    st.write("### מסד כלים פעיל")
    st.table(pd.DataFrame(TOOL_DATABASE).T[['NC_Tool', 'Diameter', 'Desc']])

uploaded = st.file_uploader("טען קובץ MPR לייצור", type=['mpr', 'txt'])

if uploaded:
    content = uploaded.read().decode('utf-8', errors='ignore')
    parser = MPRParser(content, global_z)
    final_ops = optimize_production(parser.ops)
    
    st.success(f"לוח זוהה: {parser.header['L']}x{parser.header['W']} בעובי {parser.header['T']} מילימטר")

    # הדמיה גרפית (1:1)
    fig = go.Figure()
    # שולחן מכונה (אפור)
    fig.add_shape(type="rect", x0=0, y0=0, x1=MACHINE_WIDTH_X, y1=MACHINE_LENGTH_Y, line_color="gray", fillcolor="gray", opacity=0.1)
    # פלטה (חום)
    fig.add_shape(type="rect", x0=0, y0=0, x1=parser.header['W'], y1=parser.header['L'], line_color="brown", fillcolor="brown", opacity=0.2)
    
    for idx, op in enumerate(final_ops):
        r = op['diam'] / 2
        color = "blue" if op['type'] == 'Drill' else "red"
        fig.add_shape(type="circle", x0=op['x']-r, y0=op['y']-r, x1=op['x']+r, y1=op['y']+r, fillcolor=color, opacity=0.8, line_width=1)
        # מספר פעולה ל-Timeline
        fig.add_annotation(x=op['x'], y=op['y'], text=str(idx+1), showarrow=False, font=dict(size=10, color="white"))

    fig.update_layout(
        title="הדמיית מסלול כלי (1:1 Aspect Ratio)",
        xaxis=dict(title="X (מילימטר)", range=[-100, 1400], gridcolor='lightgray'),
        yaxis=dict(title="Y (מילימטר)", range=[-100, 3150], gridcolor='lightgray'),
        width=700, height=900,
        dragmode='pan', # נכס קבוע
        yaxis_scaleanchor="x" # נעילת יחס 1:1
    )
    st.plotly_chart(fig, config={'scrollZoom': True}, use_container_width=False)

    # הפקת קוד NC
    if st.button("🛠️ הפק קוד NC סופי"):
        nc_code = [
            "%",
            "(PRODUCED BY DARWISH CNC PRO V5.1)",
            "(CLIENT: EYAL | MACHINE: AVI)",
            "N10 G90 G54 G21 G17" # כותרת קבועה
        ]
        
        curr_tool = None
        line_num = 20
        
        for op in final_ops:
            if op['tool'] != curr_tool:
                if curr_tool: nc_code.append(f"N{line_num} M05") # כיבוי לפני החלפה
                line_num += 10
                nc_code.append(f"N{line_num} {op['tool']} M06") # החלפת כלי
                line_num += 10
                nc_code.append(f"N{line_num} G43 H{op['tool'][1:]}") # פיצוי אורך כלי
                line_num += 10
                nc_code.append(f"N{line_num} S18000 M03") # הפעלה
                curr_tool = op['tool']
                line_num += 10
            
            # תנועה וביצוע
            nc_code.append(f"N{line_num} G00 X{op['x']:.3f} Y{op['y']:.3f}")
            line_num += 10
            for z_step in op['z']:
                nc_code.append(f"N{line_num} G01
