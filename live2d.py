import json
import logging
import random
from flask import Flask, send_from_directory, render_template_string
from web_settings import live2d_port, lan_ip
import tts

app = Flask(__name__, static_folder='dist')
logging.getLogger('werkzeug').setLevel(logging.ERROR)

live2d_web_template = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/png" href="assets/image/logo.png" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
      html, body {
        width: 100%;
        height: 100%;
        overflow: hidden;
        background-image: url('assets/image/bg.jpg');
        background-size: cover;
        background-repeat: no-repeat;
        background-position: center center;
      }
      #canvas2 {
        width: 100%;
        height: 100%;
        display: block;
        background-color: transparent;
      }
    </style>
    <script src="assets/live2d_core/live2dcubismcore.min.js"></script>
    <script src="assets/live2d_core/live2d.min.js"></script>
    <script src="assets/live2d_core/pixi.min.js"></script>
    <title>Live2D角色 - Aivmate LX3</title>
    <script type="module" crossorigin src="/assets/live2d.js?v=2"></script>
  </head>
  <body>
    <div id="app"></div>
    <canvas id="canvas2"></canvas>
  </body>
</html>
"""





# open_source_project_address:https://github.com/MewCo-AI/ai_virtual_mate_linux
@app.route('/')
def index():  # Live2D页面
    return render_template_string(live2d_web_template)


@app.route('/assets/<path:path>')
def serve_static(path):  # 静态资源
    if path.endswith(".js"):
        return send_from_directory('./dist/assets', path, mimetype='application/javascript')
    return send_from_directory('./dist/assets', path)


@app.route('/api/get_mouth_y')
def check_play_state():
    is_playing = tts.tts_playing
    if is_playing:
        return json.dumps({"y": random.uniform(0.1, 0.9)})
    else:
        return json.dumps({"y": 0})


def run_live2d():  # 启动Live2D服务
    print(f"Live2D角色网址：http://{lan_ip}:{str(live2d_port)}\n")
    app.run(port=live2d_port, host="0.0.0.0")
