import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import re
import math
import io

# --- חוק יסוד: פרוטוקול דרוויש 2026 - גרסה 48.20 ---
# סטטוס: Full Protocol V2.0 Implementation
# ייעוד: המרה הרמטית של MPR ל-NC כולל אופטימיזציה וטרנספורמציה מלאה.

st.set_page_config(page_title="Darwish CNC 2026 - V48.20", layout="wide")

# כותרת גרסה
st.markdown("<h1 style='text-align: center; color: #D32F2F;'>🚀 Darwish CNC Pro - Version 48.20</h1>", unsafe_allow_html=True)

# --- 1. ניהול מסד כלים (Persistence & Expander) ---
with st.expander("🛠️ הגדרות מסד כלים (Tool Database)", expanded=False):
    if 'tool_df' not in st.session_state:
        data = {
            "MPR_Name": ["5.0", "8.0", "15.0", "35.0", "142", "6.0", "20.0"],
            "NC_Tool": ["T44", "T47", "T49", "T6", "T2", "T10", "T28"],
            "Diameter": [5.0, 8.0, 15.0, 35.0, 12.0, 6.0, 20.0],
            "Feed": [2000, 2000, 2000, 2000, 4000, 3500, 2500],
            "RPM": [4500, 4500, 4500, 4500, 18000, 16000, 12000]
        }
        st.session_state.tool_df = pd.DataFrame(data)
    
    st.session_state.tool_df = st.data_editor(st.session_state.tool_df, num_rows="dynamic", key="main_editor")

def get_tool(val):
    clean = str(int(float(val))) if "." in str(val) else str(val)
    res = st.session_state.tool_df[st.session_state.tool_df['MPR_Name'].str.contains(clean, na=False)]
    if not res.empty: return res.iloc[0].to_dict()
    return {"NC_Tool": f"T{clean}", "Diameter": 5.0, "Feed": 2000, "RPM": 4000}

# --- 2. מנוע עיבוד וקטורי (Transformation & Parsing) ---

def parse_mpr_v2(content):
    # חילוץ Workpiece [001]
    size = re.search(r'\[001\s+l="([\d.]+)"\s+.*?w="([\d.]+)"\s+.*?t="([\d.]+)"', content, re.DOTALL)
    if not size: return None, []
    L, W, T = float(size.group(1)), float(size.group(2)), float(size.group(3))
    
    blocks = []
    # Regex גמיש לקידוחים <102
    drill_matches = re.finditer(r'<(102|100)\s+\\BohrVert\\(.*?)(?=<|$)', content, re.DOTALL)
    for m in drill_matches:
        data = m.group(2)
        # חילוץ גמיש (תמיכה ב-XA=55 וגם XA="55")
        xa = re.search(r'XA="?([\d.-]+)"?', data)
        ya = re.search(r'YA="?([\d.-]+)"?', data)
        ti = re.search(r'TI="?([\d.-]+)"?', data)
        du = re.search(r'DU="?([\d.-]+)"?', data)
        an = re.search(r'AN="?([\d.-]+)"?', data)
        ab = re.search(r'AB="?([\d.-]+)"?', data)
        wi = re.search(r'WI="?([\d.-]+)"?', data)
        
        if xa and ya:
            x_mpr, y_mpr = float(xa.group(1)), float(ya.group(1))
            count = int(float(an.group(1))) if an else 1
            dist = float(ab.group(1)) if ab else 0
            angle = math.radians(float(wi.group(1))) if wi else 0
            
            # יצירת סדרה (קבינאו/מדפים)
            for i in range(count):
                curr_x = x_mpr + (i * dist * math.cos(angle))
                curr_y = y_mpr + (i * dist * math.sin(angle))
                
                # חוק סיבוב 90 מעלות CCW
                x_nc = W - curr_y
                y_nc = curr_x
                z_nc = round(T - float(ti.group(1)), 3) if ti else 0
                
                blocks.append({
                    'type': 'Drill', 'tool_mpr': du.group(1) if du else "5",
                    'x': x_nc, 'y': y_nc, 'z': [z_nc],
                    'diam': float(du.group(1)) if du else 5.0
                })

    # כרסומים <105 (סינון ]1)
    mill_matches = re.finditer(r'<(105)\s+\\Konturfraesen\\(.*?)(?=<|$)', content, re.DOTALL)
    for m in mill_matches:
        data = m.group(2)
        za = re.search(r'ZA="?([\d.-]+)"?', data)
        tno = re.search(r'TNO="?([^"]+)"?', data)
        if za:
            z_val = float(za.group(1))
            blocks.append({
                'type': 'Milling', 'tool_mpr': tno.group(1) if tno else "142",
                'x': W/2, 'y': L/2, 'z': [z_val], 'diam': 12.0
            })
            
    return {"L": L, "W": W, "T": T}, blocks

