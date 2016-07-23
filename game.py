from __future__ import print_function

import itertools as it
import random
from collections import defaultdict

from pycryptosat import Solver

from prop import Symbol, And, Or, Not, onehot, at_least

"""

Stuff for "knowledge card games" like a stripped down version of Clue. The
`GameType` holds information about number of players, their names, the name of
the "secret" player that holds the hidden cards, the number of types of cards
and the cards themselves.

`SolverProxy` is our interface to cryptominisat. Objects of this type are
created by `GameType` and are able to say whether or not a particular game
state is consistent with some set of facts.

`PlayerState` models a player and uses the Strategy pattern to perform such
actions as making a suggestion, responding to a suggestion, and performing
special deductions at the end of another player's turn. Knowledge is
represented by a map of players to cards to real numbers in [0, 1]; this is
vestigial from when the program computed probabilities for player holding
certain cards. Now we use 1.0 to mean a player definitely has a card and
0.5 to mean the player might have the card.

`Suggestion` reifies a suggestion, refutations or lack thereof by players,
and the knowledge players obtain from such.

`Game` keeps the state of an actual game. It creates the player states, keeps
track of common knowledge, and allows the computer to play itself through the
`turn` method. Although the program used to support an "assistant mode"
interface for beating your friends and neighbors at Clue, it changed to
investigate games by having the computer play itself. It may or may not still
offer decent support for being a game playing assistant.

"""

def has(player, card):
    return "has_{}_{}".format(player, card)

## Actual game stuff
class GameType(object):
    def __init__(self, players, secret_name, cards_by_type):
        self.players = players
        self.secret_name = secret_name
        self.cards_by_type = cards_by_type
        self._all_cards = sum(cards_by_type.values(), [])
        self.next_index = -1
        self.basic_clauses = []

    def all_cards(self):
        return self._all_cards

    def card_type(self, card):
        for typ in self.cards_by_type:
            if card in self.cards_by_type[typ]:
                return typ

    def basic_constraint_clauses(self, player_n_cards):
        players, agents = self.players, self.players + [self.secret_name]

        owned_by_one = []
        for c in self.all_cards():
            owned_by_one.extend(onehot([has(a, c) for a in agents]))

        cardinality_constraints = []
        for p in players:
            player_cards = [has(p, c) for c in self.all_cards()]
            cardinality_constraints.extend(at_least(player_cards, player_n_cards[p]))

        secret_constraints = []
        for typ, cards in self.cards_by_type.items():
            secret_cards = [has(self.secret_name, c) for c in cards]
            secret_constraints.extend(onehot(secret_cards))

        return owned_by_one + cardinality_constraints + secret_constraints

    def deal(self, n=0):
        n_players = len(self.players)
        secret_cards, leftover_cards = [], []
        for typ in self.cards_by_type:
            typ_cards = self.cards_by_type[typ]
            cs = random.sample(typ_cards, len(typ_cards))
            secret_cards.append(cs[0])
            leftover_cards.extend(cs[1:])

        cards_by_player = defaultdict(list)
        cards_by_player[self.secret_name] = secret_cards

        random.shuffle(leftover_cards)
        player_stream = it.cycle(self.players)
        for i in range(n % len(self.players)):
            player_stream.next()

        for p, c in zip(player_stream, leftover_cards):
            cards_by_player[p].append(c)

        return cards_by_player

    def solver(self, player_n_cards, additional_facts=[]):
        if not self.basic_clauses:
            clauses = And(self.basic_constraint_clauses(player_n_cards))
            vars = sorted(set(clauses.vars()))
            self.var_to_int = dict(zip(vars, range(1, len(vars) + 1)))
            self.basic_clauses = list(clauses.cnf_clauses(self.var_to_int))

        solver = Solver(threads=6)

        for c in self.basic_clauses:
            solver.add_clause(c)

        for c in And(additional_facts).cnf_clauses(self.var_to_int):
            solver.add_clause(c)

        return SolverProxy(solver, self.var_to_int)

