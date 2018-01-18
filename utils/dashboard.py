#!/usr/bin/python3

import asyncio
import datetime
import json
import time
from operator import attrgetter
import os
import challonge
import dateutil.parser
from dateutil import tz
from pytz import timezone




def get_config():
    # Open the config file
    with open('config.json') as json_data_file:
        config = json.load(json_data_file)
    return config


config = get_config()

# set username, api key, and timezone from config.json
my_username = config["challonge"]["username"]
my_api_key = config["challonge"]["api_key"]
tz = timezone(config["system"]["timezone"])




# I would suggest collapsing all of the functions for maximum cleanliness
### FUNCTIONS ###




# Grabs tournament, and handles all parameters to keep main loop clean



async def get_tourney():
    # Re-reading the configuration file so you can make changes without restarting
    # This makes it easier to re-point at a different tournament_url

    config = get_config()

    # set username, api key, and timezone from config.json
    my_username = config["challonge"]["username"]
    my_api_key = config["challonge"]["api_key"]


    # Initiate Connection to CO
    my_user = await challonge.get_user(my_username, my_api_key)

    # Get Tournament Data
    t = await my_user.get_tournament(url=config["challonge"]["tournament_url"])
    return t

# Correct a crappy string timezone to make it properly
# a datetime object and also has a proper timezone

def fix_date_string(date_string):
    dt_obj = dateutil.parser.parse(date_string)
    dt_obj = dt_obj.astimezone(tz)

    return dt_obj


# Gets either the started_at or start_at date string from tournament object
# and returns parsed datetime object
def get_real_start(tournament, matches):
    # for some reason started_at is a string instead of a DT object
    # also totally not sure when it wants to use started_at or start_at
    # so the news here is that

    if (tournament.started_at):
        time = fix_date_string(tournament.started_at)
    elif (tournament.start_at):
        time = fix_date_string(tournament.start_at)

    elif (len(matches) > 1 and matches[0].underway_at):
        time = fix_date_string(matches[0].underway_at)
    elif (len(matches) > 1 and matches[0].started_at):
        time = fix_date_string(matches[0].started_at)

    else:
        return False
    return time


# Loop to check if tournament has started based on # of participants and start time.
# Loop will break and return true after tournament has started
# Sleep time increases after each unsuccesful run but doesn't keep growing
# Tournament must have .dt property when this is ran
# Straight up Fucked -- for group stages, sometimes Challonge doesn't even bother setting the start time.

async def tournament_has_started(tournament, matches):

    X_default = 5
    X = X_default
    not_started = True

    while (not_started == True):
        if(len(await tournament.get_participants()) < 1):
            print("Tournament has not started.  ( no participants ). Blocking threads by sleeping: ", X)
            not_started = True
        elif (tournament.dt == False and tournament.group_stages_were_started != True):
            print("Tournament has not started.  ( Group not started ). Blocking threads by sleeping: ", X)
            not_started = True
        elif(len(matches) < 1):
            print("Tournament has not started.  ( no matches ). Blocking threads by sleeping: ", X)

            not_started = True
        elif (tournament.dt != False and tournament.dt > datetime.datetime.now(datetime.timezone.utc)):
            print("Tournament has not started.  ( Start time later than now ). Blocking threads by sleeping: ", X)

            not_started = True
        else:
            not_started = False
            return True

        tournament = await get_tourney()
        if tournament.state != "pending":
            matches = await tournament.get_matches()

        tournament.dt = get_real_start(tournament, matches)


        time.sleep(X)
        X = X * 2
        if (X > (X_default*12)):
            X = X_default
    return True


async def get_last_completed_match_id(matches):
    # This isn't finished need to find the match that has newest completion time
    latest_completed_match = matches[0]

    for m in matches:
        if (m.completed_at is None):
            continue
        else:
            if (latest_completed_match.completed_at is None) or (latest_completed_match.completed_at < m.completed_at):
                latest_completed_match = m

    if (latest_completed_match.completed_at is None):
        return False
    else:
        return latest_completed_match.id

