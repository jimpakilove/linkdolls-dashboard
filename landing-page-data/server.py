#!/usr/bin/env python3
"""
数据看板后端服务
- 提供静态文件
- 提供刷新数据API
"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import subprocess
import json
import os

class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=os.path.dirname(os.path.abspath(__file__)), **kwargs)
    
    def do_GET(self):
        # API: 刷新数据
        if self.path == '/api/refresh':
            self.handle_refresh()
            return
        
        # API: 检查状态
        if self.path == '/api/status':
            self.handle_status()
            return
        
        # 其他请求走静态文件
        super().do_GET()
    
    def do_POST(self):
        # POST 也支持刷新
        if self.path == '/api/refresh':
            self.handle_refresh()
            return
        
        self.send_error(404)
    
    def handle_refresh(self):
        """执行聚合脚本"""
        try:
            # 执行聚合脚本
            result = subprocess.run(
                ['python3', 'aggregate_detail.py'],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                response = {
                    'success': True,
                    'message': '数据刷新成功',
                    'output': result.stdout
                }
            else:
                response = {
                    'success': False,
                    'message': '数据刷新失败',
                    'error': result.stderr
                }
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
    
    def handle_status(self):
        """检查服务状态"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'status': 'ok'}).encode('utf-8'))
    
    def log_message(self, format, *args):
        # 只记录API请求
        if '/api/' in args[0]:
            print(f"[API] {args[0]}")

def main():
    port = 8765
    server = HTTPServer(('', port), DashboardHandler)
    print(f"🚀 服务启动: http://localhost:{port}")
    print(f"📊 看板地址: http://localhost:{port}/dashboard.html")
    print(f"🔄 刷新API: http://localhost:{port}/api/refresh")
    print("\n按 Ctrl+C 停止服务\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 服务已停止")
        server.shutdown()

if __name__ == '__main__':
    main()