class SolverProxy(object):
    def __init__(self, solver, var_map):
        self.solver = solver
        self.var_map = var_map

    def add_clause(self, expr):
        if isinstance(expr, str):
            self.solver.add_clause([self.var_map[expr]])
        elif isinstance(expr, And):
            for c in expr.cnf_clauses(self.var_map):
                self.solver.add_clause(c)
        elif isinstance(expr, Symbol):
            self.solver.add_clause([expr.cnf_clause(self.var_map)])
        else:
            self.solver.add_clause(expr.cnf_clause(self.var_map))

    def _convert_arg(self, arg):
        if isinstance(arg, str):
            return self.var_map[arg]
        elif isinstance(arg, int):
            return arg
        elif isinstance(arg, Not):
            return -self.var_map[arg.clause.name]

    def _to_assumptions(self, arg):
        if arg is None:
            return []
        elif isinstance(arg, list):
            return [self._convert_arg(a) for a in arg]
        else:
            return [self._convert_arg(arg)]

    def satisfy(self, arg=None):
        return self._satisfy_coded(self._to_assumptions(arg))

    def _satisfy_coded(self, assumptions=[]):
        return self.solver.solve(assumptions)[0]

    def entity_card_probs(self, cards, agents, arg=None):
        assumptions = self._to_assumptions(arg) if arg else []
        agent_card_probs = {}
        for a in agents:
            agent_card_probs[a] = {}
            for c in cards:
                if not self._satisfy_coded(assumptions + [-self.var_map[has(a, c)]]):
                    agent_card_probs[a][c] = 1.0
                elif not self.satisfy(assumptions + [self.var_map[has(a, c)]]):
                    pass # agent doesn't have it
                else:
                    agent_card_probs[a][c] = 0.5
        return agent_card_probs

## PlayerState and strategies

def RegularActStrategy(self):
    def act(suggestion):
        for c in self.my_cards:
            if c in suggestion.cards:
                return suggestion.refuted(self.name, [c])
        return suggestion.not_refuted(self.name)
    return act

def ClueActStrategy(self):
    def act(suggestion):
        for typ in ("rooms", "people", "weapons"):
            for c in suggestion.cards:
                if c in self.my_cards_by_type[typ]:
                    return suggestion.refuted(self.name, [c])
        return suggestion.not_refuted(self.name)
    return act

def DumbEndturnStrategy(self):
    def endturn(other_player):
        return False
    return endturn

def SmartEndturnStrategy(self):
    def test_cards(other_player, assumptions, op_unknown, solver):
        for unknown_card in op_unknown:
            for test_assumption in (has(other_player, unknown_card),
                                    Not(has(other_player, unknown_card))):
                cprobs = solver.entity_card_probs(self.game.all_cards(),
                                                  [self.game.secret_name()],
                                                  test_assumption)
                if self.game.is_winning_cards(cprobs):
                    return Not(test_assumption).simplify()
        return []

    def endturn(other_player):
        if len(self.game.common_knowledge()) < 2:
            print("{} not enough common knowledge".format(self.name))
            return False

        if self.can_win():
            print("{} can win".format(self.name))
            return False

        learned = []
        common_knowledge = And(self.game.common_knowledge()).simplify().human_str()
        before_report = ["Common knowledge: {}\n".format(common_knowledge),
                         self.game.observer.report(),
                         self.report()]
        op_cards = self.card_probs(other_player)

        op_unknown = set(card for card, p in op_cards.items() if p < 1.0)
        op_held_cards = [card for card, p in op_cards.items() if p == 1.0]
        op_not_held_cards = [c for c in self.game.all_cards()
                            if c not in op_cards.keys()]

        if (len(op_held_cards) == self.game.n_cards_per_player(other_player) or
            len(op_unknown) > 8):
            return False

        solver = self.game.solver()
        assumptions = [has(other_player, c) for c in op_held_cards]
        assumptions.extend(Not(has(other_player, c)) for c in op_not_held_cards)
        for clause in assumptions:
            solver.add_clause(clause)

        keep_going = True
        while keep_going:
            keep_going = False
            op_cards = self.card_probs(other_player)
            op_unknown = set(card for card, p in op_cards.items() if p < 1.0)
            op_held_cards = [card for card, p in op_cards.items() if p == 1.0]
            op_not_held_cards = [c for c in self.game.all_cards()
                                if c not in op_cards.keys()]

            new_knowledge = test_cards(other_player, assumptions, op_unknown, solver)
            if new_knowledge:
                learned.append(new_knowledge)
                solver.add_clause(new_knowledge)
                keep_going = True
                self.update([new_knowledge])

        if learned:
            print("We LEARNED something from the announcement not(K delta)!  Before:")
            print("\n".join(before_report))
            print("Learned {}".format(", ".join(repr(l) for l in learned)))
            print("After: ", self.report())
            if self.can_win():
                print("WOWZERS!  We can win now though we couldn't before!  MATH!")
            return True

    return endturn

