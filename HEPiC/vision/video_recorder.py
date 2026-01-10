import subprocess
import numpy as np
from PySide6.QtCore import QThread, Slot, Signal
import queue
import logging

class VideoRecorder(QThread):

    sigClose = Signal()

    def __init__(self, filename, width=512, height=512, fps=30, logger=None):
        super().__init__()

        # name the thread for easier debugging
        self.setObjectName("VideoRecorder")

        self.command = [
            'ffmpeg',
            '-y',                 # 覆盖同名文件
            '-f', 'rawvideo',     # 输入格式：原始视频流
            '-vcodec', 'rawvideo',
            '-s', f'{width}x{height}', # 分辨率
            '-pix_fmt', 'bgr24',  # OpenCV 默认是 BGR，这里告诉 FFmpeg 输入是 BGR
            '-r', str(fps),       # 帧率
            '-i', '-',            # 从标准输入(Pipe)读取数据
            '-c:v', 'libx264',    # 编码器 (如果有 N 卡，改成 'h264_nvenc' 速度起飞)
            '-pix_fmt', 'yuv420p',# 输出必须转为 yuv420p 才能在普通播放器播放
            '-preset', 'fast',    # 编码速度：ultrafast, superfast, veryfast, fast, medium, slow
            '-crf', '28',         # 画质控制：18-28。数值越小画质越好。23 是默认平衡点。
            '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2', # 总是将图像转为偶数尺寸
            filename
        ]
        
        self.queue = queue.Queue(maxsize=200)

        # 创建子进程，打开 stdin 管道
        self.pipe = subprocess.Popen(
            self.command, 
            stdin=subprocess.PIPE, 
            stderr=subprocess.PIPE # 或者是 subprocess.PIPE 以捕获错误日志
        )

        self.logger = logger or logging.getLogger(__name__)

    @Slot()
    def add_frame(self, frame):
        try:
            # 关键点 2: put_nowait 防止阻塞生产者
            # 如果队列满了，说明写入太慢，这里选择丢帧，保护主程序不卡死
            self.queue.put_nowait(frame)
        except queue.Full:
            self.logger.warning("写入队列已满，发生丢帧！")
    
    def run(self):
        self.logger.info("start recording video")
        while True:
            frame = self.queue.get() # 阻塞等待，直到有数据
            if frame is None: # 遇到哨兵，退出
                self.queue.task_done()
                break
            
            try:
                self.pipe.stdin.write(frame.tobytes())
            except Exception as e:
                self.logger.error(f"FFmpeg Pipe Error: {e}")
            
            self.queue.task_done()

    @Slot()
    def close(self):
        # put None in queue
        self.queue.put_nowait(None)
        # self.is_running = False
        if self.pipe:         
            try:
                # communicate 会关闭 stdin，并读取 stdout/stderr 直到进程结束
                outs, errs = self.pipe.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                self.pipe.kill()
                outs, errs = self.pipe.communicate()
            self.deleteLater()

# --- 使用示例 ---
# 假设在你的线程中
if __name__ == "__main__":
    recorder = VideoRecorder('output.mkv', 512, 512, 30)

    x = np.arange(512)
    y = x
    X, Y = np.meshgrid(x, y)
    
    # 模拟循环
    for i in range(80000):
        # 假设这是你的分析结果图像
        
        w = 1
        k = 5
        frame = np.zeros((512, 512, 3))
        frame[:, :, 0] = np.sin(w*X - k*i)
        
        recorder.write(frame)

    recorder.close()