# Find out if any match has started but not finished
# this could be by using the "start match" button in challonge
# this is a good way to override what this script THINKS is the current match.
# Just hit start on the actual current match.
async def get_current_match_id(matches):
    started_matches = {}
    for m in matches:
        if (m.completed_at is None) and (m.underway_at is not None):
            started_matches[m.id] = m.underway_at

    if (len(started_matches) >= 1):
        return  max(started_matches, key=started_matches.get)
    else:
        return None


async def get_unplayed_rounds(matches):
    rounds = []
    unfinished_rounds = []
    for m in matches:
        if m.round not in rounds:
            rounds.append(m.round)

        if (m.completed_at is None):
            unfinished_rounds.append(m.round)

    if len(unfinished_rounds) < 1:
        return None

    next_round = min(unfinished_rounds)
    return next_round


async def get_next_round_match_id(matches):
    groups = []  # Still not sure what this is for. Holds groups for fun?
    rounds = []
    unplayed_in_round= []  # Store unplayed match id's in

    next_round = await get_unplayed_rounds(matches)

    for m in matches:
        # If we want our matches staggered between group stage pools I need to find the
        # pool that has the most unplayed matches
        if (m.group_id not in groups):
            groups.append(m.group_id)

        if m.round == next_round and m.completed_at is None:
            unplayed_in_round.append(m.id)

    if len(unplayed_in_round) == 0:
        return None

    next_match_id = min(unplayed_in_round)
    return next_match_id



# Ryan's magic function. Returns the next match id in a staggered group scenario
async def get_next_staggered_match_id(matches):
    groups = []  # Still not sure what this is for. Holds groups for fun?
    unplayed_per_group = {}  # Number of unplayed games per group will be stored in this
    completion_time = {}  # Last completion time of each group will be stored in this
    for m in matches:
        # Totally not sure why this doesn't work, I hate python.  See my note
        # above about me not understanding classes
        # "Hello... is it parenthesis you're looking for?" - Pythonel Richie, and his inconsistent use of parenthesis

        # I think the confusion is that without the parenthesis, the intepreter
        # thinks that you want something like a nested property of the tournament.
        # This specifically says you want the name property from the results of the method:
        # print(m.id, (await t.get_participant(m.player1_id)).name)

        # If we want our matches staggered between group stage pools I need to find the
        # pool that has the most unplayed matches
        if (m.group_id not in groups):
            groups.append(m.group_id)

        if (m.completed_at is None):
            unplayed_per_group[m.group_id] = unplayed_per_group.get(m.group_id, 0) + 1
        else:
            # Again this python library doesn't bother switching the datetime to proper dt objects
            # Anyway what i'm doing here is getting the latest completion time per group
            # using it later
            cat_dt = fix_date_string(m.completed_at)
            if (completion_time.get(m.group_id) is None) or (completion_time.get(m.group_id) < cat_dt):
                completion_time[m.group_id] = cat_dt

    # Done interating through the match results now to parse through this crap

    groups.sort()

    if (len(unplayed_per_group) == 0):
        return None

    # python max returns a single entry if there is a tie -- need to find
    # a way to make sure it returns the pool stage group that has waited the longest for
    # a match or for the group that is directly after the group that has just
    # played.
    maxval = max(unplayed_per_group.values())

    # grab all of the pools who have the most incomplete games (thanks python for a dumb max)
    need_more_games = ([k for k, v in unplayed_per_group.items() if v == maxval])

    # So right now need_more_games has a list of groups that have the most unplayed
    if (len(need_more_games) == 0):
        print("ERROR: We should not get here.", need_more_games)
    elif (len(need_more_games) == 1):
        next_group = need_more_games[0]
    elif (len(need_more_games) >= 1):
        # okay i need to find the team who has the furthest
        # completed match that is the latest of the matches
        # they have played

        # time to go through some completion times! :)
        # Going to make the assumption that lower group_id is lower group
        # gimme that completion time dictionary but only with the need_more_games keys
        # cuz you know performance is important or something lulz
        # p.s. take a shot of whiskey if you don't understand this xsect
        # In medieval times, you would be burned for this kind of black magic

        cross_section = {k: v for k, v in completion_time.items() if k in need_more_games}

        for group in sorted(need_more_games):
            if completion_time.get(group) is None:
                # Hey they have never finished a match in this pool we're great here
                next_group = group
                break
            elif completion_time.get(group) == cross_section[min(cross_section)]:
                next_group = group
                break
            else:
                print(min(cross_section), completion_time.get(group))
                print("ERROR: Are we really getting here?")

    # I know there's a shorthand for this

    next_group_matches = []
    for m in matches:
        if (m.completed_at is None and m.group_id == next_group):
            next_group_matches.append(m.id)

    next_match = min(next_group_matches)
    return next_match
    # print("Next Match ID: ", next_match)


