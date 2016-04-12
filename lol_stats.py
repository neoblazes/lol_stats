#-*- coding: utf-8 -*-

#!/usr/bin/env python
#
# LOL stats.
# To collect matches and show stats per champion.
#
# Yung Choi, neoblaze@gmail.com
#
import cgi
import datetime
import json
import time
import webapp2

from collections import defaultdict
from operator import itemgetter
from google.appengine.ext import ndb
from google.appengine.api import taskqueue
from google.appengine.api import urlfetch
from google.appengine.api import users
from google.appengine.datastore.datastore_query import Cursor

import sys
reload(sys)
sys.setdefaultencoding('utf-8')

import champ_mappings

riot_api_host = 'https://kr.api.pvp.net/'
# Get the api key by register to Riot developer,
# https://developer.riotgames.com/
riot_api_key = '?api_key=a77a6e5a-cbb0-4327-ad39-867478a4cc1f'

url_featured_matches = (
    riot_api_host + 'observer-mode/rest/featured' + riot_api_key)
url_summoner_by_name = (
    riot_api_host + 'api/lol/kr/v1.4/summoner/by-name/%s' + riot_api_key)
url_summoner_detail_by_id = (
    riot_api_host + 'api/lol/kr/v2.5/league/by-summoner/%s/entry' +
    riot_api_key)
url_find_matches = (
    riot_api_host + 'api/lol/kr/v2.2/matchlist/by-summoner/%d' + riot_api_key +
    '&beginTime=%s000')
url_update_match = (
    riot_api_host + 'api/lol/kr/v2.2/match/%d' + riot_api_key)

# Static api has different host.
url_champion = (
    'https://global.api.pvp.net/api/lol/static-data/kr/v1.2/champion' +
    riot_api_key)

url_item_image_tpl = (
    'http://ddragon.leagueoflegends.com/cdn/6.4.1/img/item/%s.png')

tier_sort_score = {
    'UNRANKED' : 0,
    'BRONZE' : 1,
    'SILVER' : 2,
    'GOLD' : 3,
    'PLATINUM' : 4,
    'DIAMOND' : 5,
    'MASTER' : 6,
    'CHALLENGER' : 7,
    }
tier_cut_off = 4  # lowest tier to store. 4 is PLATIN.

rank_queue_id = 'RANKED_SOLO_5x5'
rank_game_id = 'TEAM_BUILDER_DRAFT_RANKED_5x5'

class Summoner(ndb.Model):
  """ DB model for summoners. """
  name = ndb.StringProperty()
  user_id = ndb.IntegerProperty()
  tier = ndb.StringProperty()
  last_update = ndb.DateTimeProperty()

class Seed(webapp2.RequestHandler):
  """ Finds seed summoners from featured games. """
  def get(self):
    # Gets featured games.
    self.response.out.write('Open url: ' + url_featured_matches + '<br/>')
    result = urlfetch.fetch(url_featured_matches)
    if result.status_code == 200:
      rc = json.loads(result.content)
      summoner_names = set()
      for game in rc['gameList']:
        for participant in game['participants']:
          summoner_names.add(participant['summonerName'])
      # Add summoner names to DB.
      for name in summoner_names:
        summoner = Summoner(name=name)
        summoner.put()
        self.response.out.write('Added %s to Summoner DB<br>' % name)
    else:
      self.response.out.write(result.status_code)

    # Find summoner ids until it return false (found all ids).
    while self.find_summoner_ids():
      pass

  def find_summoner_ids(self):
    # Find 20 ids per call.
    summoners = Summoner.query(Summoner.user_id == None).fetch(20)
    if not summoners:
      self.response.out.write('No summoner to find id.');
      return False
    all_names = ','.join(x.name for x in summoners)
    name_id_map = {}
    url = (url_summoner_by_name % all_names).replace(' ', '%20')
    self.response.out.write('Open url: ' + url + '<br/>')
    result = urlfetch.fetch(url)
    if result.status_code == 200:
      rc = json.loads(result.content)
      for value in rc.values():
        name_id_map[value['name']] = value['id']
    else:
      response = result.status_code
    for summoner in summoners:
      if summoner.name in name_id_map:
        summoner.user_id = name_id_map[summoner.name]
        self.response.out.write(
            'Name: %s, Id: %s<br/>' % (summoner.name, summoner.user_id))
        summoner.put()
      else:
        # Remove summoner cannot get id.
        summoner.key.delete()
    return True

