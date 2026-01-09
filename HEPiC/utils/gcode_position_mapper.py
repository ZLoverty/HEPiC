import time
import bisect
import logging

class GcodePositionMapper:
    """
    此类用于将 Klipper 的 file_position (字节偏移量)
    高效地映射回 G-code 文件的行号。
    """
    
    def __init__(self, gcode_content: str):
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("正在构建 G-code 字节偏移量映射表...")
        self.gcode_content = gcode_content
        # self.line_start_offsets 存储 *每一行* 的 *起始字节偏移量*
        # 列表的索引 0 对应行号 1, 索引 1 对应行号 2...
        self.line_start_offsets = []
        self.total_lines = 0
        
        self._build_map()
        self.logger.info(f"映射表构建完毕。总行数: {self.total_lines}, 总字节: {self.total_bytes}")

    def _build_map(self):
        """
        遍历 G-code 字符串，填充 line_start_offsets 列表。
        必须按“字节”计算，而不是“字符”。
        """
        current_byte_offset = 0
        
        # 我们按行分割字符串，保留换行符
        for line in self.gcode_content.splitlines(True):
            # 将此行的起始字节偏移量添加到列表中
            self.line_start_offsets.append(current_byte_offset)
            
            # 计算此行（包括 \n）的 *字节* 长度，并累加
            # Klipper (Python 3) 默认使用 UTF-8
            current_byte_offset += len(line.encode('utf-8'))
        
        self.total_lines = len(self.line_start_offsets)
        self.total_bytes = current_byte_offset

    def get_line_number(self, target_byte_position: int) -> int:
        """
        使用二分查找 (bisect) 来高效地找到对应的行号。
        
        bisect_right 在排序列表中找到一个插入点，该插入点
        位于所有小于或等于 target_byte_position 的条目之后。
        
        这完美地对应了我们的需求：
        - offsets = [0, 10, 25] (第1行在0, 第2行在10, 第3行在25)
        - target = 0  -> bisect_right(offsets, 0)  -> 1 (第1行)
        - target = 9  -> bisect_right(offsets, 9)  -> 1 (第1行)
        - target = 10 -> bisect_right(offsets, 10) -> 2 (第2行)
        - target = 26 -> bisect_right(offsets, 26) -> 3 (第3行)
        
        返回的是 1-based 的行号。
        """
        if target_byte_position < 0:
            return 1
            
        # bisect_right 返回的是 1-based 的索引（即行号）
        line_number = bisect.bisect_right(self.line_start_offsets, target_byte_position)
        
        # 确保不会返回一个不存在的行号（例如，如果 Klipper 报告的位置 > 文件总字节）
        return min(line_number, self.total_lines)
    

def _test_gcode_mapper():
    # --- 演示如何使用 ---

    # 1. 假设这是您上传到 Klipper 的 G-code 文件内容
    gcode_file_content = """
    G21 ; 使用毫米
    G90 ; 绝对坐标
    M107 ; 关闭风扇

    ; 一个包含非 ASCII 字符的注释 (测试 UTF-8)
    ; 注释：你好世界
    G28 ; 归位

    M140 S60 ; 设置热床 (不等待)
    G1 X10 Y10 F3000
    G1 X20 Y10
    G1 X20 Y20
    G1 X10 Y20
    M105
    """

    # 2. (在您的客户端) 文件上传时，创建映射器实例
    # 这一步（预处理）应该只做一次。
    start_time = time.perf_counter()
    mapper = GcodePositionMapper(gcode_file_content)
    end_time = time.perf_counter()
    print(f"构建映射表耗时: {(end_time - start_time) * 1000:.4f} 毫秒")

    print("-" * 30)

    # 3. (在您的 Websocket 监听器中) 模拟从 Klipper 收到 file_position
    #    您会实时调用 get_line_number()
    klipper_positions_stream = [
        0, 10, 25, 30, 75, 100, 
        160, 178, 195, 212, 229, 235
    ]

    print("模拟 Klipper 实时 `file_position` 更新：\n")
    for pos in klipper_positions_stream:
        line_num = mapper.get_line_number(pos)
        
        # 为了演示，我们同时获取该行的内容
        # 注意：self.line_start_offsets 的索引是 0-based (line_num - 1)
        line_content = gcode_file_content.splitlines()[line_num - 1].strip()
        
        print(f"Klipper 报告: file_position = {pos:3d}  ->  客户端映射到: 行 {line_num:2d} ({line_content})")
        time.sleep(0.5)

    print("\n--- 模拟结束 ---")

if __name__ == "__main__":
    _test_gcode_mapper()