def RealSmartSuggestionStrategy(self):
    def count_unknown(probs):
        n = 0
        for key in probs:
            n += sum(1 for _, p in probs[key].items() if p < 1.0)
        return n

    def suggest():
        if self.can_win():
            return self.naive_suggestion()

        cards_to_guess = []

        secret_cards = self.card_probs(self.game.secret_name())
        known_secret_cards = {self.game.card_type(c): c
                                for c, p in secret_cards.items() if p == 1.0}
        unknown_secret_cards = {typ: [c for c, p in secret_cards.items()
                                        if p < 1.0 and self.game.card_type(c) == typ]
                                for typ in self.game.card_types()}

        unknown_cards_by_type = defaultdict(set)
        for other in self.others():
            cps = self.card_probs(other)
            for card, prob in cps.items():
                if prob < 1.0:
                    unknown_cards_by_type[self.game.card_type(card)].add(card)

        solver = self._solver()
        for typ in self.game.card_types():
            unknown_cards = unknown_cards_by_type[typ]
            if typ in known_secret_cards or len(unknown_cards) == 0:
                if len(self.my_cards_by_type[typ]) > 0:
                    to_guess = self.my_cards_by_type[typ][0]
                else:
                    to_guess = known_secret_cards[typ]
            else:
                min_secret_unknown = 100
                n_unknown_list = []
                for card in unknown_cards:
                    n_secret_unknown = 0
                    for p in self.others():
                        test_assumption = has(p, card)
                        cprobs = solver.entity_card_probs(self.game.all_cards(),
                                                   [self.game.secret_name()],
                                                   test_assumption)
                        n_secret_unknown += count_unknown(cprobs)
                    n_unknown_list.append((card, n_secret_unknown))
                    if n_secret_unknown < min_secret_unknown:
                        to_guess = card
                        min_secret_unknown = n_secret_unknown
            cards_to_guess.append(to_guess)
        return Suggestion(self.name, cards_to_guess)

    return suggest

def SmartSuggestionStrategy(self):
    def suggest():
        if self.can_win(): # we'll win at the end of the turn anyway, so whatever
            return self.naive_suggestion()

        secret_cards = self.card_probs(self.game.secret_name())
        known_secret_cards = {self.game.card_type(c): c
                                for c, p in secret_cards.items() if p == 1.0}
        unknown_secret_cards = {typ: [c for c, p in secret_cards.items()
                                        if p < 1.0 and self.game.card_type(c) == typ]
                                for typ in self.game.card_types()}
        cards_to_guess = []

        for typ in self.game.card_types():
            if len(unknown_secret_cards[typ]) > 0:
                cards_to_guess.append(unknown_secret_cards[typ][0])
            elif typ in known_secret_cards:
                if len(self.my_cards_by_type[typ]) > 0:
                    cards_to_guess.append(self.my_cards_by_type[typ][0])
                else:
                    cards_to_guess.append(known_secret_cards[typ])
            else:
                raise Exception("D'oh we're boned {}".format(secret_cards))
        assert(not set(cards_to_guess).issubset(set(self.my_cards)))

        return Suggestion(self.name, cards_to_guess)
    return suggest

