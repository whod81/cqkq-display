import asyncio
import pickle
import os


# from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, render_template, send_from_directory, request, redirect
from dateutil.relativedelta import relativedelta
from datetime import datetime, timedelta
from utils.dashboard import get_results, get_config, update_config
from pathlib import Path;



def poller():
    """ Function for test purposes. """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    output = loop.run_until_complete(get_results(loop))
    o = open('data.pkl', 'wb')

    pickle.dump(output, o)


sched = BackgroundScheduler(daemon=True)
sched.add_job(poller, 'interval', seconds=10)
sched.start()

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

@app.route('/teams/<path:path>')
def send_teams(path):
    return send_from_directory('teams', path)



@app.route('/js/<path:path>')
def send_js(path):
    return send_from_directory('js', path)


# @app.route('/poll')
# def poll(name=None):
#
#     return render_template('index.html', name=name, output=output)


@app.route('/')
def hello(name=None):
    o = open('data.pkl', 'rb')
    output = pickle.load(o)
    return render_template('index.html', name=name, tournament=output['tournament'], matches=output['matches'])

@app.route('/pictures/<match>')
def print_imgpage(match):
    o = open('data.pkl', 'rb')
    output = pickle.load(o)

    if match == "next":
            team1_name = output['matches']['next']['player1']
            team2_name = output['matches']['next']['player2']
    elif match == "next2":
            team1_name = output['matches']['next2']['player1']
            team2_name = output['matches']['next2']['player2']
    elif match == "next3":
            team1_name = output['matches']['next3']['player1']
            team2_name = output['matches']['next3']['player2']
    else:
            team1_name = output['matches']['current']['player1']
            team2_name = output['matches']['current']['player2']

    # Cheezey solution but I'm just going to create a couple of arrays that the key is the player name (assumeed
    # from the image name) and the value is the URI of their pictures

    # To make it more complicated I am going to also create an array of player names for each team
    # to make the template easier to understand

    team1_images = {}
    team2_images = {}

    team1_players = {}
    team2_players = {}

    ValidExts = ['.JPG','.JPEG','.PNG']

    # Just a note that if a team has a () in it that isn't part of the scene names the code will break

    sep = ' ('


    # I mean I could have written a function but I'm sorta into copy/paste.

    team1_name_without_scene = team1_name.split(sep, 1)[0];
    path="teams/" + team1_name_without_scene;
    print(path);

    if os.path.isdir(path):
        for count, filename in enumerate(sorted(os.listdir(path)), start=1):
            if count > 5:
                break;
            suffix = Path(filename).suffix;
            player_name = filename.replace(suffix,'')
            team1_players[count] = player_name;
            if suffix.upper() in ValidExts:
                team1_images[player_name] = "/teams/" + team1_name_without_scene + '/' + filename;
    else:
        print("Having trouble finding team images:" + path)

    # I mean I could have written a function but I'm sorta into copy/paste.

    team2_name_without_scene = team2_name.split(sep, 1)[0];
    path="teams/" + team2_name_without_scene;


    if os.path.isdir(path):
        for count, filename in enumerate(sorted(os.listdir(path)), start=1):
            if count > 5:
                break;
            suffix = Path(filename).suffix;
            player_name = filename.replace(suffix,'')
            team2_players[count] = player_name;

            if suffix.upper() in ValidExts:
                team2_images[player_name] = "/teams/" + team2_name_without_scene + '/' + filename;
    else:
        print("Having trouble finding team images:" + path)


    return render_template('pictures.html', match=match, team1_name=team1_name, team2_name=team2_name, team1_players=team1_players, team2_players=team2_players,team1_images=team1_images, team2_images=team2_images)

@app.route('/player/<match>/<player>')
def print_player(match, player):
    o = open('data.pkl', 'rb')
    output = pickle.load(o)

    if match == "current":
        if player == '1':
            player_name = output['matches']['current']['player1']
        elif player == '2':
            player_name = output['matches']['current']['player2']
    elif match == "next":
        if player == '1':
            player_name = output['matches']['next']['player1']
        elif player == '2':
            player_name = output['matches']['next']['player2']
    elif match == "next2":
        if player == '1':
            player_name = output['matches']['next2']['player1']
        elif player == '2':
            player_name = output['matches']['next2']['player2']
    elif match == "next3":
        if player == '1':
            player_name = output['matches']['next3']['player1']
        elif player == '2':
            player_name = output['matches']['next3']['player2']
    else:
        player_name = "ERROR"

    return render_template('player.html', player=player, player_name=player_name)

@app.route('/config', methods=['GET', 'POST'])
def configurate():
    if request.method == 'POST':
        update_config(request.form["username"], request.form["api_key"], request.form["tournament_url"], request.form["timezone"], request.form["pool"])
        return redirect('http://localhost:5000/config', code=302)
    else:
        config = get_config()
        template_variables = {
            'username': config['challonge']['username'],
            'api_key': config['challonge']['api_key'],
            'tournament_url': config['challonge']['tournament_url'],
            'timezone': config['system']['timezone'],
            'pool_type': config['order']['pool']
        }
        return render_template('config.html', **template_variables)

@app.after_request
def add_header(response):
    """
    Add headers to both force latest IE rendering engine or Chrome Frame,
    and also to cache the rendered page for 10 minutes.
    """
    response.headers['X-UA-Compatible'] = 'IE=Edge,chrome=1'
    response.headers['Cache-Control'] = 'public, max-age=60'
    return response

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html')



if __name__ == '__main__':
    app.run(host='0.0.0.0',debug=True)