class ShowSummoners(webapp2.RequestHandler):
  """ Shows all summoners. """
  def get(self):
    cache = ResultCache.query(ResultCache.request == 'summoners').fetch(1)
    if len(cache) >= 1:
      self.response.out.write(cache[0].response)

class CleanupSummoners(webapp2.RequestHandler):
  """ Removes duplicated summoners. """
  def get(self):
    summoner_names = set()
    curs = Cursor()
    while True:
      # Breaks down the record into pieces to avoid timeout.
      summoners, curs, more = (
          Summoner.query().fetch_page(5000, start_cursor=curs))
      for summoner in summoners:
        if summoner.name in summoner_names:
          summoner.key.delete()
          self.response.out.write('Deleted dup Name: %s<br/>' % summoner.name)
        else:
          summoner_names.add(summoner.name)
      if not(more and curs):
        break

class Matchup(ndb.Model):
  """ DB model for matchups. """
  match_id = ndb.IntegerProperty()
  match_creation = ndb.IntegerProperty()
  # Chanpions per lane.
  top_win = ndb.IntegerProperty(indexed=False)
  top_lose = ndb.IntegerProperty(indexed=False)
  middle_win = ndb.IntegerProperty(indexed=False)
  middle_lose = ndb.IntegerProperty(indexed=False)
  jungle_win = ndb.IntegerProperty(indexed=False)
  jungle_lose = ndb.IntegerProperty(indexed=False)
  bottom_duo_carry_win = ndb.IntegerProperty(indexed=False)
  bottom_duo_carry_lose = ndb.IntegerProperty(indexed=False)
  bottom_duo_support_win = ndb.IntegerProperty(indexed=False)
  bottom_duo_support_lose = ndb.IntegerProperty(indexed=False)
  # Items per lane.
  top_win_items = ndb.StringProperty(indexed=False)
  top_lose_items = ndb.StringProperty(indexed=False)
  middle_win_items = ndb.StringProperty(indexed=False)
  middle_lose_items = ndb.StringProperty(indexed=False)
  jungle_win_items = ndb.StringProperty(indexed=False)
  jungle_lose_items = ndb.StringProperty(indexed=False)
  bottom_duo_carry_win_items = ndb.StringProperty(indexed=False)
  bottom_duo_carry_lose_items = ndb.StringProperty(indexed=False)
  bottom_duo_support_win_items = ndb.StringProperty(indexed=False)
  bottom_duo_support_lose_items = ndb.StringProperty(indexed=False)

