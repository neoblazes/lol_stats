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
from google.appengine.ext import ndb
from google.appengine.api import urlfetch
from google.appengine.api import users

import sys
reload(sys)
sys.setdefaultencoding('utf-8')

riot_api_host = 'https://kr.api.pvp.net/'
# Get the api key by register to Riot developer,
# https://developer.riotgames.com/
riot_api_key = '?api_key=7ff24dff-48c7-4df8-883b-d08d4787fefc'

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

# This map is generated by '/champions' request.
champ_name_map = {
  1 : '애니',
  2 : '올라프',
  3 : '갈리오',
  4 : '트위스티드 페이트',
  5 : '신 짜오',
  6 : '우르곳',
  7 : '르블랑',
  8 : '블라디미르',
  9 : '피들스틱',
  10 : '케일',
  11 : '마스터 이',
  12 : '알리스타',
  13 : '라이즈',
  14 : '사이온',
  15 : '시비르',
  16 : '소라카',
  17 : '티모',
  18 : '트리스타나',
  19 : '워윅',
  20 : '누누',
  21 : '미스 포츈',
  22 : '애쉬',
  23 : '트린다미어',
  24 : '잭스',
  25 : '모르가나',
  26 : '질리언',
  27 : '신지드',
  28 : '이블린',
  29 : '트위치',
  30 : '카서스',
  31 : '초가스',
  32 : '아무무',
  33 : '람머스',
  34 : '애니비아',
  35 : '샤코',
  36 : '문도 박사',
  37 : '소나',
  38 : '카사딘',
  39 : '이렐리아',
  40 : '잔나',
  41 : '갱플랭크',
  42 : '코르키',
  43 : '카르마',
  44 : '타릭',
  45 : '베이가',
  48 : '트런들',
  50 : '스웨인',
  51 : '케이틀린',
  53 : '블리츠크랭크',
  54 : '말파이트',
  55 : '카타리나',
  56 : '녹턴',
  57 : '마오카이',
  58 : '레넥톤',
  59 : '자르반 4세',
  60 : '엘리스',
  61 : '오리아나',
  62 : '오공',
  63 : '브랜드',
  64 : '리 신',
  67 : '베인',
  68 : '럼블',
  69 : '카시오페아',
  72 : '스카너',
  74 : '하이머딩거',
  75 : '나서스',
  76 : '니달리',
  77 : '우디르',
  78 : '뽀삐',
  79 : '그라가스',
  80 : '판테온',
  81 : '이즈리얼',
  82 : '모데카이저',
  83 : '요릭',
  84 : '아칼리',
  85 : '케넨',
  86 : '가렌',
  89 : '레오나',
  90 : '말자하',
  91 : '탈론',
  92 : '리븐',
  96 : '코그모',
  98 : '쉔',
  99 : '럭스',
  101 : '제라스',
  102 : '쉬바나',
  103 : '아리',
  104 : '그레이브즈',
  105 : '피즈',
  106 : '볼리베어',
  107 : '렝가',
  110 : '바루스',
  111 : '노틸러스',
  112 : '빅토르',
  113 : '세주아니',
  114 : '피오라',
  115 : '직스',
  117 : '룰루',
  119 : '드레이븐',
  120 : '헤카림',
  121 : '카직스',
  122 : '다리우스',
  126 : '제이스',
  127 : '리산드라',
  131 : '다이애나',
  133 : '퀸',
  134 : '신드라',
  143 : '자이라',
  150 : '나르',
  154 : '자크',
  157 : '야스오',
  161 : '벨코즈',
  201 : '브라움',
  222 : '징크스',
  223 : '탐 켄치',
  236 : '루시안',
  238 : '제드',
  245 : '에코',
  254 : '바이',
  266 : '아트록스',
  267 : '나미',
  268 : '아지르',
  412 : '쓰레쉬',
  421 : '렉사이',
  429 : '칼리스타',
  432 : '바드',
    }

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
    self.response.out.write('Totoal %d summoners<br/>' %
                            Summoner.query().count())
    summoners = Summoner.query().order(Summoner.name)
    for summoner in summoners:
      self.response.out.write(
          'Name: %s, Id: %s, Tier: %s, Updated: %s<br/>' % (
          summoner.name, summoner.user_id, summoner.tier,
          summoner.last_update))

