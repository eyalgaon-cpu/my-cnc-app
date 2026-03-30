import streamlit as st
import re, os, zipfile
import pandas as pd
from collections import defaultdict
from io import BytesIO

# רשימת הכלים המדויקת לפי תמונת ה-Tool Database של אבי
DEFAULT_TOOLS = [
    {"ID_MPR": "142", "קוטר_ממ": 6.0, "תיאור": "כרסום 6", "T_CNC": "T2"},
    {"ID_MPR": "158", "קוטר_ממ": 8.0, "תיאור": "כרסום 8", "T_CNC": "T3"},
    {"ID_MPR": "128", "קוטר_ממ": 12.0, "תיאור": "כרסום 12", "T_CNC": "T4"},
    {"ID_MPR": "140", "קוטר_ממ": 3.0, "תיאור": "כרסום 3", "T_CNC": "T11"},
    {"ID_MPR": "130", "קוטר_ממ": 0.0, "תיאור": "כרסום 45 מעלות", "T_CNC": "T13"},
    {"ID_MPR": "121", "קוטר_ממ": 5.0, "תיאור": "מקדח 5", "T_CNC": "T44"},
    {"ID_MPR": "149", "קוטר_ממ": 15.0, "תיאור": "מקדח 15", "T_CNC": "T49"},
    {"ID_MPR": "135", "קוטר_ממ": 35.0, "תיאור": "מקדח 35 (צירים)", "T_CNC": "T6"} # תיקון ל-T6 לפי התמונה
]

def convert_logic(mpr_text, tool_df, num_passes, swap_axes, offset):
    id_map = {str(row['ID_MPR']): row['T_CNC'] for _, row in tool_df.iterrows()}
    dia_map = {float(row['קוטר_ממ']): row['T_CNC'] for _, row in tool_df.iterrows() if row['קוטר_ממ'] > 0}
    
    t_match = re.search(r't="([\d.]+)"', mpr_text)
    thickness = float(t_match.group(1)) if t_match else 16.5
    
    geometries = {}
    blocks = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(blocks), 2):
        block_id, content = blocks[i], blocks[i+1]
        pts = []
        for elem in re.split(r'\$E\d+', content):
            x_m, y_m = re.search(r'X=([\d.-]+)', elem), re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m:
                vx, vy = float(x_m.group(1)), float(y_m.group(1))
                pts.append((vy, vx) if swap_axes else (vx, vy))
        geometries[block_id] = pts

    drills_by_tool, millings_by_tool = defaultdict(list), defaultdict(list)
    
    drills = re.findall(r'<102.*?XA="([\d.]+)".*?YA="([\d.]+)".*?TI="([\d.]+)".*?DU="([\d.]+)".*?(?:TNO="(\d+)")?.*?', mpr_text, re.DOTALL)
    for x, y, depth, dia, tno in drills:
        vx, vy = (float(y), float(x)) if swap_axes else (float(x), float(y))
        final_t = id_map.get(tno, dia_map.get(float(dia), "T44"))
        drills_by_tool[final_t].append({'x': vx, 'y': vy, 'depth': float(depth)})

    millings = re.findall(r'<105.*?EA="(\d+):.*?ZA="([\d.-]+)".*?TNO="(\d+)".*?', mpr_text, re.DOTALL)
    for geo_id, za, tno in millings:
        final_t = id_map.get(tno, "T2")
        millings_by_tool[final_t].append({'geo_id': geo_id, 'za': float(za)})

    nc_out, l_num, last_tool = [f"G90 {offset}"], 10, ""
    for t_dict, rpm, feed in [(drills_by_tool, 4000, 2000), (millings_by_tool, 17000, 3000)]:
        for cnc_tool in sorted(t_dict.keys()):
            if cnc_tool != last_tool:
                nc_out.extend([f"N{l_num} {cnc_tool} M06", f"N{l_num+5} G43 H{cnc_tool[1:]} S{rpm} M03"])
                l_num, last_tool = l_num + 10, cnc_tool
            for item in t_dict[cnc_tool]:
                if 'x' in item:
                    z_target = round(thickness - item['depth'], 3)
                    nc_out.extend([f"N{l_num} G00 X{item['x']:.3f} Y{item['y']:.3f}", f"N{l_num+5} G01 Z{z_target:.3f} F{feed}", f"N{l_num+10} G00 Z{thickness + 10:.3f}"])
                    l_num += 15
                else:
                    pts = geometries.get(item['geo_id'])
                    if pts:
                        z_vals = [item['za']] if num_passes != 2 else [2.0, -0.2]
                        for z in z_vals:
                            nc_out.append(f"N{l_num} G00 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}")
                            nc_out.append(f"N{l_num+5} G01 Z{z:.3f} F{feed}")
                            l_num += 10
                            for px, py in pts[1:]:
                                nc_out.append(f"N{l_num} G01 X{px:.3f} Y{py:.3f}")
                                l_num += 5
                            nc_out.append(f"N{l_num} G00 Z{thickness + 10:.3f}")
                            l_num += 10
    nc_out.append(f"N{l_num} M30")
    return "\n".join(nc_out)

st.set_page_config(page_title="Darwish CNC Pro", page_icon="🪚", layout="wide")
st.title("🪚 Darwish CNC Pro - גרסה 14.1")

# Sidebar
st.sidebar.header("🛠️ ניהול כלים (אבי השכן)")
if 'tool_df' not in st.session_state:
    st.session_state.tool_df = pd.DataFrame(DEFAULT_TOOLS)
edited_df = st.sidebar.data_editor(st.session_state.tool_df, num_rows="dynamic")
st.session_state.tool_df = edited_df

st.sidebar.markdown("---")
st.sidebar.header("📁 ניהול פרויקט")
p_name = st.sidebar.text_input("שם פרויקט", "Kitchen")
m_type = st.sidebar.text_input("סוג חומר", "19_Plywood")

# Main
col1, col2 = st.columns([1, 1])
with col1:
    st.subheader("⚙️ הגדרות מכונה")
    swap_axes = st.checkbox("החלף צירים (X ↔ Y)", value=True)
    offset_choice = st.selectbox("נקודת אפס", ["G54", "G55", "G56", "G57"])
    mode = st.radio("שיטה:", ('לפי MPR', '2 פסיעות'))
    uploaded = st.file_uploader("בחר קבצי MPR", accept_multiple_files=True)

with col2:
    st.subheader("👀 תצוגה מקדימה והורדה")
    if uploaded:
        pass_val = 2 if '2 פסיעות' in mode else 0
        if len(uploaded) == 1:
            content = uploaded[0].read().decode('utf-8', errors='ignore')
            res = convert_logic(content, edited_df, pass_val, swap_axes, offset_choice)
            st.code(res, language='gcode')
            st.download_button("📂 הורד קובץ NC", res, uploaded[0].name.replace(".mpr", ".nc"))
        else:
            if st.button("בצע המרה", type="primary"):
                buf = BytesIO()
                with zipfile.ZipFile(buf, 'w') as zf:
                    for f in uploaded:
                        content = f.read().decode('utf-8', errors='ignore')
                        res = convert_logic(content, edited_df, pass_val, swap_axes, offset_choice)
                        zf.writestr(f"{p_name}/{m_type}/{f.name.replace('.mpr', '.nc')}", res)
                st.download_button("📂 הורד ZIP פרויקט", buf.getvalue(), f"{p_name}.zip")
