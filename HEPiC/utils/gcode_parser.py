import re
import numpy as np
import matplotlib.pyplot as plt

def parse_gcode_time_series(gcode):
    # 初始化状态
    current_pos = {'X': 0.0, 'Y': 0.0, 'Z': 0.0, 'E': 0.0}
    current_temp = 0.0  # 初始温度
    current_feedrate = 1000.0 # 默认进给速率 (mm/min)
    
    # 定位模式状态
    is_abs_xyz = True # G90 (True) / G91 (False)
    is_abs_e = True   # M82 (True) / M83 (False)
    
    # 时间序列数据存储
    times = [0.0]
    extrusion_velocities = [0.0]
    temperatures = [0.0]
    
    # 正则表达式用于提取 G-code 参数 (例如: X10.5 Y-20)
    param_pattern = re.compile(r"([XYZEFMS])([-+]?[0-9]*\.?[0-9]*)")
    
    total_time = 0.0

    for line in gcode.split("\n"):
        line = line.split(';')[0].strip() # 去除注释和空格
        if not line:
            continue

        # 解析指令类型
        parts = line.split()
        cmd = parts[0].upper()

        # --- 处理运动指令 (G0, G1) ---
        if cmd in ['G0', 'G1']:
            # 解析参数
            params = dict((m.group(1), float(m.group(2))) for m in param_pattern.finditer(line))
            
            # 更新进给速率 (F)
            if 'F' in params:
                current_feedrate = params['F']
            
            # 计算 XYZ 移动距离
            old_xyz = np.array([current_pos['X'], current_pos['Y'], current_pos['Z']])
            
            # 更新 XYZ 坐标
            for axis in ['X', 'Y', 'Z']:
                if axis in params:
                    val = params[axis]
                    if is_abs_xyz:
                        current_pos[axis] = val
                    else:
                        current_pos[axis] += val
            
            new_xyz = np.array([current_pos['X'], current_pos['Y'], current_pos['Z']])
            dist_xyz = np.linalg.norm(new_xyz - old_xyz)

            # 计算 E (挤出) 移动距离
            delta_e = 0.0
            if 'E' in params:
                val = params['E']
                if is_abs_e:
                    delta_e = val - current_pos['E']
                    current_pos['E'] = val
                else:
                    delta_e = val
                    current_pos['E'] += val # 即使是相对模式也要更新虚拟绝对位置
            
            # 忽略极小的浮点误差
            if dist_xyz < 1e-6 and abs(delta_e) < 1e-6:
                continue

            # --- 计算时间 ---
            # 逻辑：
            # 1. 如果有 XYZ 移动，进给速率 F 作用于 XYZ 矢量长度。
            # 2. 如果只有 E 移动 (回抽/单纯挤出)，进给速率 F 作用于 E 的长度。
            
            if dist_xyz > 1e-6:
                move_dist = dist_xyz
            else:
                move_dist = abs(delta_e)

            # F 是 mm/min，转换为 mm/s
            speed_mm_s = current_feedrate / 60.0
            
            if speed_mm_s > 0:
                dt = move_dist / speed_mm_s
            else:
                dt = 0 

            # 计算挤出速度 (mm/s)
            # 注意：回抽 (Retraction) 会产生负速度
            v_e = delta_e / dt if dt > 0 else 0.0
            
            # --- 记录数据 ---
            # 为了绘制方波图（阶跃变化），我们在变化发生前和发生后都记录点
            times.append(total_time)
            extrusion_velocities.append(v_e) # 这一段开始时的速度
            temperatures.append(current_temp)

            total_time += dt
            
            times.append(total_time)
            extrusion_velocities.append(v_e) # 这一段结束时的速度
            temperatures.append(current_temp)

        # --- 处理温度指令 (M104, M109) ---
        elif cmd in ['M104', 'M109']:
            # M104 S200
            params = dict((m.group(1), float(m.group(2))) for m in param_pattern.finditer(line))
            if 'S' in params:
                # 在温度改变这一刻，记录旧温度结束，新温度开始
                times.append(total_time)
                extrusion_velocities.append(0) # 温度变化通常不伴随移动，或者瞬间发生
                temperatures.append(current_temp)
                
                current_temp = params['S']
                
                times.append(total_time)
                extrusion_velocities.append(0)
                temperatures.append(current_temp)

        # --- 处理定位模式 (G90, G91, M82, M83) ---
        elif cmd == 'G90': 
            is_abs_xyz = True
            is_abs_e = True
        elif cmd == 'G91': 
            is_abs_xyz = False
            is_abs_e = False
        elif cmd == 'M82': is_abs_e = True
        elif cmd == 'M83': is_abs_e = False
        
        # --- 处理位置重置 (G92) ---
        elif cmd == 'G92':
            params = dict((m.group(1), float(m.group(2))) for m in param_pattern.finditer(line))
            for axis, val in params.items():
                if axis in current_pos:
                    current_pos[axis] = val

    return np.array(times), np.array(extrusion_velocities), np.array(temperatures)

# --- 使用示例 ---
# 请将 'test.gcode' 替换为你的实际文件路径
# gcode_file = 'test.gcode' 
# t, ve, temp = parse_gcode_time_series(gcode_file)

# 绘图演示 (仅用于本地测试)
if __name__ == "__main__":
    # 创建一个伪造的 Gcode 内容进行测试
    test_gcode_content = """
    G91
    M104 S200 ; Set Temp
    G1 F100 ; Set speed 20mm/s
    G1 E1 ; Move and Extrude
    G1 F200
    G1 E2 ; Move and Extrude
    G1 F300
    G1 E3 ; Retract (E goes from 2 to 1)
    M104 S210 ; Change Temp
    G1 X30 E3 ; Move and Extrude
    """

    t, ve, temp = parse_gcode_time_series(test_gcode_content)

    fig, ax1 = plt.subplots()

    # 绘制挤出速度
    color = 'tab:red'
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Extrusion Velocity (mm/s)', color=color)
    ax1.plot(t, ve, color=color, label='Extrusion Vel')
    ax1.tick_params(axis='y', labelcolor=color)

    # 绘制温度 (双Y轴)
    ax2 = ax1.twinx() 
    color = 'tab:blue'
    ax2.set_ylabel('Temperature (°C)', color=color)
    ax2.plot(t, temp, color=color, linestyle='--', label='Temperature')
    ax2.tick_params(axis='y', labelcolor=color)

    plt.title("G-code Time Series Analysis")
    plt.show()