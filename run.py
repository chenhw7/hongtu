import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    if debug:
        app.run(host='0.0.0.0', port=5000, debug=True)
    else:
        from waitress import serve
        app.logger.info('鸿图建材获客工具启动中...')
        app.logger.info('访问地址：http://localhost:5000')
        app.logger.info('按 Ctrl+C 停止服务')
        serve(app, host='0.0.0.0', port=5000)
