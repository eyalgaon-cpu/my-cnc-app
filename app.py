import streamlit as st
import re, os
import pandas as pd
import math
import plotly.graph_objects as go

# הגדרות דף
st.set_page_config(page_title="Darwish CNC Pro 41.0", layout="wide")

# מודול ניהול פרופילי מכונות
if 'profiles' not in st.session_state:
    st.session_state.profiles = {
        "אבי": [
            {"קוטר": 6.0, "תיאור": "כרסום 6", "T_CNC": "T2", "צבע": "red", "תיקון_Z": 0.0},
            {"קוטר": 8.0, "תיאור": "מקדח 8", "T_CNC": "T47", "צבע": "green", "תיקון_Z": -1.0},
            {"קוטר": 10.0, "תיאור": "מקדח 10", "T_CNC": "T46", "צבע": "blue", "תיקון_Z": -0.5},
            {"קוטר": 15.0, "תיאור": "מקדח 15", "T_CNC": "T49", "צבע": "cyan", "תיקון_Z": 0.0},
            {"קוטר": 35.0, "תיאור": "מקדח 35", "T_CNC": "T6", "צבע": "orange", "תיקון_Z": -0.1}
        ],
        "מושיקו": [
            {"קוטר": 12.0, "תיאור": "כרסום 12", "T_CNC": "T10", "צבע": "purple", "תיקון_Z": 0.0},
            {"קוטר": 5.0, "תיאור": "מקדח 5", "T_CNC": "T101", "צבע": "yellow", "תיקון_Z": 0.0}
        ]
    }

if 'current_machine' not in st.session_state:
    st.session_state.current_machine = "אבי"

def get_safe_float(key, block, default=0.0):
    match = re.search(f'{key}="([^"]*)"', block)
    if not match: return default
    try: return float(match.group(1))
    except:
        nums = re.findall(r'[\d.-]+', match.group(1))
        return float(nums[0]) if nums else default