# Get next match in a non-staggered groups scenario
def get_next_match(matches):
    # Will get the match with lowest id and is incomplete and save the object to next match
    incomplete_matches = []

    for m in matches:
        if m.completed_at is None:
            incomplete_matches.append(m)

    # It might be that there are no matches left.

    if len(incomplete_matches) < 1:
        return None

    next_match = min(incomplete_matches, key=attrgetter('suggested_play_order'))
    return next_match


# Get dictionary of team ids -> team names
# Hey so I have to fix this real quick so I am copy pasting.  It only uses group id in group stages
def group_get_participants_list(participants):
    p_list = {}

    if len(participants) < 1:
        print("Tournament has no participants.  It probably hasn't started.")
        return False

    for p in participants:

        # CO has decided that the participant id does not line up
        # to the participant id in the match class -- instead you
        # have to join on the group_player_ids -- I suspect this is CO's
        # way of supporting multi-player teams, participants get assigned
        # to a group_player_id -- group_player_id are assigned to matches
        # unfortunately this behavior looks quirky when you aren't tracking
        # on a player level and just tracking a team

        # group_id does not work as expected -- it is set to None. Thanks Obama


        if (p.group_id):
            print("DEBUG: something has changed", p.group_id)
        elif (len(p.group_player_ids) >= 1):
            p_list[p.group_player_ids[0]] = p.name
        else:
            # This is where you end up if the tournament hasn't started
            p_list[p.id] = p.name


    return p_list

# Get dictionary of team ids -> team names
# Hey so I have to fix this real quick so I am copy pasting.  It only uses group id in group stages
def get_participants_list(participants):
    p_list = {}

    if len(participants) < 1:
        print("Tournament has no participants.  It probably hasn't started.")
        return False

    for p in participants:

        # CO has decided that the participant id does not line up
        # to the participant id in the match class -- instead you
        # have to join on the group_player_ids -- I suspect this is CO's
        # way of supporting multi-player teams, participants get assigned
        # to a group_player_id -- group_player_id are assigned to matches
        # unfortunately this behavior looks quirky when you aren't tracking
        # on a player level and just tracking a team

        # group_id does not work as expected -- it is set to None. Thanks Obama


        if (p.group_id):
            print("DEBUG: something has changed", p.group_id)
        else:
            # This is where you end up if the tournament hasn't started
            p_list[p.id] = p.name


    return p_list



### END FUNCTIONS ###

