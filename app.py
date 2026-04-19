import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import re
import math

# --- חוק יסוד: פרוטוקול דרוויש 2026 - גרסה 48.19 ---
# סטטוס: Industrial Foundation Fix
# מטרה: שחזור לוגיקה מלאה, סיבוב 90 מעלות, ניהול פסיעות, וסרגלים אינטראקטיביים.

st.set_page_config(page_title="Darwish CNC 2026 - V48.19", layout="wide")

# כותרת גרסה קבועה
st.markdown(f"<h1 style='text-align: center; color: #1E88E5;'>🚀 Darwish CNC Pro - Version 48.19</h1>", unsafe_allow_html=True)

# --- 1. מסד כלים (Expander מתקפל - חוק יסוד) ---
with st.expander("🛠️ הגדרות מסד כלים (Tool Database)", expanded=False):
    if 'tool_df' not in st.session_state:
        # נתוני עוגן - טבלת הכלים של אבי
        data = {
            "MPR_Name": ["5.0", "8.0", "15.0", "35.0", "142", "6.0"],
            "NC_Tool": ["T44", "T47", "T49", "T6", "T2", "T10"],
            "Diameter": [5.0, 8.0, 15.0, 35.0, 12.0, 6.0],
            "Type": ["Drill", "Drill", "Drill", "Drill", "Milling", "Milling"],
            "Feed": [2000, 2000, 2000, 2000, 4000, 3500],
            "RPM": [4500, 4500, 4500, 4500, 18000, 16000]
        }
        st.session_state.tool_df = pd.DataFrame(data)
    
    edited_df = st.data_editor(st.session_state.tool_df, num_rows="dynamic", key="main_tool_editor")
    st.session_state.tool_df = edited_df

def get_tool_info(mpr_val):
    try:
        # ניקוי שם כלי (הסרת .00000)
        clean_name = str(int(float(mpr_val))) if "." in str(mpr_val) else str(mpr_val)
    except:
        clean_name = str(mpr_val)
    
    res = st.session_state.tool_df[st.session_state.tool_df['MPR_Name'].str.contains(clean_name, na=False)]
    if not res.empty:
        return res.iloc[0].to_dict()
    return {"NC_Tool": f"T{clean_name}", "Diameter": 5.0, "Type": "Unknown", "Feed": 2000, "RPM": 4000}

# --- 2. מנוע טרנספורמציה ועיבוד MPR ---

def parse_mpr_full(content):
    # חילוץ מידות לוח (Workpiece) - בלוק 001
    size_match = re.search(r'\[001\s+l="([\d.]+)"\s+.*?w="([\d.]+)"\s+.*?t="([\d.]+)"', content, re.DOTALL)
    if not size_match:
        return None, []
    
    L_orig = float(size_match.group(1)) # אורך מקורי (X ב-MPR)
    W_orig = float(size_match.group(2)) # רוחב מקורי (Y ב-MPR)
    T = float(size_match.group(3))      # עובי
    
    # חוק עוגן: הפלטה הופכת להיות W_orig ב-X ו-L_orig ב-Y אחרי סיבוב 90 מעלות
    dims = {"L": L_orig, "W": W_orig, "T": T}
    
    blocks = []
    
    # חיפוש קדחים (100/102) - סינון קפדני למניעת קדחי רפאים
    drill_pattern = re.compile(r'<(100|102)\s+\\BohrVert\\(.*?)(?=<|$)', re.DOTALL)
    for match in drill_pattern.finditer(content):
        data = match.group(2)
        xa = re.search(r'XA="([\d.-]+)"', data)
        ya = re.search(r'YA="([\d.-]+)"', data)
        ti = re.search(r'TI="([\d.-]+)"', data)
        du = re.search(r'DU="([\d.-]+)"', data)
        
        if xa and ya:
            x_mpr, y_mpr = float(xa.group(1)), float(ya.group(1))
            # חוק עוגן: סיבוב 90 מעלות CCW
            x_nc = W_orig - y_mpr
            y_nc = x_mpr
            z_nc = round(T - float(ti.group(1)), 3) if ti else 0
            
            blocks.append({
                'id': len(blocks),
                'type': 'Drill',
                'mpr_tool': du.group(1) if du else "5",
                'x': x_nc, 'y': y_nc,
                'z_levels': [z_nc],
                'is_final': False
            })

    # חיפוש כרסומים (105)
    mill_pattern = re.compile(r'<(105)\s+\\Konturfraesen\\(.*?)(?=<|$)', re.DOTALL)
    for match in mill_pattern.finditer(content):
        data = match.group(2)
        za = re.search(r'ZA="([\d.-]+)"', data)
        tno = re.search(r'TNO="([^"]+)"', data)
        
        # כאן תיושם בעתיד לוגיקת מסלול מלאה. כרגע מדגימים מיקום מרכזי.
        if za:
            z_val = float(za.group(1))
            blocks.append({
                'id': len(blocks),
                'type': 'Milling',
                'mpr_tool': tno.group(1) if tno else "142",
                'x': W_orig / 2, 'y': L_orig / 2, # פלייסהולדר למרכז
                'z_levels': [z_val],
                'is_final': True if z_val < 0.05 else False
            })
            
    return dims, blocks

# --- 3. ממשק משתמש וניהול פסיעות (Multi-pass) ---

uploaded_file = st.file_uploader("📂 העלה קובץ MPR לעיבוד", type=['mpr'])