class FindMatches(webapp2.RequestHandler):
  """ Finds matches by listing games for summoners.

  The summoners to be updated are selected by LRU.
  It only gets game IDs. The detail of games will be filled by UpdateMatches().
  It will do nothing if there are more than 1000 games waiting for 'update'.
  """
  def get(self):
    # There is limit control inside find_match() function.
    # So it's fine to call the function multiple times.

    # Finds new summoner first.
    self.response.out.write('Finding matches from new summoners.<br/>')
    if not self.find_match(0):  # 0 means only new.
      # Finds old summoners next. Note that new summoners always
      # can be picked on any steps.
      self.response.out.write(
          'Finding matches from 1 week old summoners.<br/>')
      if not self.find_match(7):
        # Finds recent summoners at last.
        self.response.out.write(
            'Finding matches from 1 day old summoners.<br/>')
        self.find_match(1)

  def find_match(self, days_delta):
    """ Returns True when it's full. """
    not_updated_matchups = Matchup.query(
        Matchup.match_creation == None).fetch(1000)
    if len(not_updated_matchups) >= 1000:
      self.response.out.write(
          'More than 1000 matches are waiting for update. ' +
          'Will not find more.<br/>');
      return True

    if days_delta == 0:
      summoners = Summoner.query(Summoner.last_update == None).fetch(10)
    else:
      summoners = Summoner.query(
          ndb.OR(Summoner.last_update == None,
                 Summoner.last_update < (datetime.datetime.now() -
                                         datetime.timedelta(days=days_delta))
                 )).fetch(10)
    if not summoners:
      self.response.out.write('No summoner to update match.');
      return

    # Updates summoners' tiers.
    # Try up to 5 times because tier info is important to
    # decide whether keep or drop summoners.
    for _ in xrange(5):
      url = url_summoner_detail_by_id % (
          ','.join(str(summoner.user_id) for summoner in summoners))
      self.response.out.write('Fetch url: %s<br/>' % url)
      result = urlfetch.fetch(url)
      id_to_tier = {}
      if result.status_code == 200:
        rc = json.loads(result.content)
        for key in rc:
          for league in rc[key]:
            if league['queue'] == rank_queue_id:
              id_to_tier[int(key)] = league['tier']
              break
        break
      elif result.status_code == 429:
        time.sleep(3)  # Sleeps 3 seconds to avoid ACL.
      else:
        self.response.out.write('API server error. Delete all.<br/>')
        for summoner in summoners:
          summoner.key.delete()
        return

    # Find matchs.
    count = 0
    for summoner in summoners:
      if not summoner.user_id:
        self.response.out.write('Id is missing to summoner: %s<br/>' %
                                summoner.name)
        continue
      # Updates summoner tier.
      if summoner.user_id not in id_to_tier:
        # Do not delete because it can be an ACL issue.
        self.response.out.write(
            'Deletes player having no rank record, %s.<br/>' % summoner.name)
        summoner.key.delete()
        continue
      # Updates summoner tier.
      summoner.tier = id_to_tier[summoner.user_id]
      self.response.out.write('Updated tier, %s is %s.<br/>' %
                              (summoner.name, summoner.tier))
      if (summoner.tier not in tier_sort_score or
          tier_sort_score[summoner.tier] < tier_cut_off):
        self.response.out.write('Deletes low ranked player, %s (%s).<br/>' %
                                (summoner.name, summoner.tier))
        # Deletes players lower than PLATINUM.
        # The matches still can contain records for non PLATINUM users.
        # This records are for PLATINUM and who played againt PLATINUM,
        # who maybe are high rators in GOLD tier.
        summoner.key.delete()
        continue

      # Only fetches up to 500+ matches per execution.
      # We can update only 500 matches per 10 minutes.
      if count > 500:
        summoner.put()  # Just records new tier.
        continue

      # Fetchs match detail.
      time_cut = (datetime.datetime.now() -  # Weeks ago.
                  datetime.timedelta(days=7)).strftime('%s')
      url = url_find_matches % (summoner.user_id, time_cut)
      self.response.out.write('Fetch url: %s<br/>' % url)
      result = urlfetch.fetch(url)
      if result.status_code == 200:
        rc = json.loads(result.content)
        if 'matches' not in rc:
          summoner.key.delete()
          self.response.out.write(
              'Deleted summoner having no matches recently, %s<br/>' %
              summoner.name)
          continue
        for match in rc['matches']:
          # Skips non rank solo games.
          if match['queue'] != rank_game_id:
            continue
          # Skips already existing matches.
          if Matchup.query(Matchup.match_id==match['matchId']).count() > 0:
            continue
          matchup = Matchup(match_id = match['matchId'])
          matchup.put()
          count += 1
        summoner.last_update = datetime.datetime.now()
        self.response.out.write('Found new matches for %s, count = %d.<br/>' % (
            summoner.name, count))
      elif result.status_code == 429:
        self.response.out.write('Rate limit exceeded.<br/>')
        time.sleep(3)  # Sleeps 3 seconds to avoid ACL.
      else:
        summoner.key.delete()
        self.response.out.write('Deleted summoner with match error: %s<br/>' %
                                summoner.name)
      summoner.put()