def RegularSuggestionStrategy(self):
    def suggest():
        if self.can_win(): # we'll win at the end of the turn anyway, so whatever
            return self.naive_suggestion()

        secret_cards = self.card_probs(self.game.secret_name())
        cards = []
        unknown_cards_by_type = defaultdict(set)
        for other in self.others():
            cps = self.card_probs(other)
            for card, prob in cps.items():
                if prob < 1.0:
                    unknown_cards_by_type[self.game.card_type(card)].add(card)

        for typ in self.game.card_types():
            if unknown_cards_by_type[typ]:
                cards.append(unknown_cards_by_type[typ].pop())
            elif len(self.my_cards_by_type[typ]) > 0:
                cards.append(random.choice(self.my_cards_by_type[typ]))
            else: # choose the card in the secret box
                cps = self.card_probs(self.game.secret_name())
                cards.append([c for c, p in cps.items() if self.game.card_type(c) == typ][0])

        assert(not set(cards).issubset(set(self.my_cards)))

        return Suggestion(self.name, cards)
    return suggest

class PlayerState(object):
    def __init__(self, name, my_cards, initial_knowledge, game):
        self.name = name
        self.my_cards = my_cards
        self.game = game
        self._card_probs = None
        self.my_cards_by_type = defaultdict(list)
        for c in self.my_cards:
            self.my_cards_by_type[self.game.card_type(c)].append(c)
        self._initial_knowledge = initial_knowledge
        self._knowledge = initial_knowledge[:]
        self.endturn_strategy = DumbEndturnStrategy(self)
        self.act_strategy = RegularActStrategy(self)
        self.suggestion_strategy = SmartSuggestionStrategy(self)
        self.update([])

    def update(self, new_knowledge):
        self._knowledge += new_knowledge
        self._card_probs = None

    def knowledge(self):
        return self._knowledge

    def _solver(self):
        solver = self.game.solver()
        for clause in self.knowledge():
            solver.add_clause(clause)
        return solver

    def entity_card_probs(self):
        if not self._card_probs:
            solver = self._solver()
            self._card_probs = solver.entity_card_probs(
                self.game.all_cards(), self.game.entities())

        return self._card_probs

    def card_probs(self, entity):
        ecp = self.entity_card_probs()
        return ecp[entity]

    def can_win(self):
        return self.game.is_winning_cards(self.entity_card_probs())

    def set_suggestion_strategy(self, Strategy):
        self.suggestion_strategy = Strategy(self)

    def suggestion(self):
        return self.suggestion_strategy()

    def naive_suggestion(self):
        cards = []
        for typ in self.game.card_types():
            subcards = self.game.cards_of_type(typ)
            c = random.choice(subcards)
            while c in self.my_cards:
                c = random.choice(subcards)
            cards.append(c)
        assert(not set(cards).issubset(set(self.my_cards)))
        return Suggestion(self.name, cards)

    def set_act_strategy(self, Strategy):
        self.act_strategy = Strategy(self)

    def act(self, suggestion):
        return self.act_strategy(suggestion)

    def others(self):
        return sorted(set(self.game.entities()).difference([self.name]))

    def known_cards(self):
        known = set()
        for o in self.others():
            cps = self.card_probs(o)
            for c, p in cps.items():
                if p == 1.0: known.add(c)
        return known

    def set_endturn_strategy(self, Strategy):
        self.endturn_strategy = Strategy(self)

    def endturn(self, other_player):
        return self.endturn_strategy(other_player)

    def report(self):
        max_player_name = max(len(e) for e in self.game.entities())
        indent = max_player_name + 3
        r = ["Knowledge of {}:".format(self.name)]
        for e in self.others():
            subreport = self.game.report_by_cardtype(self.card_probs(e),
                                                     " " * indent)
            r.append("  {}{}".format(e.ljust(indent - 1), subreport.lstrip()))
        return "\n".join(r) + "\n"

