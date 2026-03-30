import streamlit as st
import re, os, zipfile
from collections import defaultdict
from io import BytesIO

# הגדרות כלים סופיות - אבי השכן
AVI_LOGIC = {
    "142": {"name": "כרסום 6 מילימטר", "cnc": "T2"},
    "158": {"name": "כרסום 8 מילימטר", "cnc": "T3"},
    "128": {"name": "כרסום 12 מילימטר", "cnc": "T4"},
    "140": {"name": "כרסום 3 מילימטר", "cnc": "T11"},
    "130": {"name": "כרסום 45 מעלות", "cnc": "T13"},
    "121": {"name": "מקדח 5 מילימטר", "cnc": "T44"},
    "149": {"name": "מקדח 15 מילימטר", "cnc": "T49"}
}

def convert_logic(mpr_text, tool_mapping, num_passes):
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
            if x_m and y_m: pts.append((float(x_m.group(1)), float(y_m.group(1))))
        geometries[block_id] = pts

    drills_by_tool, millings_by_tool = defaultdict(list), defaultdict(list)
    drills = re.findall(r'<102.*?XA="([\d.]+)".*?YA="([\d.]+)".*?TI="([\d.]+)".*?(?:TNO="(\d+)")?.*?', mpr_text, re.DOTALL)
    for x, y, depth, tno in drills:
        tno = tno if tno else "121"
        drills_by_tool[tno].append({'x': float(x), 'y': float(y), 'depth': float(depth)})
    millings = re.findall(r'<105.*?EA="(\d+):.*?ZA="([\d.-]+)".*?TNO="(\d+)".*?', mpr_text, re.DOTALL)
    for geo_id, za, tno in millings:
        millings_by_tool[tno].append({'geo_id': geo_id, 'za': float(za)})

    nc_out, l_num, last_tool = [], 10, ""
    for tno in sorted(drills_by_tool.keys()):
        cnc_tool = tool_mapping.get(tno, {"cnc": "T44"})["cnc"]
        if cnc_tool != last_tool:
            nc_out.extend([f"N{l_num} {cnc_tool} M06", f"N{l_num+10} G43 H{cnc_tool[1:]} S4000 M03"])
            l_num, last_tool = l_num + 20, cnc_tool
        for d in drills_by_tool[tno]:
            z_target = round(thickness - d['depth'], 3)
            nc_out.extend([f"N{l_num} G00 X{d['x']:.3f} Y{d['y']:.3f}", f"N{l_num+10} G01 Z{z_target:.3f} F2000.0", f"N{l_num+20} G00 Z{thickness + 10:.3f}"])
            l_num += 30
    for tno in sorted(millings_by_tool.keys()):
        cnc_tool = tool_mapping.get(tno, {"cnc": "T2"})["cnc"]
        if cnc_tool != last_tool:
            nc_out.extend([f"N{l_num} {cnc_tool} M06", f"N{l_num+10} G43 H{cnc_tool[1:]} S17000 M03"])
            l_num, last_tool = l_num + 20, cnc_tool
        for m in millings_by_tool[tno]:
            pts = geometries.get(m['geo_id'])
            if pts:
                z_levels = [m['za']] if num_passes != 2 else [2.0, -0.2]
                for z_val in z_levels:
                    nc_out.append(f"N{l_num} G00 X{pts[0][0]:.3f} Y{pts[0][1]:.3f}")
                    l_num += 10
                    nc_out.append(f"N{l_num} G01 Z{z_val:.3f} F3000.0")
                    l_num += 10
                    for px, py in pts[1:]:
                        nc_out.append(f"N{l_num} G01 X{px:.3f} Y{py:.3f}")
                        l_num += 10
                    nc_out.append(f"N{l_num} G00 Z{thickness + 10:.3f}")
                    l_num += 10
    nc_out.append(f"N{l_num} M30")
    return "\n".join(nc_out)

st.set_page_config(page_title="Darwish CNC Pro", page_icon="🪚")
st.title("🪚 המרת MPR ל-NC - גרסה 9.0")

# אזור ניהול פרויקט
st.subheader("ארגון פרויקט")
col1, col2 = st.columns(2)
with col1:
    project_name = st.text_input("שם הפרויקט", "פרויקט_חדש")
with col2:
    material_type = st.text_input("סוג חומר", "כללי")

mode = st.radio("שיטת עבודה:", ('לפי MPR', '2 פסיעות (2.0 ומינוס 0.2)'))
pass_val = 2 if '2 פסיעות' in mode else 0

uploaded = st.file_uploader("העלה קבצי MPR", accept_multiple_files=True)

if uploaded:
    if len(uploaded) == 1:
        # טיפול בקובץ בודד - הורדה ישירה
        file = uploaded[0]
        content = file.read().decode('utf-8', errors='ignore')
        nc_content = convert_logic(content, AVI_LOGIC, pass_val)
        nc_name = file.name.replace(".mpr", ".nc")
        st.download_button(f"📂 הורד קובץ {nc_name}", nc_content, nc_name, "text/plain")
    
    else:
        # טיפול בכמה קבצים - ZIP עם מבנה תיקיות
        if st.button("ארוז פרויקט ל-ZIP", type="primary"):
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w') as zip_f:
                for file in uploaded:
                    content = file.read().decode('utf-8', errors='ignore')
                    res = convert_logic(content, AVI_LOGIC, pass_val)
                    # יצירת נתיב בתוך ה-ZIP: שם פרויקט / חומר / קובץ
                    path_in_zip = f"{project_name}/{material_type}/{file.name.replace('.mpr', '.nc')}"
                    zip_f.writestr(path_in_zip, res)
            
            st.download_button("📂 הורד ZIP פרויקט מסודר", zip_buffer.getvalue(), f"{project_name}.zip")
