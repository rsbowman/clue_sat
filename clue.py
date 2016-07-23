from __future__ import print_function

import sys
import itertools as it
from collections import defaultdict

import numpy as np

from game import GameType, Game, ClueActStrategy, SmartEndturnStrategy, \
    SmartSuggestionStrategy, DumbEndturnStrategy, RealSmartSuggestionStrategy

"""
The main function for playing Clue-like card games and Clue itself (at least
the version I own).  A "color card" version of clue is included to simulate
games in which every player has the same number of cards.  I wanted to answer
some basic questions about game statistics, like the average number of rounds,
so there's a class for that.  Most of the important stuff is in game.py.
"""

clue_card_dict = {
    "people": ["ProfPlum", "MissScarlett", "ColMustard", "MrGreen", "MrsPeacock", "MsWhite"],
    "weapons": ["knife", "cdstick", "rope", "revolver", "wrench", "pipe"],
    "rooms": ["kitchen", "ballroom", "conservatory", "billiard", "lounge",
              "study", "hall", "library", "dining"]
    }

def clue_cards(n):
    cards = {}
    for key in clue_card_dict:
        cards[key] = clue_card_dict[key][:n]
    return cards

class C:
    ProfPlum = clue_card_dict["people"][0]
    MissScarlett = clue_card_dict["people"][1]
    ColMustard = clue_card_dict["people"][2]
    MrGreen = clue_card_dict["people"][3]
    MrsPeacock = clue_card_dict["people"][4]
    MrsWhite = clue_card_dict["people"][5]

    knife = clue_card_dict["weapons"][0]
    candlestick = clue_card_dict["weapons"][1]
    rope = clue_card_dict["weapons"][2]
    revolver = clue_card_dict["weapons"][3]
    wrench = clue_card_dict["weapons"][4]
    # pipe = clue_card_dict["weapons"][5]

    kitchen = clue_card_dict["rooms"][0]
    ballroom = clue_card_dict["rooms"][1]
    lounge = clue_card_dict["rooms"][2]
    study = clue_card_dict["rooms"][3]
    parlor = clue_card_dict["rooms"][4]
    library = clue_card_dict["rooms"][5]

class CC:
    red1 = "red1"
    red2 = "red2"
    red3 = "red3"
    red4 = "red4"
    red5 = "red5"

    blue1 = "blue1"
    blue2 = "blue2"
    blue3 = "blue3"
    blue4 = "blue4"
    blue5 = "blue5"

    green1 = "green1"
    green2 = "green2"
    green3 = "green3"
    green4 = "green4"
    green5 = "green5"

def color_cards(n_colors, n_cards):
    colors = ["red", "blue", "green", "yellow"]
    cards = {}
    for color in colors[:n_colors]:
        cards[color] = []
        for i in range(n_cards):
            cards[color].append("{}{}".format(color, i + 1))
    return cards

class Stats(object):
    def __init__(self):
        self.last_common_known_cards = {}
        self.turns = []
        self.known_by_entity = defaultdict(list)

    def common_known_cards(self, game):
        known_cards = {}
        for e in game.entities():
            card_probs = game.observer.card_probs(e)
            known_cards[e] = [c for c, p in card_probs.items() if p == 1.0]

        self.last_common_known_cards = known_cards

    def end_game(self, turn):
        self.turns.append(turn)
        for e in self.last_common_known_cards:
            self.known_by_entity[e].append(len(self.last_common_known_cards[e]))

    def report(self):
        print("Games lasted average of {:.2f} turns, std. dev {:.2f}, median {}".format(
            np.mean(self.turns), np.std(self.turns), np.median(self.turns)))
        print("Common knowledge:")
        for e, n_cards in self.known_by_entity.items():
            print("  Knew {:.2f} cards of {}; std. {:.2f}".format(
                np.average(n_cards), e, np.std(n_cards)))

def play_clue(players, n_rounds):
    play_c(players, clue_card_dict, n_rounds)

def play_colors(players, n_types, n_cards, n_rounds):
    cards = color_cards(n_card_types, n_cards)
    play_c(players, cards, n_rounds)

def play_clue_strategy(players, n_rounds):
    def make_game(game_type, deal):
        g = Game(game_type, deal)
        for name in players:
            p = g.get_player(name)
            p.set_act_strategy(ClueActStrategy)
            p.set_endturn_strategy(DumbEndturnStrategy) # SmartEndturnStrategy)
            p.set_suggestion_strategy(SmartSuggestionStrategy)

        p = g.get_player(players[0])
        p.set_suggestion_strategy(RealSmartSuggestionStrategy)
        return g

    play_c(players, clue_card_dict, n_rounds, make_game)

def play_c(players, cards, n_rounds, make_game=lambda typ, deal: Game(typ, deal)):
    secret, wins = "secret", defaultdict(int)
    stats = Stats()

    for n in range(n_rounds):
        print("================= Game {} =================".format(n + 1))
        game_type = GameType(players, secret, cards)
        deal = game_type.deal(n)

        game = make_game(game_type, deal)

        print("Secret cards: {}".format(", ".join(deal[secret])))
        for p in players:
            print("{} cards: {}".format(p, ", ".join(deal[p])))
        print()

        player_stream = it.cycle(players)
        for i in range(len(players) - 1 - (n % len(players))): # alternate beginning player
            player_stream.next()

        for i, p in enumerate(player_stream):
            print("turn {:>3}, game {:>3} {}".format(i + 1, n, "-"*30))
            stats.common_known_cards(game)
            if not game.turn(p):
                stats.end_game(i + 1)
                wins[p] += 1
                break
        print(", ".join(("{} has {} wins".format(p, wins[p]) for p in players))
              + " out of {} games".format(n + 1))
    stats.report()

def main(argv):
    """
    possibly interesting games to play (?)

    # 3 card types
    print i, cs(3, i), factors(cs(3, i))
    ....:
    3 6 [1, 2, 3, 6]
    4 9 [1, 3, 9]
    5 12 [1, 2, 3, 4, 6, 12]
    6 15 [1, 3, 5, 15]
    7 18 [1, 2, 3, 6, 9, 18]
    8 21 [1, 3, 7, 21]
    9 24 [1, 2, 3, 4, 6, 8, 12, 24]

    # 4 card types
    In [30]: for i in range(3, 10):
        print i, cs(4, i), factors(cs(4, i))
    ....:
    3 8 [1, 2, 4, 8]
    4 12 [1, 2, 3, 4, 6, 12]
    5 16 [1, 2, 4, 8, 16]
    6 20 [1, 2, 4, 5, 10, 20]
    7 24 [1, 2, 3, 4, 6, 8, 12, 24]
    8 28 [1, 2, 4, 7, 14, 28]
    9 32 [1, 2, 4, 8, 16, 32]

    """
    players = ["P1", "P2", "P3", "P4", "P5"]

    play_clue_strategy(players[:3], 50)
    play_clue_strategy(players[:4], 50)
    play_clue_strategy(players[:5], 50)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