class ShowMatches(webapp2.RequestHandler):
  """ Shows matches up to 1000. """
  def get(self):
    response = ''
    self.response.out.write('Totoal %d matches<br/>' % Matchup.query().count())
    matchups = Matchup.query().fetch(1000)
    for matchup in matchups:
      if not matchup.match_creation:
        response += 'Id: %d, match is not updated.<br />' % matchup.match_id
      else:
        response += (
            'Id: %d, Time: %s, Win(T,M,J,BC,BS): %s,%s,%s,%s,%s ' +
            'Lose: %s,%s,%s,%s,%s<br />') % (
                matchup.match_id,
                time.gmtime(matchup.match_creation / 1000),
                matchup.top_win, matchup.middle_win, matchup.jungle_win,
                matchup.bottom_duo_carry_win, matchup.bottom_duo_support_win,
                matchup.top_lose, matchup.middle_lose, matchup.jungle_lose,
                matchup.bottom_duo_carry_lose, matchup.bottom_duo_support_lose)
    self.response.out.write(response)

class UpdateMatchesCron(webapp2.RequestHandler):
  """ Launches 5 match update job for every 10 seconds.

  App cron supports 1 minutes, but ACL is controlled by 10 seconds.
  To maximize the ACL, launch 5 workers for each cron call (once per minutes).
  """
  def get(self):
    for i in xrange(5):
      try:
        self.response.out.write('Scheduling match update %d<br/>' % i)
        taskqueue.add(url = '/update_matches',
                      countdown = i * 10)
      except (taskqueue.TaskAlreadyExistsError, taskqueue.TombstonedTaskError), e:
        self.response.out.write('taskqueue exception on %d<br/>' % i)
      except:
        self.response.out.write('Unknown excpetion on %d<br/>' % i);
    self.response.out.write('Succeeded!<br/>');

class UpdateMatches(webapp2.RequestHandler):
  """ Fills detail of games. """
  def create_db_string(self, lane, role, win, champion):
    attr = lane
    if lane == 'BOTTOM':
      attr += ('_' + role)
    attr += '_WIN' if win else '_LOSE'
    return 'matchup.%s = %d' % (attr.lower(), champion)

  def get_attr_str(self, lane, role, win):
    attr = lane
    if lane == 'BOTTOM':
      attr += ('_' + role)
    attr += '_WIN' if win else '_LOSE'
    return attr.lower()

  def get(self):
    # Updates lane win/lose records.
    matchups = Matchup.query(Matchup.match_creation == None).fetch(10)
    summoner_name_id = {}
    for matchup in matchups:
      url = url_update_match % matchup.match_id
      self.response.out.write('Fetch url: %s<br/>' % url)
      result = urlfetch.fetch(url)
      if result.status_code == 200:
        rc = json.loads(result.content)
        for participant in rc['participants']:
          attr = self.get_attr_str(
              participant['timeline']['lane'], participant['timeline']['role'],
              participant['stats']['winner'])
          champ = participant['championId']
          stats = participant['stats']
          items = '%d %d %d %d %d %d' % (
              stats['item0'], stats['item1'], stats['item2'],
              stats['item3'], stats['item4'], stats['item5'])
          self.response.out.write('%s = %s, items(%s)<br/>' % (attr, champ, items))
          setattr(matchup, attr, champ)
          setattr(matchup, attr + '_items', items)
        matchup.match_creation = rc['matchCreation']
        matchup.put()

        # Store summoners.
        for p in rc['participantIdentities']:
          summoner_name_id[
              p['player']['summonerName']] = p['player']['summonerId']
      elif result.status_code == 429:
        self.response.out.write('Rate limit exceeded.<br/>')
        time.sleep(3)  # Sleeps 3 seconds to avoid ACL.
      else:
        matchup.key.delete()
    # Updates new summoners.
    for name, user_id in summoner_name_id.iteritems():
      if Summoner.query(Summoner.name == name).count() > 0:
        self.response.out.write('Summoner %s is already in DB.<br>' % name)
        continue
      summoner = Summoner(name=name)
      summoner.user_id = user_id
      summoner.put()
      self.response.out.write(
          'Added %s(%s) to Summoner DB.<br>' % (name, user_id))

  def post(self):
    # Called by taskqueue.
    self.get()