if uploaded_file:
    content = uploaded_file.read().decode('utf-8', errors='ignore')
    dims, blocks = parse_mpr_full(content)
    
    if dims:
        st.info(f"✅ לוח זוהה: אורך {dims['L']}, רוחב {dims['W']}, עובי {dims['T']} מילימטר")
        
        processed_blocks = []
        st.subheader("⚙️ ניהול פסיעות וסדר פעולות")
        
        # תצוגת בלוקים לעריכה
        for i, b in enumerate(blocks):
            tool = get_tool_info(b['mpr_tool'])
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
                c1.write(f"**#{i+1}**")
                c2.write(f"**{b['type']}: {tool['NC_Tool']}** (Ø{tool['Diameter']})")
                
                new_z_levels = []
                for idx, z in enumerate(b['z_levels']):
                    active = c3.checkbox(f"פסיעה {idx+1}", value=True, key=f"act_{i}_{idx}")
                    depth = c4.number_input("עומק Z", value=z, key=f"z_{i}_{idx}", step=0.1)
                    if active:
                        new_z_levels.append(depth)
                
                if new_z_levels:
                    b['z_levels'] = new_z_levels
                    b['nc_tool'] = tool['NC_Tool']
                    b['feed'] = tool['Feed']
                    b['rpm'] = tool['RPM']
                    b['diam'] = tool['Diameter']
                    processed_blocks.append(b)

        # חוק עוגן: איחוד בלוקים ומיון חיתוך סופי לסוף
        processed_blocks.sort(key=lambda x: 1 if x['is_final'] else 0)

        # --- 4. ויזואליזציה אינטראקטיבית (Interactive Rulers & True Circles) ---
        st.subheader("🔍 הדמיית ייצור")
        
        fig = go.Figure()
        
        # שולחן המכונה (אפור) - 3000x1220 מילימטר
        fig.add_trace(go.Scatter(
            x=[0, 3000, 3000, 0, 0], y=[0, 0, 1220, 1220, 0],
            fill="toself", fillcolor="rgba(180, 180, 180, 0.2)",
            line=dict(color="gray", width=1), name="Table", hoverinfo='skip'
        ))
        
        # הפלטה (חום) - חוק עוגן: מקשה אחת מיושרת ל-0,0
        fig.add_trace(go.Scatter(
            x=[0, dims['W'], dims['W'], 0, 0], y=[0, 0, dims['L'], dims['L'], 0],
            fill="toself", fillcolor="rgba(139, 69, 19, 0.4)",
            line=dict(color="#5D4037", width=3), name="Workpiece"
        ))
        
        # ציור אלמנטים (עיגולים אמיתיים)
        for b in processed_blocks:
            color = "green" if b['type'] == 'Drill' else "blue"
            if b['is_final']: color = "red"
            
            radius = b['diam'] / 2
            # ציור עיגול (Shape) במיקום המדויק
            fig.add_shape(type="circle",
                xref="x", yref="y",
                x0=b['x'] - radius, y0=b['y'] - radius,
                x1=b['x'] + radius, y1=b['y'] + radius,
                line_color=color, fillcolor=color, opacity=0.6
            )
            # נקודת מרכז ל-Tooltip
            fig.add_trace(go.Scatter(
                x=[b['x']], y=[b['y']], mode='markers',
                marker=dict(size=4, color="white"),
                hovertext=f"כלי: {b['nc_tool']}<br>קוטר: {b['diam']}<br>Z: {b['z_levels']}",
                name=b['nc_tool']
            ))

        # סרגלי מידות אינטראקטיביים (חוק יסוד)
        fig.update_layout(
            xaxis=dict(title="X Axis (מילימטר)", range=[-100, 3100], dtick=100, gridcolor='lightgray', zerolinecolor='black'),
            yaxis=dict(title="Y Axis (מילימטר)", range=[-100, 1300], dtick=100, gridcolor='lightgray', zerolinecolor='black'),
            width=1100, height=600, plot_bgcolor='white', showlegend=False, dragmode='pan'
        )
        st.plotly_chart(fig, use_container_width=True)

        # --- 5. מחולל NC (G-Code Generator) ---
        if st.button("🛠️ הפק קובץ NC סופי"):
            nc = []
            nc.append("%")
            nc.append(f"(FILENAME: {uploaded_file.name} - DARWISH V48.19)")
            nc.append("N10 G90 G54 G21 G17") # חוק עוגן: קואורדינטות מוחלטות, מילימטר
            
            curr_tool = None
            line = 20
            
            for b in processed_blocks:
                if b['nc_tool'] != curr_tool:
                    nc.append(f"N{line} M05")
                    nc.append(f"N{line+5} {b['nc_tool']} M06")
                    nc.append(f"N{line+10} G43 H{b['nc_tool'][1:]} S{b['rpm']} M03")
                    curr_tool = b['nc_tool']
                    line += 20
                
                # ביצוע פסיעות (Multi-pass loop)
                for z_depth in b['z_levels']:
                    nc.append(f"N{line} G00 X{b['x']:.3f} Y{b['y']:.3f}")
                    nc.append(f"N{line+5} G01 Z{z_depth:.3f} F{b['feed']}")
                    nc.append(f"N{line+10} G00 Z35.0") # גובה בטיחות
                    line += 15
            
            nc.append(f"N{line} M30")
            nc.append("%")
            
            nc_string = "\\n".join(nc)
            st.download_button("💾 הורד קובץ NC לייצור", nc_string, file_name=f"{uploaded_file.name}.nc")
            st.code(nc_string, language='gcode')
else:
    st.warning("⚠️ ממתין להעלאת קובץ MPR...")