class CleanupSummoners(webapp2.RequestHandler):
  """ Removes duplicated summoners. """
  def get(self):
    ndb.delete_multi(Summoner.query(
        Summoner.last_update == None).iter(keys_only=True))

    summoner_names = set()
    summoners = Summoner.query()
    for summoner in summoners:
      if summoner.name in summoner_names:
        summoner.key.delete()
        self.response.out.write('Deleted dup Name: %s<br/>' % summoner.name)
      else:
        summoner_names.add(summoner.name)

class Matchup(ndb.Model):
  """ DB model for matchups. """
  match_id = ndb.IntegerProperty()
  match_creation = ndb.IntegerProperty()
  # Chanpions per lane.
  top_win = ndb.IntegerProperty()
  top_lose = ndb.IntegerProperty()
  middle_win = ndb.IntegerProperty()
  middle_lose = ndb.IntegerProperty()
  jungle_win = ndb.IntegerProperty()
  jungle_lose = ndb.IntegerProperty()
  bottom_duo_carry_win = ndb.IntegerProperty()
  bottom_duo_carry_lose = ndb.IntegerProperty()
  bottom_duo_support_win = ndb.IntegerProperty()
  bottom_duo_support_lose = ndb.IntegerProperty()

class FindMatches(webapp2.RequestHandler):
  """ Finds matches by listing games for summoners.

  The summoners to be updated are selected by LRU.
  It only gets game IDs. The detail of games will be filled by UpdateMatches().
  It will do nothing if there are more than 1000 games waiting for 'update'.
  """
  def get(self):
    not_updated_matchups = Matchup.query(
        Matchup.match_creation == None).fetch(1000)
    if len(not_updated_matchups) >= 1000:
      self.response.out.write(
          'More than 1000 matches are waiting for update. ' +
          'Will not find more.<br/>');
      return

    summoners = Summoner.query(
        ndb.OR(Summoner.last_update == None,
               Summoner.last_update < (
                   datetime.datetime.now() - datetime.timedelta(hours=24))
               )).fetch(10)
    if not summoners:
      self.response.out.write('No summoner to update match.');
      return

    # Updates summoners' tiers.
    url = url_summoner_detail_by_id % (
        ','.join(str(summoner.user_id) for summoner in summoners))
    self.response.out.write('Fetch url: %s<br/>' % url)
    result = urlfetch.fetch(url)
    if result.status_code == 200:
      rc = json.loads(result.content)
      for key in rc:
        for league in rc[key]:
          if league['queue'] == 'RANKED_SOLO_5x5':
            summoners_to_update = Summoner.query(Summoner.user_id==int(key))
            for s in summoners_to_update:
              s.tier = league['tier']
              s.put()
            break

    # Find matchs.
    count = 0
    for summoner in summoners:
      if not summoner.user_id:
        self.response.out.write('Id is missing to summoner: %s<br/>' %
                                summoner.name)
        continue
      # TODO: Check summoner tier.
      # Delete if the tier is lower than some criteria.

      # Fetchs match detail.
      time_cut = (datetime.datetime.now() -  # Weeks ago.
                  datetime.timedelta(days=7)).strftime('%s')
      url = url_find_matches % (summoner.user_id, time_cut)
      self.response.out.write('Fetch url: %s<br/>' % url)
      result = urlfetch.fetch(url)
      if result.status_code == 200:
        rc = json.loads(result.content)
        if not rc['matches']:
          summoner.key.delete()
          self.response.out.write(
              'Deleted summoner having no matches recently<br/>' %
              summoner.name)
          continue
        for match in rc['matches']:
          # Skips already existing matches.
          if Matchup.query(Matchup.match_id==match['matchId']):
            continue
          matchup = Matchup(match_id = match['matchId'])
          matchup.put()
          count += 1
        summoner.last_update = datetime.datetime.now()
        summoner.put()
        self.response.out.write('Updated summoner %s, count = %d.<br/>' % (
            summoner.name, count))
      elif result.status_code == 429:
        self.response.out.write('Rate limit exceeded.<br/>')
        time.sleep(10)  # Sleeps 10 seconds to avoid ACL.
      else:
        summoner.key.delete()
        self.response.out.write('Deleted summoner with match error: %s<br/>' %
                                summoner.name)
      # Only fetches up to 2000+ matches per execution.
      # We can update only 500 matches per 10 minutes.
      if count > 500:
        break

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

