import asyncio
import pickle
from flask import Flask, render_template, send_from_directory

from utils.dashboard import get_results

app = Flask(__name__, static_url_path='')


@app.route('/css/<path:path>')
def send_css(path):
    return send_from_directory('css', path)


@app.route('/font-awesome/<path:path>')
def send_font(path):
    return send_from_directory('font-awesome', path)


@app.route('/fonts/<path:path>')
def send_fonts(path):
    return send_from_directory('fonts', path)


@app.route('/img/<path:path>')
def send_img(path):
    return send_from_directory('img', path)


@app.route('/js/<path:path>')
def send_js(path):
    return send_from_directory('js', path)


@app.route('/poll')
def poll(name=None):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    output = loop.run_until_complete(get_results(loop))

    o = open('data.pkl', 'wb')

    pickle.dump(output, o)
    return render_template('index.html', name=name, output=output)


@app.route('/')
@app.route('/<name>')
def hello(name=None):

    o = open('data.pkl', 'rb')
    output = pickle.load(o)

    return render_template('index.html', name=name, output=output)


if __name__ == '__main__':
    app.run()
