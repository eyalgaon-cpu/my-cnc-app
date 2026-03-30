import streamlit as st
import re, os, zipfile
from collections import defaultdict
from io import BytesIO

# הגדרות כלים - אבי השכן
AVI_LOGIC = {
    "142": {"name": "כרסום 6 מילימטר", "cnc": "T2"},
    "158": {"name": "כרסום 8 מילימטר", "cnc": "T3"},
    "128": {"name": "כרסום 12 מילימטר", "cnc": "T4"},
    "140": {"name": "כרסום 3 מילימטר", "cnc": "T11"},
    "130": {"name": "כרסום 45 מעלות", "cnc": "T13"},
    "121": {"name": "מקדח 5 מילימטר", "cnc": "T44"},
    "149": {"name": "מקדח 15 מילימטר", "cnc": "T49"}
}

def convert_logic(mpr_text, tool_mapping, num_passes, swap_axes, offset):
    t_match = re.search(r't="([\d.]+)"', mpr_text)
    thickness = float(t_match.group(1)) if t_match else 16.5
    
    geometries = {}
    blocks = re.split(r'\](\d+)', mpr_text)
    for i in range(1, len(blocks), 2):
        block_id, block_content = blocks[i], blocks[i+1]
        pts = []
        elements = re.split(r'\$E\d+', block_content)
        for elem in elements:
            x_m, y_m = re.search(r'X=([\d.-]+)', elem), re.search(r'Y=([\d.-]+)', elem)
            if x_m and y_m:
                vx, vy = float(x_m.group(1)), float(y_m.group(1))
                if swap_axes: pts.append((vy, vx))
                else: pts.append((vx, vy))
        geometries[block_id] = pts

    drills_by_tool, millings_by_tool = defaultdict(list), defaultdict(list)
    drills = re.findall(r'<102.*?XA="([\d.]+)".*?YA="([\d.]+)".*?TI="([\d.]+)".*?(?:TNO="(\d+)")?.*?', mpr_text, re.DOTALL)
    for x, y, depth, tno in drills:
        tno = tno if tno else "121"
        vx, vy = (float(y), float(x)) if swap_axes else (float(x), float(y))
        drills_by_tool[tno].append({'x': vx, 'y': vy, 'depth': float(depth)})

    millings = re.findall(r'<105.*?EA="(\d+):.*?ZA="([\d.-]+)".*?TNO="(\d+)".*?', mpr_text, re.DOTALL)
    for geo_id, za, tno in millings:
        millings_by_tool[tno].append({'geo_id': geo_id, 'za': float(za)})

    nc_out, l_num, last_tool = [f"G90 {offset}"], 10, ""
    
    for t_dict, rpm, feed in [(drills_by_tool, 4000, 2000), (millings_by_tool, 17000, 3000)]:
        for tno in sorted(t_dict.keys()):
            cnc_tool = tool_mapping.get(tno, {"cnc": "T2" if rpm > 5000 else "T44"})["cnc"]
            if cnc_tool != last_tool:
                nc_out.extend([f"N{l_num} {cnc_tool} M06", f"N{l_num+5} G43 H{cnc_tool[1:]} S{rpm} M03"])
                l_num, last_tool = l_num + 10, cnc_tool
            for item in t_dict[tno]:
                if 'x' in item:
                    z_target = round(thickness - item['depth'], 3)
                    nc_out.extend([f"N{l_num} G00 X{item['x']:.3f} Y{item['y']:.3f}", f"N{l_num+5} G01 Z{z_target:.3f} F{feed}", f"N{l_num+10} G00 Z{thickness + 10:.3f}"])
                    l_num += 15
                else:
                    pts = geometries.get(item['geo_id'])
                    if pts:
                        z_lvls = [item['za']] if num_passes != 2 else [2.0, -0.2]
                        for z_val in z_lvls:
                            nc_out.append(f"N{l_num} G00 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}")
                            nc_out.append(f"N{l_num+5} G01 Z{z_val:.3f} F{feed}")
                            l_num += 10
                            for px, py in pts[1:]:
                                nc_out.append(f"N{l_num} G01 X{px:.3f} Y{py:.3f}")
                                l_num += 5
                            nc_out.append(f"N{l_num} G00 Z{thickness + 10:.3f}")
                            l_num += 5
    nc_out.append(f"N{l_num} M30")
    return "\n".join(nc_out)

st.set_page_config(page_title="Darwish CNC Pro", page_icon="🪚")
st.title("🪚 Darwish CNC Pro - גרסה 12.0")

st.sidebar.header("📁 ניהול פרויקט")
p_name = st.sidebar.text_input("שם פרויקט", "Kitchen")
m_type = st.sidebar.text_input("סוג חומר", "16.5_Plywood")

st.subheader("⚙️ הגדרות מכונה")
col_a, col_b = st.columns(2)
with col_a:
    swap_axes = st.checkbox("החלף צירים (X ↔ Y)", value=True)
    offset_choice = st.selectbox("נקודת אפס (Work Offset)", ["G54", "G55", "G56", "G57"])
with col_b:
    mode = st.radio("שיטה:", ('לפי MPR', '2 פסיעות'))

uploaded = st.file_uploader("בחר קבצי MPR", accept_multiple_files=True)

if uploaded:
    pass_val = 2 if '2 פסיעות' in mode else 0
    if len(uploaded) == 1:
        content = uploaded[0].read().decode('utf-8', errors='ignore')
        res = convert_logic(content, AVI_LOGIC, pass_val, swap_axes, offset_choice)
        st.info("תצוגה מקדימה של הקוד:")
        st.code(res, language='gcode')
        st.download_button(f"📂 הורד קובץ NC", res, uploaded[0].name.replace(".mpr", ".nc"))
    else:
        if st.button("בצע המרה והצג תצוגה מקדימה", type="primary"):
            buf = BytesIO()
            with zipfile.ZipFile(buf, 'w') as zf:
                for f in uploaded:
                    content = f.read().decode('utf-8', errors='ignore')
                    res = convert_logic(content, AVI_LOGIC, pass_val, swap_axes, offset_choice)
                    zf.writestr(f"{p_name}/{m_type}/{f.name.replace('.mpr', '.nc')}", res)
            st.success("ההמרה הסתיימה בהצלחה!")
            st.download_button("📂 הורד ZIP פרויקט", buf.getvalue(), f"{p_name}.zip")