def convert_logic(mpr_text, tool_df, rotate_90, zero_nesting, margin_x, margin_y, global_z_off):
    dia_map = {round(float(row['קוטר']), 1): row for _, row in tool_df.iterrows()}
    thickness = get_safe_float('t', mpr_text, 19.0)
    
    # סריקה עמוקה לזיהוי כרסום (בלוקים 101, 130, 131)
    contour_tool = "לא זוהה"
    passes = []
    # חיפוש רחב בכל סוגי בלוקי העיבוד
    contour_match = re.search(r'<(130|131|101|133)(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL)
    if contour_match:
        c_block = contour_match.group(2)
        # ניסיון לשלוף קוטר ממספר פרמטרים אפשריים ב-MPR
        c_dia = max(get_safe_float('DU', c_block), get_safe_float('DI', c_block), get_safe_float('D', c_block))
        ti_total = max(get_safe_float('TI', c_block), get_safe_float('T', c_block))
        
        if c_dia > 0:
            contour_tool = f"כרסום {c_dia:.0f}"
        else:
            # אם לא נמצא קוטר מספרי, חיפוש שם כלי (Tool Name)
            t_name = re.search(r'T_CNC="([^"]*)"', c_block)
            contour_tool = t_name.group(1) if t_name else "כרסום לא מוגדר"
            
        if ti_total > 0:
            passes = [f"{ti_total/2:.2f} מילימטר", f"{ti_total + 2.0:.2f} מילימטר"]

    geos = {}
    parts = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(parts), 2):
        bid, content = parts[i], parts[i+1]
        pts = []
        for elem in re.split(r'\$E\d+', content):
            x_m, y_m = re.search(r'X=([\d.-]+)', elem), re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m: pts.append([float(x_m.group(1)), float(y_m.group(1))])
        if pts: geos[bid] = pts

    raw_drills = []
    for m in re.finditer(r'<102(.*?)(?=<|\!|\[H)', mpr_text, re.DOTALL):
        b = m.group(1)
        xa, ya, ti, du = [get_safe_float(k, b) for k in ['XA', 'YA', 'TI', 'DU']]
        conf = dia_map.get(round(du, 1))
        if conf is None: continue
        # לוגיקת Z: פלוס מרחיק מהשולחן (רדוד), מינוס מקרב לשולחן (עמוק)
        f_z = (thickness - ti) + global_z_off - conf.get("תיקון_Z", 0.0)
        raw_drills.append({
            'x': xa, 'y': ya, 'z': f_z, 't': conf['T_CNC'], 'desc': conf['תיאור'], 'dia': du, 'color': conf['צבע']
        })

    # סיבוב ונסטינג
    if rotate_90:
        for d in raw_drills: d['x'], d['y'] = -d['y'], d['x']
        for pts in geos.values():
            for p in pts: p[0], p[1] = -p[1], p[0]

    all_x = [d['x'] for d in raw_drills] + [p[0] for pts in geos.values() for p in pts]
    all_y = [d['y'] for d in raw_drills] + [p[1] for pts in geos.values() for p in pts]
    dx, dy = 0.0, 0.0
    if all_x and all_y:
        min_x, min_y = min(all_x), min(all_y)
        if zero_nesting:
            for d in raw_drills: d['x'] -= min_x; d['y'] -= min_y
            for pts in geos.values():
                for p in pts: p[0] -= min_x; p[1] -= min_y
        else:
            shift_x = abs(min_x) if min_x < 0 else 0
            shift_y = abs(min_y) if min_y < 0 else 0
            for d in raw_drills: d['x'] += shift_x; d['y'] += shift_y
            for pts in geos.values():
                for p in pts: p[0] += shift_x; p[1] += shift_y
        
        final_x = [d['x'] for d in raw_drills] + [p[0] for pts in geos.values() for p in pts]
        final_y = [d['y'] for d in raw_drills] + [p[1] for pts in geos.values() for p in pts]
        dx, dy = max(final_x) - min(final_x), max(final_y) - min(final_y)

    for d in raw_drills:
        d['x'] += margin_x; d['y'] += margin_y
    for pts in geos.values():
        for p in pts: p[0] += margin_x; p[1] += margin_y

    nc, ln, last_t = [f"G90 G54"], 10, ""
    for t_name in sorted(list(set(d['t'] for d in raw_drills))):
        subset = [dr for dr in raw_drills if dr['t']==t_name]
        for d in subset:
            if d['t'] != last_t:
                nc.extend([f"N{ln} {d['t']} M06", f"N{ln+5} G43 H{d['t'][1:]} S4000 M03"])
                ln, last_t = ln + 10, d['t']
            nc.extend([f"N{ln} G00 X{d['x']:.3f} Y{d['y']:.3f}", f"N{ln+5} G01 Z{d['z']:.3f} F2000", f"N{ln+10} G00 Z{thickness+10:.3f}"])
            ln += 15
    return "\n".join(nc), raw_drills, geos, thickness, dx, dy, contour_tool, passes