class ShowLane(webapp2.RequestHandler):
  """ Shows win/lose statistics per champion.

  If only lane is given, show win/lose stats for all lane champions.
  If both of lane and champ are given, show stats for champ vs champ.
  ex)
  http://localhost:8080/lane?lane=top&champ=쉔
  http://localhost:8080/lane?lane=middle
  http://localhost:8080/lane?lane=jungle
  http://localhost:8080/lane?lane=bottom_duo_carry&champ=베인
  http://localhost:8080/lane?lane=bottom_duo_support
  """
  def get(self):
    lane = self.request.get("lane")
    if not lane:
      self.response.out.write(
          'Select lane, top, middle, jungle, ' +
          'bottom_duo_carry or bottom_duo_support.')
      return
    self.response.out.write(
        '<head><script src="js/sorttable.js"></script></head><body>')

    db_key = lane
    champ = self.request.get("champ")
    if champ:
      for id, name in champ_mappings.champ_name_map.iteritems():
        if champ == name:
          db_key = '%s_%s' % (lane, id)
          break

    cache = ResultCache.query(ResultCache.request == db_key).fetch(1)
    if len(cache) >= 1:
      self.response.out.write(cache[0].response)
    else:
      self.response.out.write('DB not found.')

class PrintChampions(webapp2.RequestHandler):
  """ Prints champion names map in Python code format. """
  def get(self):
    response = ''
    # Gets featured games.
    result = urlfetch.fetch(url_champion)
    if result.status_code == 200:
      rc = json.loads(result.content)
      champ_id_name = {}
      champ_id_key = {}
      for value in rc['data'].values():
        id = value['id']
        key = value['key']
        name = value['name']
        champ_id_name[id] = name
        champ_id_key[id] = key
      self.response.out.write('Name map<br/>')
      for id, name in champ_id_name.iteritems():
        self.response.out.write(
            '&nbsp;&nbsp;%d : \'%s\',<br/>' % (id, name))
      self.response.out.write('Key map<br/>')
      for id, key in champ_id_key.iteritems():
        self.response.out.write(
            '&nbsp;&nbsp;%d : \'%s\',<br/>' % (id, key))
    else:
      self.response.out.write(result.status_code)

class CleanUpMatchesCron(webapp2.RequestHandler):
  """ Cleans up matches older than 2 weeks. """
  def get(self):
    # Will invoke post().
    taskqueue.add(url = '/cleanup_matches')
    self.response.out.write('Launched a backend cleanup task.')

class CleanUpMatches(webapp2.RequestHandler):
  """ Cleans up matches older than 3 weeks. """
  def get(self):
    self.response.out.write('Cleaning old matches<br/>')
    time_cut = (datetime.datetime.now() -
                datetime.timedelta(days=14)).strftime('%s') + '000'
    curs = Cursor()
    while True:
      # Breaks down the record into pieces to avoid timeout.
      try:
        matchups, curs, more = Matchup.query().fetch_page(5000, start_cursor=curs)
      except:
        self.response.out.write('Stopped cleaning job on exception.<br/>')
        break
      for matchup in matchups:
        if matchup.match_creation != None and matchup.match_creation < int(time_cut):
          self.response.out.write('Found old match, %s, %s<br>' % (
              matchup.match_id, time.gmtime(matchup.match_creation / 1000)))
          matchup.key.delete()
      if not(more and curs):
        break

  def post(self):
    # Called by taskqueue.
    self.get()

