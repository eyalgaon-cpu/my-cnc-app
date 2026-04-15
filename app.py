import streamlit as st
import re, math
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# Darwish 47.0 - SOFTWARE OFFSET PRODUCTION (G40 MODE)
st.set_page_config(page_title="Darwish 47.0 Production", layout="wide")

# --- 1. מסד נתוני כלים (Tool Database) ---
if 'tool_db' not in st.session_state:
    # נתונים סופיים שחולצו מה-VCarve של אבי
    st.session_state.tool_db = pd.DataFrame([
        {"T_CNC": "T1", "קוטר": 40.0, "RPM": 18000, "Feed": 12000, "תיאור": "Surfacing"},
        {"T_CNC": "T2", "קוטר": 6.0, "RPM": 18000, "Feed": 4500, "תיאור": "End Mill 6mm"},
        {"T_CNC": "T3", "קוטר": 8.0, "RPM": 18000, "Feed": 4500, "תיאור": "End Mill 8mm"},
        {"T_CNC": "T4", "קוטר": 12.0, "RPM": 18000, "Feed": 5000, "תיאור": "End Mill 12mm"},
        {"T_CNC": "T11", "קוטר": 3.0, "RPM": 18000, "Feed": 2500, "תיאור": "Detail Mill"},
        {"T_CNC": "T44", "קוטר": 5.0, "RPM": 4500, "Feed": 1200, "תיאור": "Drill 5mm"}
    ])

# --- 2. מנוע גאומטרי: Software Offset (G40 Engine) ---
def offset_polyline(points, r):
    """חישוב מסלול מקביל (Offset) עבור פוליגון פתוח/סגור"""
    if r == 0: return points
    pts = np.array(points)
    new_pts = []
    for i in range(len(pts)):
        # חישוב וקטור כיוון
        if i < len(pts) - 1:
            v = pts[i+1] - pts[i]
        else:
            v = pts[i] - pts[i-1]
        
        mag = np.linalg.norm(v)
        if mag == 0: continue
        
        # וקטור נורמל (צידוד שמאלה - G41 Logic)
        n = np.array([-v[1], v[0]]) / mag
        new_pts.append(pts[i] + n * r)
        
        if i == len(pts) - 1: # נקודה אחרונה
            new_pts.append(pts[i+1] + n * r if i < len(pts)-1 else pts[i] + n * r)
            
    return np.unique(np.array(new_pts), axis=0).tolist()

def clean_txt(s): return str(s).replace("\r", "").replace("\n", "").strip()
def get_f(key, block, default=0.0):
    m = re.search(f'{key}="([^"]*)"', block)
    return float(clean_txt(m.group(1))) if m else default

# --- 3. ממשק משתמש (Tabs) ---
tab_tools, tab_prod = st.tabs(["🛠️ מסד נתוני כלים", "🏭 מרכז ייצור דרוויש"])

with tab_tools:
    st.subheader("כיול כלים (כולל השחזות)")
    st.session_state.tool_db = st.data_editor(st.session_state.tool_db, num_rows="dynamic")
    st.info("💡 כאן ניתן לעדכן את הקוטר המדויק (למשל 5.8 במקום 6.0) והאפליקציה תחשב את האופסט בהתאם.")