def plot_2d_pro(drills, geos, thickness, dx, dy, contour_tool, passes, filename):
    st.markdown(f"### 📄 קובץ: {filename}")
    c1, c2 = st.columns(2)
    c1.info(f"📏 **מידות:** {dx:.2f} × {dy:.2f} מילימטר | עובי: {thickness:.2f} מילימטר")
    c2.warning(f"🪚 **קונטור:** {contour_tool} | פסיעות: {' ← '.join(passes) if passes else 'לא הוגדרו'}")
    
    fig = go.Figure()
    fig.add_shape(type="rect", x0=0, y0=0, x1=1300, y1=3050, fillcolor="whitesmoke", line=dict(color="black", width=2), layer="below")
    
    for bid, pts in geos.items():
        if len(pts) > 1:
            x_p, y_p = zip(*pts)
            c_dx, c_dy = max(x_p) - min(x_p), max(y_p) - min(y_p)
            fig.add_trace(go.Scatter(
                x=x_p, y=y_p, mode='lines', line=dict(color='red', width=2),
                name=f"קונטור {bid}",
                text=f"חלק: {c_dx:.2f} × {c_dy:.2f} מילימטר",
                hoverinfo="text+name"
            ))

    for d in drills:
        actual_depth = thickness - d['z']
        fig.add_trace(go.Scatter(
            x=[d['x']], y=[d['y']], mode='markers',
            marker=dict(size=d['dia'], color=d['color'], line=dict(width=1, color='black')),
            text=[d['desc']], 
            customdata=[[d['t'], actual_depth]],
            hovertemplate=(
                "<span style='font-size:16px;'><b>%{customdata[0]}</b></span><br>"
                "כלי: %{text}<br>"
                "עומק: %{customdata[1]:.2f} מילימטר<extra></extra>"
            )
        ))

    fig.update_xaxes(title="ציר X (מילימטר)", range=[-100, 1400], gridcolor='rgba(0,0,0,0.1)', showline=True, mirror=True)
    fig.update_yaxes(title="ציר Y (מילימטר)", range=[-100, 3150], gridcolor='rgba(0,0,0,0.1)', scaleanchor="x", scaleratio=1, showline=True, mirror=True)
    fig.update_layout(width=900, height=850, template="plotly_white", showlegend=False, hoverlabel=dict(bgcolor="white", font_size=14))
    st.plotly_chart(fig, use_container_width=True)

# Sidebar - הגדרות ותפעול
st.sidebar.title("🛠️ ממשק דרוויש 41.0")

# בורר מכונות
machine_names = list(st.session_state.profiles.keys())
selected_machine = st.sidebar.selectbox("בחר מכונה (פרופיל):", machine_names, index=machine_names.index(st.session_state.current_machine))
st.session_state.current_machine = selected_machine

st.sidebar.markdown("---")
nest = st.sidebar.checkbox("צמד לפינה (Nesting)", value=True)
rot = st.sidebar.checkbox("סובב Portrait (90°)", value=True)
gz_off = st.sidebar.slider("כיול Z גלובלי (מילימטר)", -5.0, 5.0, 0.0, 0.1)
mx = st.sidebar.number_input("מרג'ין X (מילימטר)", value=0.0)
my = st.sidebar.number_input("מרג'ין Y (מילימטר)", value=0.0)

# עריכת כלים וניהול פרופילים
st.markdown(f"### 🧰 הגדרות מכונה: {st.session_state.current_machine}")
with st.expander("ערוך רשימת כלים וכיולים למכונה זו"):
    current_tools = st.session_state.profiles[st.session_state.current_machine]
    edited_df = st.data_editor(pd.DataFrame(current_tools), num_rows="dynamic")
    
    col_a, col_b = st.columns(2)
    if col_a.button("שמור שינויים למכונה הנוכחית"):
        st.session_state.profiles[st.session_state.current_machine] = edited_df.to_dict('records')
        st.success(f"הגדרות המכונה '{st.session_state.current_machine}' נשמרו.")
    
    new_machine_name = col_b.text_input("שם מכונה חדשה לשמירה:", value="")
    if col_b.button("שמור כמכונה חדשה"):
        if new_machine_name:
            st.session_state.profiles[new_machine_name] = edited_df.to_dict('records')
            st.session_state.current_machine = new_machine_name
            st.rerun()

uploaded = st.file_uploader("טען קבצי MPR", accept_multiple_files=True)
if uploaded:
    for f in uploaded:
        nc, drills, geos, thick, dx, dy, c_tool, pss = convert_logic(
            f.getvalue().decode('utf-8', errors='ignore'), 
            pd.DataFrame(st.session_state.profiles[st.session_state.current_machine]), 
            rot, nest, mx, my, gz_off
        )
        plot_2d_pro(drills, geos, thick, dx, dy, c_tool, pss, f.name)
        st.download_button(f"📂 הורד NC עבור {st.session_state.current_machine}", nc, f.name.replace(".mpr", f"_{st.session_state.current_machine}.nc"))