# --- 3. אופטימיזציה (Neighbor & Multi-pass) ---

def optimize_path(blocks):
    if not blocks: return []
    optimized = []
    # איחוד לפי כלי
    by_tool = {}
    for b in blocks:
        t = b['tool_mpr']
        if t not in by_tool: by_tool[t] = []
        by_tool[t].append(b)
    
    curr_pos = (0, 0)
    for tool_name in by_tool:
        tool_group = by_tool[tool_name]
        # השכן הקרוב (Euclidean)
        while tool_group:
            next_b = min(tool_group, key=lambda b: math.sqrt((b['x']-curr_pos[0])**2 + (b['y']-curr_pos[1])**2))
            
            # חוק הניתוק הסופי (Two-pass)
            if any(z < 0.05 for z in next_b['z']):
                final_z = next_b['z'][0]
                next_b['z'] = [2.0, final_z] # Scoring + Cut
            
            optimized.append(next_b)
            curr_pos = (next_b['x'], next_b['y'])
            tool_group.remove(next_b)
            
    return optimized

# --- 4. ממשק והדמיה ---

uploaded = st.file_uploader("📂 טען קובץ MPR", type=['mpr'])
if uploaded:
    content = uploaded.read().decode('utf-8', errors='ignore')
    dims, raw_blocks = parse_mpr_v2(content)
    
    if dims:
        st.success(f"לוח זוהה: {dims['W']}x{dims['L']} (עובי {dims['T']}) מילימטר")
        
        final_list = optimize_path(raw_blocks)
        
        # הדמיה (Shapes & Rulers)
        fig = go.Figure()
        # שולחן
        fig.add_trace(go.Scatter(x=[0, 3000, 3000, 0, 0], y=[0, 0, 1220, 1220, 0], fill="toself", fillcolor="rgba(100,100,100,0.1)", line=dict(color="gray"), name="Table"))
        # פלטה (עוגן 0,0)
        fig.add_trace(go.Scatter(x=[0, dims['W'], dims['W'], 0, 0], y=[0, 0, dims['L'], dims['L'], 0], fill="toself", fillcolor="rgba(139,69,19,0.3)", line=dict(color="brown", width=2), name="Workpiece"))
        
        for b in final_list:
            tool_info = get_tool(b['tool_mpr'])
            r = tool_info['Diameter'] / 2
            color = "green" if b['type'] == 'Drill' else "blue"
            if any(z < 0.05 for z in b['z']): color = "red"
            
            fig.add_shape(type="circle", x0=b['x']-r, y0=b['y']-r, x1=b['x']+r, y1=b['y']+r, line_color=color, fillcolor=color)
            b['nc_tool'] = tool_info['NC_Tool']
            b['feed'] = tool_info['Feed']
            b['rpm'] = tool_info['RPM']

        fig.update_layout(xaxis=dict(range=[-100, 3100], dtick=100), yaxis=dict(range=[-100, 1300], dtick=100), width=1000, height=500, dragmode='pan')
        st.plotly_chart(fig, use_container_width=True)

        # הפקת NC
        if st.button("🛠️ הפק קוד NC"):
            nc = ["%", f"(FILE: {uploaded.name})", "N10 G90 G54 G21 G17"]
            curr_t = None
            l = 20
            for b in final_list:
                if b['nc_tool'] != curr_t:
                    nc.append(f"N{l} M05")
                    nc.append(f"N{l+5} {b['nc_tool']} M06")
                    nc.append(f"N{l+10} S{b['rpm']} M03")
                    curr_t = b['nc_tool']
                    l += 20
                for z_val in b['z']:
                    nc.append(f"N{l} G00 X{b['x']:.3f} Y{b['y']:.3f}")
                    nc.append(f"N{l+5} G01 Z{z_val:.3f} F{b['feed']}")
                    nc.append(f"N{l+10} G00 Z35.0")
                    l += 15
            nc.append("M30\n%")
            st.code("\n".join(nc), language='gcode')