class Suggestion(object):
    def __init__(self, accuser, cards):
        self.accuser = accuser
        self.cards = cards
        self.non_refutors = []
        self.refutor = None
        self.cards_seen = []
        self.is_done = False
        self.description = ["{} suggested {}".format(
            self.accuser, ", ".join(cards))]

    def is_finished(self):
        return self.is_done

    def refuted(self, refutor, cards=[]):
        self.refutor = refutor
        self.cards_seen = cards
        self.description.append("{} refuted by showing {}".format(
            self.refutor, ", ".join(self.cards_seen)))
        self.is_done = True
        return self

    def not_refuted(self, player):
        self.non_refutors.append(player)
        self.description.append("{} could not refute".format(player))
        return self

    def common_knowledge(self):
        conjs = []
        for nr in self.non_refutors:
            conjs.extend(Not(has(nr, c)) for c in self.cards)

        if self.refutor:
            conjs.append(Or([has(self.refutor, c) for c in self.cards]))

        # accuser doesn't have all the cards they just suggested
        conjs.append(Or([Not(has(self.accuser, c)) for c in self.cards]))

        return conjs

    def new_knowledge(self, player):
        if player == self.accuser and self.cards_seen:
            return [has(self.refutor, c) for c in self.cards_seen]
        return []

    def __str__(self):
        return "\n".join(self.description)

class Game(object):
    def __init__(self, game_type, deal):
        self.game_type = game_type
        self.names = []
        self.players = {}
        self.observer = PlayerState("observer", [], [], self)
        self.observer.set_endturn_strategy(SmartEndturnStrategy)
        self.deal = deal
        self.initial_constraints = None
        for player_name in self.game_type.players:
            self.add_player(player_name, deal.get(player_name, []))

    def secret_name(self):
        return self.game_type.secret_name

    def n_card_types(self):
        return len(self.game_type.cards_by_type.keys())

    def card_types(self):
        return self.game_type.cards_by_type.keys()

    def cards_of_type(self, typ):
        return self.game_type.cards_by_type[typ]

    def all_cards(self):
        return self.game_type.all_cards()

    def card_type(self, card):
        return self.game_type.card_type(card)

    def n_cards_per_player(self, player):
        return len(self.deal[player])

    def is_winning_cards(self, entity_card_probs):
        secret_cards = entity_card_probs[self.secret_name()]
        return len(secret_cards) == self.n_card_types()

    def entities(self):
        return list(self.players.keys()) + [self.game_type.secret_name]

    def common_knowledge(self):
        return self.observer.knowledge()

    def add_player(self, name, cards):
        not_my_cards = set(self.all_cards()).difference(cards)
        initial_knowledge = ([has(name, c) for c in cards] +
                             [Not(has(name, c)) for c in not_my_cards])

        self.players[name] = PlayerState(name, cards, initial_knowledge, self)
        self.names.append(name)

    def get_player(self, name): # sigh...
        return self.players[name]

    def make_one(self, suggestion):
        for name, player in self.players.items():
            player.update(suggestion.new_knowledge(name))

        self.observer.update(suggestion.common_knowledge())
        return self

    def make(self, *suggestions):
        for suggestion in suggestions:
            self.make_one(suggestion)
        return self

    def turn(self, name):
        i = self.names.index(name)
        order = self.names[i:] + self.names[:i]
        others = set(self.names).difference([name])

        s = self.players[name].suggestion()
        for n in order[1:]:
            s = self.players[n].act(s)
            if s.is_finished():
                break

        print(str(s) + "\n")
        self.make_one(s)

        if self.players[name].can_win():
            print(name, "won!")
            print(self.report(name))
            print(self.observer.report())
            return False
        else:
            print(self.report(name))
            for other in others:
                self.players[other].endturn(name)
            self.observer.endturn(name)
            for pname in self.names:
                if pname != name:
                    print(self.report(pname))

        return True

    def solver(self):
        player_n_cards = {p: len(cs) for p, cs in self.deal.items()}
        s = self.game_type.solver(player_n_cards, self.observer.knowledge())
        return s

    def report(self, player_name):
        return self.players[player_name].report()

    ## XXX: can move to player?
    def report_by_cardtype(self, card_probs, indent=""):
        r = []
        for cards in self.game_type.cards_by_type.values():
            known = sorted([c.upper() for c, p in card_probs.items()
                            if c in cards and p == 1.0])
            unknown = sorted([c for c, p in card_probs.items()
                              if c in cards and p < 1.0])
            s = [indent]
            if known:
                s.append(", ".join(known))
            if unknown:
                s.append("({})".format(", ".join(unknown)))

            r.append(" ".join(s))
        return "\n".join(r)
