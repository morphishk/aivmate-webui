# docker build --no-cache -t aivmate/aivmate-webui .
FROM smanx/opencode:latest

WORKDIR /app

# 更换 apt 源为清华源
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources 2>/dev/null || \
    sed -i 's|http://deb.debian.org |https://mirrors.tuna.tsinghua.edu.cn |g' /etc/apt/sources.list && \
    sed -i 's|http://security.debian.org |https://mirrors.tuna.tsinghua.edu.cn/debian-security |g' /etc/apt/sources.list || true

# 安装系统依赖（音频、编译、图形库等）
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-full \
    python3-dev \
    gcc \
    g++ \
    make \
    cmake \
    libasound-dev \
    portaudio19-dev \
    libportaudio2 \
    libportaudiocpp0 \
    libgl1 \
    libglib2.0-0 \
    libx11-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 创建 Python 虚拟环境
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 配置 pip 使用清华源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple 

# 升级 pip、setuptools、wheel
RUN pip install --upgrade pip setuptools wheel

# 1. 先安装固定版本的 openvino（兼容 rapidocr_openvino）
RUN pip install --no-cache-dir openvino==2024.6.0

# 2. 复制 requirements.txt，过滤掉 openvino 和 rapidocr_openvino（避免冲突）
COPY requirements.txt /tmp/requirements.txt
RUN grep -v -E "openvino|rapidocr_openvino" /tmp/requirements.txt > /tmp/requirements_filtered.txt

# 3. 安装过滤后的依赖
RUN pip install --no-cache-dir -r /tmp/requirements_filtered.txt && rm /tmp/requirements.txt /tmp/requirements_filtered.txt

# 4. 最后安装 rapidocr_openvino，且不安装它的依赖（防止升级 openvino）
RUN pip install --no-cache-dir rapidocr_openvino --no-deps

# 5. 手动补全 rapidocr_openvino 的依赖（这些通常在 requirements_filtered.txt 中已存在，但确保一下）
RUN pip install --no-cache-dir opencv-python pyclipper Shapely PyYAML Pillow six

# 验证 openvino 导入是否正常
RUN python -c "from openvino.runtime import Core; print('openvino.runtime OK')"

# 暴露端口：主机状态(5260) / Live2D(5261) / MMD(5262) / VRM(5263) / 系统设置(5250) / OpenCode(3000)
EXPOSE 5260 5261 5262 5263 5250 3000

# 复制启动脚本并赋予执行权限
COPY start.sh /start.sh
RUN chmod +x /start.sh

ENTRYPOINT ["/start.sh"]