class ResultCache(ndb.Model):
  """ DB model for result pages.
  Type of request,
    '/': main
    'top' : lane=top
    'top_1' : lane=top&champ=1
  """
  request = ndb.StringProperty()
  response = ndb.TextProperty()
  last_update = ndb.DateTimeProperty()

class BuildResultPages(webapp2.RequestHandler):
  """ Build result pages and store to cache DB. """
  def get(self):
    self.BuildSummonersPage()
    analyzed = self.AnalyzeMatches()
    self.BuildMainPage(analyzed)

  def BuildMainPage(self, analyzed):
    response = (
        '<br/>Welcome to LOL stats, select lane to see.<br/><br/>'
        '<a href="/lane?lane=top">Top</a><br/>'
        '<a href="/lane?lane=jungle">Jungle</a><br/>'
        '<a href="/lane?lane=middle">Middle</a><br/>'
        '<a href="/lane?lane=bottom_duo_carry">Bottom Dou Carry</a><br/>'
        '<a href="/lane?lane=bottom_duo_support">Bottom Dou Support</a><br/>')
    response += (
        '<br/>Collected %d KR summoners '
        'and analyzed %d / %d DIAMOND+ matches.<br/>' %
        (Summoner.query().count(), analyzed, Matchup.query().count()))
    response += self.GetTimestamp()

    self.AddOrUpdateResponse('/', response)
    self.response.out.write('Built main page.<br/>')

  def AnalyzeMatches(self):
    lanes = ['top', 'middle', 'jungle',
             'bottom_duo_carry', 'bottom_duo_support']

    champ_games = defaultdict(lambda: defaultdict(int))
    champ_win = defaultdict(lambda: defaultdict(int))
    champ_vs_games = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    champ_vs_win = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    champ_items = defaultdict(lambda: defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))))

    self.response.out.write('Analyzing all matches...<br/>')
    analyzed = 0
    curs = Cursor()
    while True:
      # Breaks down the record into pieces to avoid timeout.
      matchups, curs, more = (
          Matchup.query().fetch_page(5000, start_cursor=curs))
      for matchup in matchups:
        if not matchup.match_creation:
          continue
        analyzed += 1
        for lane in lanes:
          win_champ = getattr(matchup, '%s_win' % lane)
          lose_champ = getattr(matchup, '%s_lose' % lane)
          champ_games[lane][win_champ] += 1
          champ_games[lane][lose_champ] += 1
          champ_win[lane][win_champ] += 1
          champ_vs_games[lane][win_champ][lose_champ] += 1
          champ_vs_games[lane][lose_champ][win_champ] += 1
          champ_vs_win[lane][win_champ][lose_champ] += 1
          win_items = getattr(matchup, '%s_win_items' % lane)
          if win_items:
            for win_item in win_items.split():
              if win_item != '0':
                champ_items[lane][win_champ][lose_champ][win_item] += 1
          lose_items = getattr(matchup, '%s_lose_items' % lane)
          if lose_items:
            for lose_item in lose_items.split():
              if lose_item != '0':
                champ_items[lane][lose_champ][win_champ][lose_item] += 1
      if not(more and curs):
        break
    for lane in lanes:
      self.BuildLanePage(lane, champ_games[lane], champ_win[lane])
    for lane in lanes:
      for champ in champ_vs_games[lane]:
        self.BuildLaneChampPage(
            lane, champ, champ_games[lane][champ], champ_win[lane][champ],
            champ_vs_games[lane][champ], champ_vs_win[lane][champ],
            champ_items[lane][champ])
    return analyzed

  def BuildLanePage(self, lane, champ_games, champ_win):
    response = (
        '<table class="sortable"><thead><tr><th>Champ</th><th>Games</th>'
        '<th>Win</th><th>Lose</th><th>Ratio</th></tr></thead><tbody>')
    for champ in sorted(champ_games, key=champ_games.get, reverse=True):
      if not champ:
        continue
      games = champ_games[champ]
      win = champ_win[champ]
      lose = games - win
      ratio = float(win * 100) / games
      color = 'blue' if ratio >= 50 else 'red'
      response += (
          '<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td>'
          '<td><font color=%s>%0.1f%%</font></td></tr>'
          % (self.ChampWithLink(lane, champ), games, win, lose, color, ratio))
    response += ('</tbody></table>')
    response += self.GetTimestamp()
    response += ('</body></html>')

    self.AddOrUpdateResponse(lane, response)
    self.response.out.write('Built page for lane %s.<br/>' % lane)

  def BuildLaneChampPage(self, lane, champ, games, win, champ_games,
                         champ_win, champ_items):
    if champ not in champ_mappings.champ_name_map:
      return
    # TODO: use style sheet.
    response = (
        '<table class="sortable"><thead><tr><th>Against</th><th>Games</th>'
        '<th>Win</th><th>Lose</th><th>Ratio</th><th>Popular items</th></tr>'
        '</thead><tbody>'
        '<div style="display: inline-block; vertical-align: middle">'
        '<img src="%s" width=40 height=40 /></div>&nbsp;'
        '<div style="display: inline-block; vertical-align: middle">'
        'Champ: %s (%s) Games: %d Win: %d Lose: %d Ratio: %0.1f%%</div>'
        '<br/><br/>' %
        (champ_mappings.GetChampImage(champ),
         champ_mappings.GetChampName(champ), lane,
         games, win, games - win, float(win * 100) / games))
    for against in sorted(champ_games, key=champ_games.get, reverse=True):
      if not against:
        continue
      games = champ_games[against]
      win = champ_win[against]
      lose = games - win
      ratio = float(win * 100) / games
      color = 'blue' if ratio >= 50 else 'red'
      items = champ_items[against]
      sorted_items = [x[0] for x in sorted(
          items.items(), key=itemgetter(1), reverse=True)][:14]
      item_str = ''
      for item in sorted_items:
        # TODO: add tooltip.
        item_str += (
            ('<img src="' + url_item_image_tpl + '" width=20 height=20 />') %
            item)
      response += (
          '<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td>'
          '<td><font color=%s>%0.1f%%</font></td><td>%s</td></tr>'
          % (self.ChampWithLink(lane, against), games, win, lose,
             color, ratio, item_str))
    response += ('</tbody></table>')
    response += self.GetTimestamp()
    response += ('</body></html>')

    self.AddOrUpdateResponse('%s_%s' % (lane, champ), response)
    self.response.out.write(
        'Built page for lane %s, champ %s.<br/>' %
        (lane, champ_mappings.GetChampName(champ)))

  def BuildSummonersPage(self):
    tier_to_collect = ['CHALLENGER', 'MASTER', 'DIAMOND', 'PLATINUM']
    tier_count = defaultdict(int)
    for cur_tier in tier_to_collect:
      curs = Cursor()
      while True:
        # Breaks down the record into pieces to avoid timeout.
        summoners, curs, more = (
            Summoner.query(Summoner.tier == cur_tier).
            fetch_page(5000, keys_only=True, start_cursor=curs))
        tier_count[cur_tier] += len(summoners)
        if not(more and curs):
          break
    response = 'Totoal %d summoners<br/>' % Summoner.query().count()
    for tier in tier_count:
      response += 'Tier: %s Count: %d<br/>' % (tier, tier_count[tier])

    response += self.GetTimestamp()
    summoners = Summoner.query().order(Summoner.name).fetch(1000)
    for summoner in summoners:
      response += (
          'Name: %s, Id: %s, Tier: %s, Updated: %s<br/>' % (
          summoner.name, summoner.user_id, summoner.tier,
          summoner.last_update))
    self.AddOrUpdateResponse('summoners', response)
    self.response.out.write('Built summoners page.<br/>')

  def AddOrUpdateResponse(self, request, response):
    cache = ResultCache.query(ResultCache.request == request).fetch(1)
    if len(cache) < 1:
      cache = [ResultCache(request=request)]
    cache[0].response = response
    cache[0].put()

  def ChampWithLink(self, lane, champ):
    name = champ_mappings.GetChampName(champ)
    img = champ_mappings.GetChampImage(champ)
    return ('<div style="display: inline-block; vertical-align: middle">'
            '<img src="%s" width=20 height=20 /></div> '
            '<div style="display: inline-block; vertical-align: middle">'
            '<a href="/lane?lane=%s&champ=%s">%s</a></div>' %
            (img, lane, name, name))

  def GetTimestamp(self):
    return ('<br/>Updated: %s<br/><br/>' %
            datetime.datetime.now().strftime('%Y-%m-%d %H:%M') +
            'Lol stats isn\'t endorsed by Riot Games and doesn\'t reflect '
            'the views or opinions of Riot Games or anyone officially involved '
            'in producing or managing League of Legends. League of Legends and '
            'Riot Games are trademarks or registered trademarks of Riot Games, '
            'Inc. League of Legends © Riot Games, Inc.<br/>')
  
  def post(self):
    # Called by taskqueue.
    self.get()