with tab_prod:
    col_settings, col_upload = st.columns([1, 2])
    
    with col_settings:
        st.subheader("הגדרות פלטה")
        rotate_90 = st.checkbox("סובב חלק 90 מעלות", value=True)
        user_off_x = st.number_input("הרחקה נוספת X (מעבר ל-MPR)", value=0.0)
        user_off_y = st.number_input("הרחקה נוספת Y (מעבר ל-MPR)", value=0.0)
        ramp_len = st.slider("אורך נחיתה (Ramp) במילימטר", 0, 50, 20)

    with col_upload:
        upl = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)

    if upl:
        for f in upl:
            mpr_text = f.getvalue().decode('utf-8', errors='ignore')
            thickness = get_f('t', mpr_text, 19.0)
            
            # --- שלב א: חילוץ גאומטריות ---
            geometries = {}
            sections = re.split(r'\](\d+)', mpr_text)
            for i in range(1, len(sections), 2):
                pts = []
                for element in re.split(r'\$E\d+', sections[i+1]):
                    x_m, y_m = re.search(r'X=([\d.-]+)', element), re.search(r'Y=([\d.-]+)', element)
                    if x_m and y_m:
                        xv, yv = float(x_m.group(1)), float(y_m.group(1))
                        pts.append([yv, xv] if rotate_90 else [xv, yv])
                if pts: geometries[sections[i]] = pts

            # --- שלב ב: ניתוח פעולות (Internal / Final) ---
            drills, mills_internal, mills_final = [], [], []
            
            # סריקת פעולות כרסום (<105, <130, <181)
            for m_match in re.finditer(r'<(105|130|181)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
                bc, tag = m_match.group(2), m_match.group(1)
                t_mpr = clean_txt(re.search(r'(?:TNO|T_)="([^"]*)"', bc).group(1)) if re.search(r'(?:TNO|T_)="([^"]*)"', bc) else "142"
                ti_val = get_f('TI', bc) if tag == '181' else get_f('ZA', bc)
                z_abs = round((thickness - ti_val if tag == '181' else ti_val), 3)
                geoid = clean_txt(re.search(r'EA="(\d+):', bc).group(1)) if re.search(r'EA="(\d+):', bc) else None
                
                if geoid in geometries:
                    data = {'t': t_mpr, 'z': z_abs, 'pts': geometries[geoid], 'id': geoid}
                    if z_abs <= 0.1: # חיתוך שעובר את הפלטה
                        mills_final.append(data)
                    else:
                        mills_internal.append(data)

            # --- שלב ג: תצוגת בלוקים ועריכה ---
            st.write(f"### 📋 ניהול בלוקים: {f.name}")
            
            final_nc_parts = ["%", f"(DARWISH 47.0 PRODUCTION - {f.name})", "G90 G54 G21"]
            line_n = 10

            def add_n(cmd): nonlocal line_n; r = f"N{line_n} {cmd}"; line_n += 10; return r

            # סדר כלים: קודם אינטרנל, בסוף פיינל
            all_ops = mills_internal + mills_final
            unique_tools = list(set([o['t'] for o in all_ops]))
            
            for t_code in unique_tools:
                # מציאת הגדרות כלי מה-DB שלנו
                tool_row = st.session_state.tool_db[st.session_state.tool_db['T_CNC'].str.contains(t_code, na=False)]
                if tool_row.empty: tool_row = st.session_state.tool_db[st.session_state.tool_db['T_CNC'] == "T2"]
                
                t_cnc = tool_row.iloc[0]['T_CNC']
                t_radius = tool_row.iloc[0]['קוטר'] / 2
                t_feed = tool_row.iloc[0]['Feed']
                t_rpm = tool_row.iloc[0]['RPM']

                final_nc_parts.extend([
                    add_n("M05"),
                    add_n(f"{t_cnc} M06"),
                    add_n(f"G43 H{t_cnc.replace('T','')}"),
                    add_n(f"S{int(t_rpm)} M03")
                ])

                # ביצוע אופסט וקידוד
                ops_for_tool = [o for o in all_ops if o['t'] == t_code]
                for op in ops_for_tool:
                    # חישוב אופסט תוכנה (G40)
                    offset_pts = offset_polyline(op['pts'], t_radius)
                    
                    # נחיתה (Ramp)
                    start_p = offset_pts[0]
                    final_nc_parts.append(add_n(f"G00 X{start_p[0] + user_off_x - ramp_len:.3f} Y{start_p[1] + user_off_y:.3f}"))
                    final_nc_parts.append(add_n(f"G01 Z{op['z']:.3f} X{start_p[0] + user_off_x:.3f} F2000"))
                    
                    for p in offset_pts[1:]:
                        final_nc_parts.append(add_n(f"G01 X{p[0] + user_off_x:.3f} Y{p[1] + user_off_y:.3f} F{int(t_feed)}"))
                    
                    final_nc_parts.extend([add_n("G00 Z36.0")])

            final_nc_parts.extend(["M05", "M30", "M200", "%"])
            nc_string = "\n".join(final_nc_parts)

            # --- שלב ד: ויזואליזציה (Plotly) ---
            fig = go.Figure()
            for op in all_ops:
                # ציור מסלול מקורי (אפור) ומסלול אופסט (צבעוני)
                orig_x, orig_y = zip(*op['pts'])
                fig.add_trace(go.Scatter(x=orig_x, y=orig_y, mode='lines', line=dict(dash='dash', color='gray'), name="Original"))
                
                tool_row = st.session_state.tool_db[st.session_state.tool_db['T_CNC'].str.contains(op['t'], na=False)]
                r = (tool_row.iloc[0]['קוטר'] / 2) if not tool_row.empty else 3.0
                off_pts = offset_polyline(op['pts'], r)
                off_x, off_y = zip(*off_pts)
                fig.add_trace(go.Scatter(x=off_x, y=off_y, mode='lines', name=f"Offset {op['t']}"))

            fig.update_layout(title=f"תצוגת מסלול מחושב (G40): {f.name}", width=800, height=600)
            st.plotly_chart(fig)
            
            st.download_button(f"📥 הורד NC (גרסה 47.0)", nc_string, f.name.replace(".mpr", ".nc"))