class UpdateMatches(webapp2.RequestHandler):
  """ Fills detail of games. """
  def create_db_string(self, lane, role, win, champion):
    attr = lane
    if lane == 'BOTTOM':
      attr += ('_' + role)
    attr += '_WIN' if win else '_LOSE'
    return 'matchup.%s = %d' % (attr.lower(), champion)

  def get(self):
    # Updates lane win/lose records.
    matchups = Matchup.query(Matchup.match_creation == None).fetch(40)
    summoner_name_id = {}
    for matchup in matchups:
      url = url_update_match % matchup.match_id
      self.response.out.write('Fetch url: %s<br/>' % url)
      result = urlfetch.fetch(url)
      if result.status_code == 200:
        rc = json.loads(result.content)
        for participant in rc['participants']:
          cmd = self.create_db_string(
              participant['timeline']['lane'], participant['timeline']['role'],
              participant['stats']['winner'], participant['championId'])
          self.response.out.write('%s<br/>' % cmd)
          exec cmd
        matchup.match_creation = rc['matchCreation']
        matchup.put()

        # Store summoners.
        for p in rc['participantIdentities']:
          summoner_name_id[
              p['player']['summonerName']] = p['player']['summonerId']
      elif result.status_code == 429:
        self.response.out.write('Rate limit exceeded.<br/>')
        time.sleep(10)  # Sleeps 10 seconds to avoid ACL.
      else:
        matchup.key.delete()
    # TODO: Updates new summoners.
    for name, user_id in summoner_name_id.iteritems():
      found = Summoner.query(Summoner.name == name).fetch(1)
      if found:
        self.response.out.write('Summoner %s is already in DB.<br>' % name)
        continue
      summoner = Summoner(name=name)
      summoner.user_id = user_id
      summoner.put()
      self.response.out.write(
          'Added %s(%s) to Summoner DB.<br>' % (name, user_id))

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

    champ = self.request.get("champ")
    if champ:
      self.PrintChampDetail(lane, champ)
      return
    champ_games = {}
    champ_games = defaultdict(lambda: 0, champ_games)
    champ_win = {}
    champ_win = defaultdict(lambda: 0, champ_win)
    matchups = Matchup.query()
    for matchup in matchups:
      exec 'win_champ = matchup.%s_win' % lane
      exec 'lose_champ = matchup.%s_lose' % lane
      champ_games[win_champ] += 1
      champ_games[lose_champ] += 1
      champ_win[win_champ] += 1

    # Print champ stats.
    self.response.out.write(
        '<table class="sortable"><thead><tr><th>Champ</th><th>Games</th>'
        '<th>Win</th><th>Lose</th><th>Ratio</th></tr></thead><tbody>')
    for champ in sorted(champ_games, key=champ_games.get, reverse=True):
      if not champ:
        continue
      games = champ_games[champ]
      win = champ_win[champ]
      lose = games - win
      self.response.out.write(
          '<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td><td>%d%%</td></tr>'
          % (self.ChampWithLink(lane, champ), games, win, lose,
             (win * 100) / games))
    self.response.out.write('</tbody></table></body></html>')

  def PrintChampDetail(self, lane, champ_name):
    champ = None
    for id, name in champ_name_map.iteritems():
      if champ_name == name:
        champ = id
        break
    if not champ:
      self.response.out.write('Invalid champ name, %s != %s' % (champ_name, champ_name_map[98]))
      return
    champ_games = {}
    champ_games = defaultdict(lambda: 0, champ_games)
    win_against = {}
    win_against = defaultdict(lambda: 0, win_against)

    exec 'matchups = Matchup.query(Matchup.%s_win == %s)' % (lane, champ)
    for matchup in matchups:
      exec 'lose_champ = matchup.%s_lose' % lane
      champ_games[lose_champ] += 1
      win_against[lose_champ] += 1

    exec 'matchups = Matchup.query(Matchup.%s_lose == %s)' % (lane, champ)
    for matchup in matchups:
      exec 'win_champ = matchup.%s_win' % lane
      champ_games[win_champ] += 1

    # Print champ stats.
    self.response.out.write(
        '<table class="sortable"><thead><tr><th>Against</th><th>Games</th>'
        '<th>Win</th><th>Lose</th><th>Ratio</th></tr></thead><tbody>')
    for against in sorted(champ_games, key=champ_games.get, reverse=True):
      if not against:
        continue
      games = champ_games[against]
      win = win_against[against]
      lose = games - win
      self.response.out.write(
          '<tr><td>%s</td><td>%d</td><td>%d</td><td>%d</td><td>%d%%</td></tr>'
          % (self.ChampWithLink(lane, against), games, win, lose,
             (win * 100) / games))
    self.response.out.write('</tbody></table></body></html>')

  def ChampWithLink(self, lane, champ):
    name = champ_name_map[champ]
    return '<a href="/lane?lane=%s&champ=%s">%s</a>' % (lane, name, name)