async def get_results(loop):

    # Okay this is so stupid at this point this was the original logic which was very function heavy
    # cuz i was the only one working on it but now its just painful.

    output = { 'tournament' : {}, 'matches' : { 'last' : {}, 'current' : {}, 'next' : {}, 'next2' : {}, 'next3' : {} }}

    # Grab the tournament. See function above.
    t = await get_tourney()
    output["tournament"]["name"] = t.name

    # I might use this at some point
    completed = False

    # Get all them matches -- yes its early in the process but i need this info
    t_matches = {}
    if (t.state != "pending"):
        t_matches = await t.get_matches()

    t.dt = get_real_start(t, t_matches)
    await tournament_has_started(t, t_matches)


    # Grab real start time and sets it to tournament dt property. See function above

    # strftime is a function of datetime that sets format (in this example: YY/MM/DD, hh:mmAM/PM)
    # See strftime documentation here: http://strftime.org/
    output["tournament"]["started_at"] = t.dt




    # Run function to wait until tournament has started

    # Get participant data. This returns a dictionary where the key is equal to match.playerx_id
    # and the values are the names of the team.  Useful for quickly finding team names based on
    # match values
    participants = await t.get_participants()

    # This is stupid but challonge uses seperate player indexes based
    # on if it is a group match or not
    # which gets confusing when it sends you all the matches in a two part
    # tournament so we grab both sets of data but only use the group
    # data during group stages (and directly after when the 2nd part
    # starts and the last match played is a group match

    group_p_list = group_get_participants_list(participants)
    p_list =  get_participants_list(participants)
    if t.state == "group_stages_underway":
        p_list = group_p_list

    next_match_id = None
    last_match = await get_last_completed_match_id(t_matches)

    # okay i know this is stupid but if i didn't give a fake date on the matches as i re-iterated
    # they would start showing up in the list again.  (trust me).
    # also its sort of sad that i convert them into datetime just to so i can more easily do the time
    # math on them and then convert them back into a string.  it was easier to do that than to change
    # all the references to datetime objects

    if (last_match != False):
        last_match = await t.get_match(last_match)
        fake_date = fix_date_string(last_match.completed_at)
        output["matches"]["last"]["id"] = last_match.id

        # Stupid corner case where Challonge switches from using the group player id
        # to the player id to index matches but the last match that was played still uses group
        # happens on first match of a two part tournament
        if last_match.player1_id not in p_list:
            output["matches"]["last"]["player1"] = group_p_list[last_match.player1_id]
            output["matches"]["last"]["player2"] = group_p_list[last_match.player2_id]
        else:
            output["matches"]["last"]["player1"] = p_list[last_match.player1_id]
            output["matches"]["last"]["player2"] = p_list[last_match.player2_id]

        output["matches"]["last"]["completed_at"] = fake_date
    else:
        fake_date = t.dt


    # If the pool is staggered, run Ryan's magic algorithm
    # Okay I am sorry that these blocks are a giant (winter) cluster f***
    # but basically if there IS no next match, I have to do setup a fake environemnt
    # to keep on trucking.  And I have to do this in each block that is almost
    # identical
    if (config["order"]["pool"] == "staggered" and t.state == "group_stages_underway"):
        current_match_id = await get_current_match_id(t_matches)
        if (current_match_id is None):
            next_match_id = await get_next_staggered_match_id(t_matches)
            if next_match_id is not None:
                next_match = await t.get_match(next_match_id)
            else:
                # I think this means tournament is completed
                # or at final match
                completed = True

        else:
            next_match_id = current_match_id
            next_match = await t.get_match(next_match_id)
    elif (config["order"]["pool"] == "rounds" and t.state == "group_stages_underway"):
        current_match_id = await get_current_match_id(t_matches)
        if (current_match_id is None):
            next_match_id = await get_next_round_match_id(t_matches)
            if next_match_id is not None:
                next_match = await t.get_match(next_match_id)
            else:
                # I think this means tournament is completed
                # or at final match
                completed = True
        else:
            next_match_id = current_match_id
            next_match = await t.get_match(next_match_id)

    else:
        current_match_id = await get_current_match_id(t_matches)
        if (current_match_id is  None):
            next_match = get_next_match(t_matches)
            if next_match is not  None:
                next_match_id = next_match.id
            else:
                # I think this means tournament is completed_at
                # this isn't true!  it just means you are on the final match
                completed = True
        else:
            next_match_id = current_match_id
            next_match = await t.get_match(next_match_id)


    if completed == True and current_match_id is None:
        output["matches"]["current"]["id"] = None
        output["matches"]["current"]["player1"] = ''
        output["matches"]["current"]["player2"] = ''
    else:
        output["matches"]["current"]["id"] = next_match.id
        output["matches"]["current"]["player1"] = p_list[next_match.player1_id]
        output["matches"]["current"]["player2"] = p_list[next_match.player2_id]



    # Okay so if someone clicked the "start" in Challonge use that, else use the completed of the last matches
    if next_match_id is  None:
        output["matches"]["current"]["started_at"] = fake_date
    elif next_match.underway_at is not None:
        output["matches"]["current"]["started_at"] = fix_date_string(next_match.underway_at)
    elif next_match.started_at is not None:
        output["matches"]["current"]["started_at"] = fix_date_string(next_match.started_at)
    else:
        output["matches"]["current"]["started_at"] = fake_date


    # At first I thought about passing how many seconds have passed since the games
    # started but the poll only runs every X amount of time so i should just pass the
    # time into the javascript and let it do the math there
    # output["matches"]["current"]["duration_seconds"] = datetime.datetime.now(datetime.timezone.utc) - output["matches"]["current"]["started_at"]
    # print(output["matches"]["current"]["duration_seconds"].seconds)

    if next_match_id is not None:
        for idx, v in enumerate(t_matches):
            if v.id == next_match.id:
                t_matches[idx].completed_at = str(fake_date + datetime.timedelta(seconds=60))

    if (config["order"]["pool"] == "staggered" and t.state == "group_stages_underway"):
        next_match_id = await get_next_staggered_match_id(t_matches)
        if next_match_id is not None:
            next_match = await t.get_match(next_match_id)
            output["matches"]["next"]["id"] = next_match.id
            output["matches"]["next"]["player1"] = p_list[next_match.player1_id]
            output["matches"]["next"]["player2"] = p_list[next_match.player2_id]
        else:
            output["matches"]["next"]["id"] = None
            output["matches"]["next"]["player1"] = ''
            output["matches"]["next"]["player2"] = ''
    elif (config["order"]["pool"] == "rounds" and t.state == "group_stages_underway"):
        next_match_id = await get_next_round_match_id(t_matches)
        if next_match_id is not None:
            next_match = await t.get_match(next_match_id)
            output["matches"]["next"]["id"] = next_match.id
            output["matches"]["next"]["player1"] = p_list[next_match.player1_id]
            output["matches"]["next"]["player2"] = p_list[next_match.player2_id]
        else:
            output["matches"]["next"]["id"] = None
            output["matches"]["next"]["player1"] = ''
            output["matches"]["next"]["player2"] = ''
    else:
        next_match = get_next_match(t_matches)
        if next_match is not None:
            next_match_id = next_match.id
            output["matches"]["next"]["id"] = next_match.id
            if next_match.player1_id is None:
                output["matches"]["next"]["player1"] = 'TBD'
            else:
                output["matches"]["next"]["player1"] = p_list[next_match.player1_id]

            if next_match.player2_id is None:
                output["matches"]["next"]["player2"] = 'TBD'
            else:
                output["matches"]["next"]["player2"] = p_list[next_match.player2_id]
        else:
            output["matches"]["next"]["id"] = None
            output["matches"]["next"]["player1"] = ''
            output["matches"]["next"]["player2"] = ''



    if next_match_id is not None:
        for idx, v in enumerate(t_matches):
            if v.id == next_match_id:
                t_matches[idx].completed_at = str(fake_date + datetime.timedelta(seconds=120))

    if (config["order"]["pool"] == "staggered" and t.state == "group_stages_underway"):
        next_match_id = await get_next_staggered_match_id(t_matches)
        if next_match_id is not None:
            next_match = await t.get_match(next_match_id)
            output["matches"]["next2"]["id"] = next_match.id
            if next_match.player1_id is None:
                output["matches"]["next2"]["player1"] = 'TBD'
            else:
                output["matches"]["next2"]["player1"] = p_list[next_match.player1_id]

            if next_match.player2_id is None:
                output["matches"]["next2"]["player2"] = 'TBD'
            else:
                output["matches"]["next2"]["player2"] = p_list[next_match.player2_id]

        else:
            output["matches"]["next2"]["id"] = None
            output["matches"]["next2"]["player1"] = ''
            output["matches"]["next2"]["player2"] = ''

    elif (config["order"]["pool"] == "rounds" and t.state == "group_stages_underway"):
        next_match_id = await get_next_round_match_id(t_matches)
        if next_match_id is not None:
            next_match = await t.get_match(next_match_id)
            output["matches"]["next2"]["id"] = next_match.id
            if next_match.player1_id is None:
                output["matches"]["next2"]["player1"] = 'TBD'
            else:
                output["matches"]["next2"]["player1"] = p_list[next_match.player1_id]

            if next_match.player2_id is None:
                output["matches"]["next2"]["player2"] = 'TBD'
            else:
                output["matches"]["next2"]["player2"] = p_list[next_match.player2_id]

        else:
            output["matches"]["next2"]["id"] = None
            output["matches"]["next2"]["player1"] = ''
            output["matches"]["next2"]["player2"] = ''

    else:
        try:
            next_match = get_next_match(t_matches)
            next_match_id = next_match.id
            output["matches"]["next2"]["id"] = next_match.id
            if next_match.player1_id is None:
                output["matches"]["next2"]["player1"] = 'TBD'
            else:
                output["matches"]["next2"]["player1"] = p_list[next_match.player1_id]

            if next_match.player2_id is None:
                output["matches"]["next2"]["player2"] = 'TBD'
            else:
                output["matches"]["next2"]["player2"] = p_list[next_match.player2_id]

        except:
            output["matches"]["next2"]["id"] = None
            output["matches"]["next2"]["player1"] = ''
            output["matches"]["next2"]["player2"] = ''

    if next_match_id is not None:
        for idx, v in enumerate(t_matches):
            if v.id == next_match_id:
                t_matches[idx].completed_at = str(fake_date + datetime.timedelta(seconds=180))

    if (config["order"]["pool"] == "staggered" and t.state == "group_stages_underway"):
        next_match_id = await get_next_staggered_match_id(t_matches)
        if next_match_id is not None:
            next_match = await t.get_match(next_match_id)
            output["matches"]["next3"]["id"] = next_match.id
            if next_match.player1_id is None:
                output["matches"]["next3"]["player1"] = 'TBD'
            else:
                output["matches"]["next3"]["player1"] = p_list[next_match.player1_id]

            if next_match.player2_id is None:
                output["matches"]["next3"]["player2"] = 'TBD'
            else:
                output["matches"]["next3"]["player2"] = p_list[next_match.player2_id]
        else:
            output["matches"]["next3"]["id"] = None
            output["matches"]["next3"]["player1"] = ''
            output["matches"]["next3"]["player2"] = ''
    elif (config["order"]["pool"] == "rounds" and t.state == "group_stages_underway"):
        next_match_id = await get_next_round_match_id(t_matches)
        if next_match_id is not None:
            next_match = await t.get_match(next_match_id)
            output["matches"]["next3"]["id"] = next_match.id
            if next_match.player1_id is None:
                output["matches"]["next3"]["player1"] = 'TBD'
            else:
                output["matches"]["next3"]["player1"] = p_list[next_match.player1_id]

            if next_match.player2_id is None:
                output["matches"]["next3"]["player2"] = 'TBD'
            else:
                output["matches"]["next3"]["player2"] = p_list[next_match.player2_id]
        else:
            output["matches"]["next3"]["id"] = None
            output["matches"]["next3"]["player1"] = ''
            output["matches"]["next3"]["player2"] = ''

    else:
        try:
            next_match = get_next_match(t_matches)
            output["matches"]["next3"]["id"] = next_match.id
            if next_match.player1_id is None:
                output["matches"]["next3"]["player1"] = 'TBD'
            else:
                output["matches"]["next3"]["player1"] = p_list[next_match.player1_id]

            if next_match.player2_id is None:
                output["matches"]["next3"]["player2"] = 'TBD'
            else:
                output["matches"]["next3"]["player2"] = p_list[next_match.player2_id]
        except:
            output["matches"]["next3"]["id"] = None
            output["matches"]["next3"]["player1"] = ''
            output["matches"]["next3"]["player2"] = ''


    output['matches']['current']['started_at'] = output['matches']['current']['started_at'].isoformat()
    # So we have all the logic for getting matches, getting the next match, tournament details,
    # and participants detail. Now what?

    return output


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(get_results(loop))