class BuildResultPagesCron(webapp2.RequestHandler):
  """ Launches a BuildResultPages task. """
  def get(self):
    try:
      self.response.out.write('Scheduling build result page.<br/>')
      taskqueue.add(url = '/build_result_pages')
    except (taskqueue.TaskAlreadyExistsError, taskqueue.TombstonedTaskError), e:
      self.response.out.write('taskqueue exception<br/>')
    except:
      self.response.out.write('Unknown excpetion<br/>');
    self.response.out.write('Succeeded!<br/>');

class RiotVerification(webapp2.RequestHandler):
  """ File for riot verification. """
  def get(self):
    self.response.out.write('cab94386-2391-467e-9457-7ed5d1abffe7')

class Main(webapp2.RequestHandler):
  """ Main links. """
  def get(self):
    cache = ResultCache.query(ResultCache.request == '/').fetch(1)
    if len(cache) >= 1:
      posters_bar = ''
      champ_posters = set()
      while len(champ_posters) < 5:
        champ_posters.add(champ_mappings.GetRandomChampPoster())
      for poster in champ_posters:
        posters_bar += '<img src="%s" width=154 height=280 />' % poster
      self.response.out.write('%s<br/>%s' % (posters_bar, cache[0].response))

app = webapp2.WSGIApplication([
  # Crawl commands.
  ('/seed', Seed),  # Find seed summoners from featured games.
  ('/find_matches', FindMatches),
  ('/update_matches_cron', UpdateMatchesCron),
  ('/update_matches', UpdateMatches), # Used internally.
  # Analyze commands.
  ('/build_result_pages_cron', BuildResultPagesCron),
  ('/build_result_pages', BuildResultPages),
  # Internal tools.
  ('/summoners', ShowSummoners),
  ('/matches', ShowMatches),
  ('/champions', PrintChampions),
  ('/cleanup_summoners', CleanupSummoners), # Remove when stable.
  ('/cleanup_matches_cron', CleanUpMatchesCron),
  ('/cleanup_matches', CleanUpMatches),
  # Statistics per lane.
  ('/', Main),
  ('/lane', ShowLane),
  ('/riot.txt', RiotVerification),
], debug=True)