class PrintChampions(webapp2.RequestHandler):
  """ Prints champion names map in Python code format. """
  def get(self):
    response = ''
    # Gets featured games.
    result = urlfetch.fetch(url_champion)
    if result.status_code == 200:
      rc = json.loads(result.content)
      champ_id_name = {}
      for value in rc['data'].values():
        id = value['id']
        name = value['name']
        champ_id_name[id] = name
      for id, name in champ_id_name.iteritems():
        self.response.out.write(
            '&nbsp;&nbsp;%d : \'%s\',<br/>' % (id, name))
    else:
      self.response.out.write(result.status_code)

class CleanUpMatches(webapp2.RequestHandler):
  """ Cleans up matches older than a week. """
  def get(self):
    time_cut = (datetime.datetime.now() -
                datetime.timedelta(days=7)).strftime('%s') + '000'
    old_matchups = Matchup.query(
        ndb.AND(Matchup.match_creation != None,
                Matchup.match_creation < int(time_cut)))
    for matchup in old_matchups:
      self.response.out.write('Found old match, %s, %s<br>' % (
          matchup.match_id, time.gmtime(matchup.match_creation / 1000)))
      matchup.key.delete()

class Main(webapp2.RequestHandler):
  """ Main links. """
  def get(self):
    self.response.out.write('Welcome to LOL stats, select lane to see.<br/>')
    self.response.out.write('<a href="/lane?lane=top">Top</a><br/>')
    self.response.out.write('<a href="/lane?lane=middle">Middle</a><br/>')
    self.response.out.write('<a href="/lane?lane=jungle">Jungle</a><br/>')
    self.response.out.write(
        '<a href="/lane?lane=bottom_duo_carry">Bottom Dou Carry</a><br/>')
    self.response.out.write(
        '<a href="/lane?lane=bottom_duo_support">Bottom Dou Support</a><br/>')
    self.response.out.write(
        'Collected %d summoners and %d/%d matches analyzed.<br/>' % (
            Summoner.query().count(),
            Matchup.query(Matchup.match_creation != None).count(),
            Matchup.query().count()))

app = webapp2.WSGIApplication([
  # Update commands.
  ('/seed', Seed),  # Find seed summoners from featured games.
  ('/find_matches', FindMatches),
  ('/update_matches', UpdateMatches),
  # Internal tools.
  ('/summoners', ShowSummoners),
  ('/matches', ShowMatches),
  ('/champions', PrintChampions),
  ('/cleanup_summoners', CleanupSummoners), # Remove when stable.
  ('/cleanup_matches', CleanUpMatches),
  # Statistics per lane.
  ('/', Main),
  ('/lane', ShowLane),
], debug=True)
